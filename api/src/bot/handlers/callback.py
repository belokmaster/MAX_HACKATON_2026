"""
Обработчики callback-запросов от интерактивных inline-кнопок.
"""
from __future__ import annotations

import logging
from src.bot.client import MaxBotClient
from src.conversation import store as conv_store
from src.conversation.state import DialogStep
from src.data.housing import get_uk_by_id
from src.bot.keyboards import shift_windows_keyboard, resident_choice_keyboard
from src.appeals import service as appeal_service
from src.appeals.schemas import AppealStatus
from src.scheduler import store as scheduler_store, service as scheduler_service
from src.bot.keyboards import elements_keyboard
from src.classifier.categories import Responsibility
from src.classifier.elements import find_element

log = logging.getLogger(__name__)


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


async def _offer_uk(client, state, chat_id, user_id, reason=None):
    """Зона УК: создаём заявку и предлагаем выбрать смену."""
    state.responsibility = "uk"
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
    log.info("Зона УК: заявка #%s, свободных смен: %d", appeal.id, len(windows))
    text = "Это зона ответственности УК. Ремонт бесплатный."
    if reason:
        text += f"\nОснование: {reason}"
    text += "\nВыберите время визита мастера:"
    await client.send_message(
        chat_id=chat_id,
        user_id=user_id,
        text=text,
        attachments=[shift_windows_keyboard(formatted_windows)],
    )
    state.step = DialogStep.AWAIT_BOOKING
    conv_store.save(state)


async def _offer_resident(client, state, chat_id, user_id, reason=None):
    """Зона жильца: предлагаем платный вызов мастера УК."""
    state.responsibility = "resident"
    text = "Это зона вашей ответственности (платная услуга от 500 рублей)."
    if reason:
        text += f"\nОснование: {reason}"
    text += "\nВызвать мастера УК?"
    await client.send_message(
        chat_id=chat_id,
        user_id=user_id,
        text=text,
        attachments=[resident_choice_keyboard()],
    )
    state.step = DialogStep.CLARIFYING
    conv_store.save(state)


async def _go_emergency(client, state, chat_id, user_id):
    """Авария: даём телефон аварийной службы и фиксируем заявку."""
    log.warning("Зона АВАРИИ: user_id=%s, chat_id=%s", user_id, chat_id)
    uk_info = get_uk_by_id(state.uk_id) if state.uk_id else None
    emergency_phone = uk_info.emergency_phone if uk_info else "112"
    await client.send_message(
        chat_id=chat_id,
        user_id=user_id,
        text=f"ВНИМАНИЕ: ЭТО АВАРИЯ! Пожалуйста, немедленно свяжитесь с аварийной службой: {emergency_phone}",
    )
    appeal = appeal_service.create_appeal(
        user_id=user_id,
        chat_id=chat_id,
        uk_id=state.uk_id or "uk_01",
        category="emergency",
        responsibility="emergency",
        description=state.original_text,
    )
    log.info("Создана аварийная заявка #%s для user_id=%s", appeal.id, user_id)
    reset_to_problem(state)


async def _to_dispatcher(client, state, chat_id, user_id):
    """Зона не определена: честно передаём обращение диспетчеру УК."""
    appeal = appeal_service.create_appeal(
        user_id=user_id,
        chat_id=chat_id,
        uk_id=state.uk_id or "uk_01",
        category=state.category or "general",
        responsibility="unknown",
        description=state.original_text,
    )
    appeal_service.update_status(appeal.id, AppealStatus.NEEDS_CLARIFICATION)
    log.info("Обращение #%s передано диспетчеру (зона не определена)", appeal.id)
    await client.send_message(
        chat_id=chat_id,
        user_id=user_id,
        text=(
            "Не могу однозначно определить, кто отвечает за эту неисправность. "
            f"Передал обращение #{appeal.id} диспетчеру УК: он уточнит детали и свяжется с вами. "
            "Статус можно посмотреть командой /status."
        ),
    )
    reset_to_problem(state)


async def handle_callback(client: MaxBotClient, update: dict) -> None:
    """Главный обработчик нажатия inline-кнопок."""
    user_id, chat_id, callback_id, payload, message_id = extract_callback(update)
    log.info("Получен callback: user_id=%s, chat_id=%s, payload='%s', callback_id=%s", user_id, chat_id, payload, callback_id)
    
    # КРИТИЧНО: всегда первым делом подтверждаем получение callback
    await client.answer_callback(callback_id)
    
    state = conv_store.get_or_create(user_id, chat_id)
    if not state:
        log.warning("Не удалось получить состояние диалога для user_id=%s", user_id)
        return

    # Защита от устаревших кнопок: действие допустимо только на своём шаге диалога
    allowed_steps = {
        "resident:": (DialogStep.CLARIFYING,),
        "book:": (DialogStep.AWAIT_BOOKING,),
    }
    for prefix, steps in allowed_steps.items():
        if (payload or "").startswith(prefix) and state.step not in steps:
            log.info("Устаревшая кнопка проигнорирована: user_id=%s, payload=%s, шаг=%s",
                     user_id, payload, state.step)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text="Эта кнопка уже неактуальна. Опишите проблему заново или отправьте /status.",
            )
            return
        
    if (payload or "").startswith("cat:"):
        if state.step != DialogStep.CLARIFY_CATEGORY:
            log.info("Устаревшая кнопка категории: user_id=%s, шаг=%s", user_id, state.step)
            return
        state.category = payload.split(":", 1)[1]
        state.clarification_step += 1
        state.step = DialogStep.CLARIFY_ITEM
        conv_store.save(state)
        await client.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text="Что именно вышло из строя?",
            attachments=[elements_keyboard(state.category)],
        )

    elif (payload or "").startswith("item:"):
        if state.step != DialogStep.CLARIFY_ITEM:
            log.info("Устаревшая кнопка элемента: user_id=%s, шаг=%s", user_id, state.step)
            return
        el = find_element(state.category, payload.split(":", 1)[1])
        zone = el.zone if el else Responsibility.UNKNOWN
        reason = el.reason if el else None
        log.info("Выбран элемент: user_id=%s, категория=%s, элемент=%s, зона=%s",
                 user_id, state.category, payload, zone)
        if zone == Responsibility.UK:
            await _offer_uk(client, state, chat_id, user_id, reason)
        elif zone == Responsibility.RESIDENT:
            await _offer_resident(client, state, chat_id, user_id, reason)
        elif zone == Responsibility.EMERGENCY:
            await _go_emergency(client, state, chat_id, user_id)
        else:
            await _to_dispatcher(client, state, chat_id, user_id)

    elif payload == "resident:confirm":
        log.info("Жилец подтвердил вызов платного мастера: user_id=%s", user_id)
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
        state.step = DialogStep.AWAIT_BOOKING
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
                
                category_display = state.category or "мастер"
                log.info("Заявка #%s успешно назначена на смену: %s", state.pending_appeal_id, window_label)
                
                await client.send_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=(
                        f"Заявка #{state.pending_appeal_id} оформлена!\n"
                        f"Специалист: Дежурный {category_display}\n"
                        f"Время визита: {window_label}\n"
                        f"Мастер свяжется с вами перед приходом."
                    )
                )
                reset_to_problem(state)
            
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
        elif appeal.status not in (AppealStatus.OPEN, AppealStatus.SCHEDULED):
            await client.send_message(chat_id=chat_id, user_id=user_id, text="Эту заявку уже нельзя отменить.")
        else:
            appeal_service.cancel_appeal(appeal_id)
            await client.send_message(chat_id=chat_id, user_id=user_id, text=f"Заявка #{appeal_id} успешно отменена.")
        
    elif payload.startswith("admin:page:"):
        n = int(payload.split(":")[2])
        log.info("Переключение страницы диспетчера: user_id=%s, страница=%d", user_id, n)
        await client.send_message(chat_id=chat_id, user_id=user_id, text=f"Страница списка заявок {n}.")
        
    elif payload == "menu:problem":
        log.info("Пользователь запросил подачу новой проблемы: user_id=%s", user_id)
        await client.send_message(chat_id=chat_id, user_id=user_id, text="Пожалуйста, опишите вашу проблему:")
        state.step = DialogStep.AWAIT_PROBLEM
        conv_store.save(state)
