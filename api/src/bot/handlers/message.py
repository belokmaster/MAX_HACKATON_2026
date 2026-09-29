"""
Основной обработчик текстовых сообщений пользователей.
Маршрутизирует ввод по этапам диалога:
- AWAIT_ADDRESS: поиск адреса и привязка к управляющей компании
- AWAIT_PROBLEM: анализ проблемы и классификация
- CLARIFYING / AWAIT_BOOKING: напоминание об использовании кнопок
"""
from __future__ import annotations

import logging
from src.bot.client import MaxBotClient
from src.bot.keyboards import shift_windows_keyboard, clarification_zone_keyboard, resident_choice_keyboard
from src.conversation import store as conv_store
from src.conversation.state import DialogStep
from src.data.housing import find_uk, get_uk_by_id
from src.classifier.engine import classify
from src.classifier.categories import Responsibility
from src.appeals import service as appeal_service
from src.scheduler import store as scheduler_store, service as scheduler_service
from src.bot.keyboards import category_keyboard, elements_keyboard
from src.classifier.categories import Category

log = logging.getLogger(__name__)


def extract_message_data(update: dict) -> tuple[int, int, str, str]:
    """
    Извлечение данных из события создания сообщения (message_created).
    Возвращает (user_id, chat_id, text, mid).
    Поддерживает контракт платформы MAX (update['message']), а также вложенный payload.
    """
    msg = update.get("message")
    if not isinstance(msg, dict):
        msg = update.get("payload", {}).get("message", {}) if isinstance(update.get("payload"), dict) else {}

    sender = msg.get("sender", {}) if isinstance(msg.get("sender"), dict) else {}
    user_id = sender.get("user_id", 0)

    recipient = msg.get("recipient", {}) if isinstance(msg.get("recipient"), dict) else {}
    chat_id = recipient.get("chat_id") or user_id
    if not chat_id:
        chat_id = update.get("chat_id") or user_id

    body = msg.get("body", {}) if isinstance(msg.get("body"), dict) else {}
    text = (body.get("text") or "").strip()
    mid = body.get("mid", "")

    return int(user_id), int(chat_id), text, str(mid)


def extract_ids(update: dict) -> tuple[int, int]:
    """Извлечение идентификатора пользователя и идентификатора чата из любого типа события."""
    u_id, c_id, _, _ = extract_message_data(update)
    if u_id and c_id:
        return u_id, c_id

    user_obj = update.get("user") or update.get("payload", {}).get("user", {})
    if isinstance(user_obj, dict):
        u_id = user_obj.get("user_id", 0)
    c_id = update.get("chat_id") or update.get("payload", {}).get("chat_id") or u_id
    return int(u_id), int(c_id)


async def handle_message(client: MaxBotClient, update: dict) -> None:
    """Обработка текстового сообщения от пользователя."""
    user_id, chat_id, text, mid = extract_message_data(update)
    
    if not text:
        log.warning("Получено сообщение без текста: user_id=%s, chat_id=%s, update=%s", user_id, chat_id, update)
        return

    log.info("Получено текстовое сообщение: user_id=%s, chat_id=%s, текст='%s', mid=%s", user_id, chat_id, text, mid)
        
    # Обработка команд бота
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        log.info("Вызов команды %s пользователем user_id=%s", cmd, user_id)
        if cmd == "/start":
            from src.bot.handlers.commands import handle_start
            await handle_start(client, update)
        elif cmd == "/help":
            from src.bot.handlers.commands import handle_help
            await handle_help(client, update)
        elif cmd == "/status":
            from src.bot.handlers.commands import handle_status
            await handle_status(client, update)
        elif cmd == "/admin":
            from src.bot.handlers.commands import handle_admin
            await handle_admin(client, update)
        else:
            log.warning("Неизвестная команда: user_id=%s, cmd=%s", user_id, cmd)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text=f"Неизвестная команда {cmd}. Список доступных команд: /start, /help, /status"
            )
        return
        
    state = conv_store.get_or_create(user_id, chat_id)
    log.info("Текущий шаг диалога: user_id=%s, step=%s, uk_id=%s", user_id, state.step.value, state.uk_id)
        
    if state.step == DialogStep.IDLE:
        state.step = DialogStep.AWAIT_PROBLEM
        
    if state.step == DialogStep.AWAIT_ADDRESS:
        log.info("Поиск адреса в реестре домов: query='%s', user_id=%s", text, user_id)
        matches = find_uk(text)
        if len(matches) == 1:
            match = matches[0]
            state.uk_id = match.uk_id
            state.step = DialogStep.AWAIT_PROBLEM
            conv_store.save(state)
            log.info("Адрес однозначно определен: user_id=%s, uk_id=%s, uk_name='%s'", user_id, match.uk_id, match.uk_name)
            
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text=f"Нашел ваш дом! Обслуживает **{match.uk_name}**.\nТеперь опишите вашу проблему:"
            )
        elif len(matches) > 1 and len(matches) <= 3:
            log.info("Найдено несколько похожих адресов (%d) для user_id=%s: %s", len(matches), user_id, [m.address for m in matches])
            buttons = []
            for i, match in enumerate(matches):
                buttons.append([{"type": "callback", "text": match.address, "payload": f"address:{match.uk_id}"}])
                
            attachments = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text="Найдено несколько похожих адресов. Пожалуйста, выберите ваш:",
                attachments=attachments
            )
        else:
            log.warning("Адрес не найден в реестре: query='%s', user_id=%s", text, user_id)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text="Адрес не найден в базе. Попробуйте уточнить (например: «ул. Пушкина, д. 10») или свяжитесь с диспетчерской УК."
            )
            
    elif state.step in (DialogStep.AWAIT_PROBLEM, DialogStep.CLARIFY_CATEGORY, DialogStep.CLARIFY_ITEM):
        state.original_text = text
        log.info("Классификация описания проблемы: user_id=%s, текст='%s'", user_id, text)
        result = await classify(text)
        
        state.category = result.category.value if hasattr(result.category, "value") else str(result.category)
        log.info(
            "Результат классификации: user_id=%s, категория=%s, ответственность=%s, уверенность=%.2f",
            user_id, state.category, result.responsibility.value, result.confidence
        )
        
        if result.responsibility == Responsibility.EMERGENCY:
            log.warning("Обнаружена АВАРИЙНАЯ ситуация: user_id=%s, chat_id=%s, текст='%s'", user_id, chat_id, text)
            uk_info = get_uk_by_id(state.uk_id) if state.uk_id else None
            emergency_phone = uk_info.emergency_phone if uk_info else "112"
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text=f"ВНИМАНИЕ: ЭТО АВАРИЯ! Пожалуйста, немедленно свяжитесь с аварийной службой: {emergency_phone}"
            )
            appeal = appeal_service.create_appeal(
                user_id=user_id,
                chat_id=chat_id,
                uk_id=state.uk_id or "uk_01",
                category=state.category,
                responsibility="emergency",
                description=text,
            )
            log.info("Создана аварийная заявка #%s для user_id=%s", appeal.id, user_id)
            state.step = DialogStep.IDLE
            conv_store.save(state)
            
        elif result.responsibility == Responsibility.UK and result.confidence >= 0.8:
            state.responsibility = "uk"
            appeal = appeal_service.create_appeal(
                user_id=user_id,
                chat_id=chat_id,
                uk_id=state.uk_id or "uk_01",
                category=state.category,
                responsibility="uk",
                description=text,
            )
            state.pending_appeal_id = appeal.id
            log.info("Зона ответственности УК (бесплатно): создана заявка #%s для user_id=%s", appeal.id, user_id)
            
            windows = scheduler_store.get_available_windows(state.category, state.uk_id or "uk_01", 3, 4)
            formatted_windows = scheduler_service.format_windows_for_chat(windows)
            log.info("Найдено доступных смен: %d для категории %s, uk_id=%s", len(windows), state.category, state.uk_id)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text="Это зона ответственности УК. Ремонт бесплатный. Выберите удобное время визита мастера:",
                attachments=[shift_windows_keyboard(formatted_windows)]
            )
            state.step = DialogStep.AWAIT_BOOKING
            conv_store.save(state)
            
        elif result.responsibility == Responsibility.RESIDENT and result.confidence >= 0.8:
            state.responsibility = "resident"
            log.info("Зона ответственности жильца (платно): предложение платного вызова user_id=%s", user_id)
            await client.send_message(
                chat_id=chat_id,
                user_id=user_id,
                text="Это зона вашей ответственности (платная услуга от 500 рублей). Вызвать мастера УК?",
                attachments=[resident_choice_keyboard()]
            )
            state.step = DialogStep.CLARIFYING
            conv_store.save(state)
            
        else:
            log.info("Неоднозначная проблема: user_id=%s, категория=%s", user_id, state.category)
            state.clarification_step = 0
            if result.category == Category.UNKNOWN:
                state.step = DialogStep.CLARIFY_CATEGORY
                conv_store.save(state)
                await client.send_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text="Не совсем понял, что случилось. Выберите тему или опишите проблему подробнее:",
                    attachments=[category_keyboard()],
                )
            else:
                state.step = DialogStep.CLARIFY_ITEM
                conv_store.save(state)
                await client.send_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text="Что именно вышло из строя?",
                    attachments=[elements_keyboard(state.category)],
                )

    elif state.step in [DialogStep.CLARIFYING, DialogStep.AWAIT_BOOKING]:
        log.info("Получен текст вместо нажатия кнопки: user_id=%s, шаг=%s, текст='%s'", user_id, state.step.value, text)
        await client.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text="Пожалуйста, воспользуйтесь кнопками в сообщении выше для продолжения."
        )
