"""
Обработчики callback-запросов от интерактивных inline-кнопок.
"""
from __future__ import annotations

import logging
from collections import deque
from src.bot.client import MaxBotClient
from src.conversation import store as conv_store
from src.conversation.state import DialogStep
from src.data.housing import get_uk_by_id
from src.bot.keyboards import (
    shift_windows_keyboard,
    resident_choice_keyboard,
    elements_keyboard,
    clarification_zone_keyboard,
)
from src.appeals import service as appeal_service
from src.appeals.schemas import AppealStatus
from src.scheduler import store as scheduler_store, service as scheduler_service
from src.classifier.categories import format_category_ru, format_specialist_ru, Responsibility
from src.classifier.elements import find_element

log = logging.getLogger(__name__)

_processed_callback_ids: deque[str] = deque(maxlen=1000)


def extract_callback(update: dict) -> tuple[int, int, str, str, str]:
    """
    Извлечение данных callback-события: user_id, chat_id, callback_id, payload, message_id.
    Поддерживает контракт платформы MAX (update['callback'], update['message']),
    а также возможную обертку payload.
    """
    cb = update.get("callback")
    if not isinstance(cb, dict):
        cb = update.get("payload", {}).get("callback", {}) if isinstance(update.get("payload"), dict) else {}
        if not cb and isinstance(update.get("payload"), dict):
            cb = update.get("payload")

    callback_id = cb.get("callback_id", "")
    payload = cb.get("payload", "")
    user = cb.get("user", {}) if isinstance(cb.get("user"), dict) else {}
    user_id = user.get("user_id", 0)

    msg = update.get("message")
    if not isinstance(msg, dict):
        msg = update.get("payload", {}).get("message", {}) if isinstance(update.get("payload"), dict) else {}

    recipient = msg.get("recipient", {}) if isinstance(msg.get("recipient"), dict) else {}
    chat_id = recipient.get("chat_id") or update.get("chat_id") or user_id

    body = msg.get("body", {}) if isinstance(msg.get("body"), dict) else {}
    message_id = body.get("mid", "")

    return int(user_id), int(chat_id), str(callback_id), str(payload), str(message_id)


def reset_to_problem(state) -> None:
    """Сброс состояния диалога до готовности принять новую проблему."""
    state.step = DialogStep.IDLE
    state.pending_appeal_id = None
    state.category = None
    state.responsibility = None
    state.original_text = ""
    conv_store.save(state)


async def handle_callback(client: MaxBotClient, update: dict) -> None:
    """Главный обработчик нажатия inline-кнопок."""
    user_id, chat_id, callback_id, payload, message_id = extract_callback(update)
    log.info("Получен callback: user_id=%s, chat_id=%s, payload='%s', callback_id=%s", user_id, chat_id, payload, callback_id)
    
    # КРИТИЧНО: всегда первым делом подтверждаем получение callback
    await client.answer_callback(callback_id)

    if callback_id and callback_id in _processed_callback_ids:
        log.info("Повторный callback_id=%s проигнорирован", callback_id)
        return
    if callback_id:
        _processed_callback_ids.append(callback_id)
    
    state = conv_store.get_or_create(user_id, chat_id)
    if not state:
        log.warning("Не удалось получить состояние диалога для user_id=%s", user_id)
        return

    zone_callbacks = {
        "clarify:zone:uk",
        "clarify:zone:resident",
        "clarify:zone:emergency",
    }
    if payload in zone_callbacks and state.step != DialogStep.CLARIFYING:
        log.info(
            "Повторный callback зоны проигнорирован: user_id=%s, payload=%s, шаг=%s",
            user_id,
            payload,
            state.step,
        )
        return

    if payload == "resident:confirm" and (
        state.step != DialogStep.CLARIFYING or state.responsibility != "resident"
    ):
        log.info("Повторный resident:confirm проигнорирован: user_id=%s, шаг=%s", user_id, state.step)
        return

    if payload == "resident:cancel" and (
        state.step != DialogStep.CLARIFYING or state.responsibility != "resident"
    ):
        log.info("Повторный resident:cancel проигнорирован: user_id=%s, шаг=%s", user_id, state.step)
        return
        
    if payload == "clarify:zone:uk":
        log.info("Пользователь выбрал зону ответственности УК (бесплатно): user_id=%s", user_id)
        state.responsibility = "uk"
        state.step = DialogStep.AWAIT_BOOKING
        conv_store.save(state)
        appeal = appeal_service.create_appeal(
            user_id=user_id,
            chat_id=chat_id,
            uk_id=state.uk_id or "uk_01",
            category=state.category or "general",
            responsibility="uk",
            description=state.original_text,
        )
        state.pending_appeal_id = appeal.id
        
        windows = scheduler_store.get_available_windows(state.category or "general", state.uk_id or "uk_01", 3, 4)
        formatted_windows = scheduler_service.format_windows_for_chat(windows)
        log.info("Предложено свободных смен: %d для заявки #%s", len(windows), appeal.id)
        
        await client.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text="Это зона ответственности УК. Ремонт бесплатный. Пожалуйста, выберите время визита мастера:",
            attachments=[shift_windows_keyboard(formatted_windows)]
        )
        conv_store.save(state)
        
    elif payload == "clarify:zone:resident":
        log.info("Пользователь выбрал зону жильца (платно): user_id=%s", user_id)
        state.responsibility = "resident"
        state.step = DialogStep.AWAIT_PROBLEM
        conv_store.save(state)
        await client.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text="Это зона вашей ответственности (платная услуга от 500 рублей). Вызвать мастера УК?",
            attachments=[resident_choice_keyboard()]
        )
        state.step = DialogStep.CLARIFYING
        conv_store.save(state)
        
    elif payload == "clarify:zone:emergency":
        log.warning("Пользователь выбрал зону АВАРИИ: user_id=%s, chat_id=%s", user_id, chat_id)
        reset_to_problem(state)
        uk_info = get_uk_by_id(state.uk_id) if state.uk_id else None
        emergency_phone = uk_info.emergency_phone if uk_info else "112"
        await client.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=f"ВНИМАНИЕ: ЭТО АВАРИЯ! Пожалуйста, немедленно свяжитесь с аварийной службой: {emergency_phone}"
        )
        
    elif payload == "resident:confirm":
        log.info("Жилец подтвердил вызов платного мастера: user_id=%s", user_id)
        state.step = DialogStep.AWAIT_BOOKING
        conv_store.save(state)
        appeal = appeal_service.create_appeal(
            user_id=user_id,
            chat_id=chat_id,
            uk_id=state.uk_id or "uk_01",
            category=state.category or "general",
            responsibility="resident",
            description=state.original_text,
        )
        state.pending_appeal_id = appeal.id
        
        windows = scheduler_store.get_available_windows(state.category or "general", state.uk_id or "uk_01", 3, 4)
        formatted_windows = scheduler_service.format_windows_for_chat(windows)
        log.info("Предложено платных смен: %d для заявки #%s", len(windows), appeal.id)
        
        await client.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text="Выберите время для визита платного мастера:",
            attachments=[shift_windows_keyboard(formatted_windows)]
        )
        conv_store.save(state)
        
    elif payload == "resident:cancel":
        log.info("Жилец отказался от платного вызова: user_id=%s", user_id)
        reset_to_problem(state)
        await client.send_message(chat_id=chat_id, user_id=user_id, text="Заявка отменена. Если потребуется помощь — обращайтесь.")
        
    elif payload.startswith("book:"):
        action_or_window = payload[5:]  # отрезаем префикс "book:"
        
        if action_or_window == "cancel":
            if state.step != DialogStep.AWAIT_BOOKING or not state.pending_appeal_id:
                # Заявка уже была отменена или завершена — игнорируем повторный клик
                log.info("Повторный book:cancel проигнорирован: user_id=%s, шаг=%s, pending_appeal_id=%s", user_id, state.step, state.pending_appeal_id)
            else:
                log.info("Жилец отменил выбор смены для заявки #%s: user_id=%s", state.pending_appeal_id, user_id)
                appeal_service.cancel_appeal(state.pending_appeal_id)
                reset_to_problem(state)
                await client.send_message(chat_id=chat_id, user_id=user_id, text="Оформление заявки отменено.")
        elif action_or_window == "dispatcher":
            if state.step != DialogStep.AWAIT_BOOKING or not state.pending_appeal_id:
                log.info(
                    "Повторный book:dispatcher проигнорирован: user_id=%s, шаг=%s, pending_appeal_id=%s",
                    user_id,
                    state.step,
                    state.pending_appeal_id,
                )
            else:
                appeal = appeal_service.get_appeal(state.pending_appeal_id)
                if appeal is None or appeal.user_id != user_id:
                    log.warning(
                        "Не удалось передать заявку #%s диспетчеру от user_id=%s",
                        state.pending_appeal_id,
                        user_id,
                    )
                    await client.send_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        text="Не удалось найти заявку. Попробуйте оформить обращение заново.",
                    )
                    return

                uk_info = get_uk_by_id(state.uk_id) if state.uk_id else None
                uk_phone = uk_info.uk_phone if uk_info else "телефон управляющей компании"
                await client.send_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=(
                        f"Заявка #{appeal.id} передана диспетчеру УК. "
                        f"С вами свяжутся для согласования времени.\n"
                        f"Телефон УК: {uk_phone}"
                    ),
                )
                reset_to_problem(state)
        else:
            window_id = action_or_window
            if state.step != DialogStep.AWAIT_BOOKING or not state.pending_appeal_id:
                # Состояние уже сброшено — игнорируем повторный клик
                log.info("Повторный book:%s проигнорирован: user_id=%s, шаг=%s", window_id, user_id, state.step)
            else:
                log.info("Выбрана смена %s для заявки #%s (user_id=%s)", window_id, state.pending_appeal_id, user_id)
                window_parts = window_id.split(":")
                expected_speciality = (state.category or "general").lower()
                expected_uk_id = state.uk_id or "uk_01"
                if (
                    len(window_parts) != 4
                    or window_parts[2].lower() != expected_speciality
                    or window_parts[3] != expected_uk_id
                ):
                    log.warning(
                        "Отклонена смена, не соответствующая заявке #%s: window_id=%s",
                        state.pending_appeal_id,
                        window_id,
                    )
                    await client.send_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        text="Эта смена недоступна для текущей заявки. Выберите время из предложенного списка.",
                    )
                    return
                booked_window = scheduler_store.book_window(window_id, state.pending_appeal_id)
                if booked_window is None:
                    log.info(
                        "Смена %s уже недоступна для заявки #%s: user_id=%s",
                        window_id,
                        state.pending_appeal_id,
                        user_id,
                    )
                    await client.send_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        text="Эта смена уже занята. Пожалуйста, выберите другое доступное время.",
                        attachments=[
                            shift_windows_keyboard(
                                scheduler_service.format_windows_for_chat(
                                    scheduler_store.get_available_windows(
                                        state.category or "general",
                                        state.uk_id or "uk_01",
                                        3,
                                        4,
                                    )
                                )
                            )
                        ],
                    )
                    return
                window_label = scheduler_service.get_window_label(window_id)
                appeal_service.update_window(state.pending_appeal_id, window_id, window_label)
                
                specialist_label = format_specialist_ru(state.category)
                category_label = format_category_ru(state.category)
                log.info("Заявка #%s успешно назначена на смену: %s", state.pending_appeal_id, window_label)
                
                await client.send_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=(
                        f"Заявка #{state.pending_appeal_id} оформлена!\n"
                        f"Тема: {category_label}\n"
                        f"Специалист: {specialist_label}\n"
                        f"Время визита: {window_label}\n"
                        f"Мастер свяжется с вами перед приходом."
                    )
                )
                reset_to_problem(state)
            
    elif payload.startswith("cat:"):
        cat_val = payload[4:].lower()
        log.info("Выбрана категория через кнопку: user_id=%s, cat=%s", user_id, cat_val)
        state.category = cat_val
        state.step = DialogStep.CLARIFY_ITEM
        conv_store.save(state)
        await client.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=f"Категория: {format_category_ru(cat_val)}. Что именно вышло из строя?",
            attachments=[elements_keyboard(cat_val)],
        )

    elif payload.startswith("item:"):
        item_key = payload[5:]
        log.info("Выбран элемент неисправности: user_id=%s, категория=%s, item_key=%s", user_id, state.category, item_key)

        if item_key == "unknown":
            state.step = DialogStep.CLARIFYING
            conv_store.save(state)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text="Уточните, пожалуйста: это общедомовая система (УК) или личное оборудование в квартире?",
                attachments=[clarification_zone_keyboard(state.category or "general")],
            )
            return

        element = find_element(state.category, item_key)
        if element is None:
            state.step = DialogStep.CLARIFYING
            conv_store.save(state)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text="Уточните, пожалуйста: это зона ответственности управляющей компании или личное имущество?",
                attachments=[clarification_zone_keyboard(state.category or "general")],
            )
            return

        if element.zone == Responsibility.EMERGENCY:
            log.warning("Выбран аварийный элемент: user_id=%s, элемент=%s", user_id, element.key)
            reset_to_problem(state)
            uk_info = get_uk_by_id(state.uk_id) if state.uk_id else None
            emergency_phone = uk_info.emergency_phone if uk_info else "112"
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text=f"ВНИМАНИЕ: ЭТО АВАРИЯ! Пожалуйста, немедленно свяжитесь с аварийной службой: {emergency_phone}",
            )

        elif element.zone == Responsibility.UK:
            log.info("Элемент относится к УК: user_id=%s, элемент=%s", user_id, element.key)
            state.responsibility = "uk"
            appeal = appeal_service.create_appeal(
                user_id=user_id,
                chat_id=chat_id,
                uk_id=state.uk_id or "uk_01",
                category=state.category or "general",
                responsibility="uk",
                description=f"{element.label}: {state.original_text or element.label}",
            )
            state.pending_appeal_id = appeal.id
            state.step = DialogStep.AWAIT_BOOKING
            conv_store.save(state)

            windows = scheduler_store.get_available_windows(state.category or "general", state.uk_id or "uk_01", 3, 4)
            formatted_windows = scheduler_service.format_windows_for_chat(windows)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text=f"«{element.label}» — это зона ответственности УК. Ремонт бесплатный. Выберите удобное время визита мастера:",
                attachments=[shift_windows_keyboard(formatted_windows)],
            )

        elif element.zone == Responsibility.RESIDENT:
            log.info("Элемент относится к жильцу: user_id=%s, элемент=%s", user_id, element.key)
            state.responsibility = "resident"
            state.step = DialogStep.CLARIFYING
            conv_store.save(state)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text=f"«{element.label}» — это зона вашей ответственности (платная услуга от 500 рублей). Вызвать мастера УК?",
                attachments=[resident_choice_keyboard()],
            )

        else:
            state.step = DialogStep.CLARIFYING
            conv_store.save(state)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text=f"По вопросу «{element.label}» требуется уточнение. Укажите принадлежность:",
                attachments=[clarification_zone_keyboard(state.category or "general")],
            )

    elif payload.startswith("address:"):
        uk_id = payload[8:]
        state.uk_id = uk_id
        state.step = DialogStep.AWAIT_PROBLEM
        conv_store.save(state)
        uk_info = get_uk_by_id(uk_id)
        uk_name = uk_info.uk_name if uk_info else "УК"
        log.info("Адрес подтвержден через кнопку: user_id=%s, uk_id=%s, uk_name='%s'", user_id, uk_id, uk_name)
        await client.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=f"Адрес подтвержден! Обслуживает **{uk_name}**.\nТеперь опишите вашу проблему:"
        )
        
    elif payload.startswith("appeal:cancel:"):
        appeal_id = payload.split("appeal:cancel:")[1]
        log.info("Запрос на отмену заявки #%s от user_id=%s", appeal_id, user_id)
        appeal = appeal_service.get_appeal(appeal_id)
        if appeal is None or appeal.user_id != user_id:
            log.warning("Отклонена отмена чужой или неизвестной заявки #%s от user_id=%s", appeal_id, user_id)
            await client.send_message(chat_id=chat_id, user_id=user_id, text="Заявка не найдена.")
        elif appeal.status == AppealStatus.CANCELLED:
            log.info("Повторная отмена заявки #%s проигнорирована: user_id=%s", appeal_id, user_id)
            return
        elif appeal.status not in (AppealStatus.OPEN, AppealStatus.SCHEDULED):
            await client.send_message(chat_id=chat_id, user_id=user_id, text="Эту заявку уже нельзя отменить.")
        else:
            appeal_service.cancel_appeal(appeal_id)
            await client.send_message(chat_id=chat_id, user_id=user_id, text=f"Заявка #{appeal_id} успешно отменена.")
        
    elif payload.startswith("admin:page:"):
        n = int(payload.split(":")[2])
        log.info("Переключение страницы диспетчера: user_id=%s, страница=%d", user_id, n)
        from src.bot.handlers.commands import render_admin_page
        await render_admin_page(client, user_id, chat_id, page=n)
        
    elif payload == "menu:problem":
        log.info("Пользователь запросил подачу новой проблемы: user_id=%s", user_id)
        await client.send_message(chat_id=chat_id, user_id=user_id, text="Пожалуйста, опишите вашу проблему:")
        state.step = DialogStep.AWAIT_PROBLEM
        conv_store.save(state)
