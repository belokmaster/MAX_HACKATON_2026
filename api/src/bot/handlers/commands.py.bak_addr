"""
Обработчики команд бота: /start, /help, /status, /admin.
"""
from __future__ import annotations

import logging
from src.bot.client import MaxBotClient
from src.conversation import store as conv_store
from src.conversation.state import DialogStep
from src.appeals import service as appeal_service
from src.config import get_settings
from src.data.housing import get_uk_by_id

log = logging.getLogger(__name__)


def extract_ids(update: dict) -> tuple[int, int]:
    """
    Извлечение идентификатора пользователя и идентификатора чата из события.
    Поддерживает контракты событий bot_started и message_created платформы MAX.
    """
    # 1. Формат bot_started: user и chat_id на верхнем уровне
    if "user" in update and "chat_id" in update:
        u_obj = update["user"]
        u_id = u_obj.get("user_id", 0) if isinstance(u_obj, dict) else int(u_obj)
        return int(u_id), int(update["chat_id"])

    # 2. Формат message_created: message.sender и message.recipient
    msg = update.get("message")
    if not isinstance(msg, dict):
        msg = update.get("payload", {}).get("message", {}) if isinstance(update.get("payload"), dict) else {}

    sender = msg.get("sender", {}) if isinstance(msg.get("sender"), dict) else {}
    user_id = sender.get("user_id", 0)

    recipient = msg.get("recipient", {}) if isinstance(msg.get("recipient"), dict) else {}
    chat_id = recipient.get("chat_id") or update.get("chat_id") or user_id

    # 3. Fallback на payload
    payload = update.get("payload", {})
    if isinstance(payload, dict) and "user" in payload:
        p_user = payload["user"]
        p_uid = p_user.get("user_id", 0) if isinstance(p_user, dict) else int(p_user)
        p_cid = payload.get("chat_id") or p_uid
        return int(p_uid), int(p_cid)

    return int(user_id), int(chat_id)


async def handle_start(client: MaxBotClient, update: dict) -> None:
    """
    Обработка запуска бота (bot_started) и команды /start.
    Сбрасывает диалоговое состояние и запрашивает адрес дома.
    """
    user_id, chat_id = extract_ids(update)
    log.info("Команда /start: сброс состояния диалога для user_id=%s, chat_id=%s", user_id, chat_id)
    state = conv_store.get_or_create(user_id, chat_id)
    
    state.step = DialogStep.AWAIT_ADDRESS
    state.uk_id = None
    state.pending_appeal_id = None
    state.category = None
    state.responsibility = None
    state.original_text = ""
    conv_store.save(state)
    
    await client.send_message(
        chat_id=chat_id,
        user_id=user_id,
        text="Добро пожаловать! Я помогу вам быстро оформить заявку в управляющую компанию.\nПожалуйста, укажите адрес вашего дома (например: «ул. Пушкина, д. 10»):"
    )


async def handle_help(client: MaxBotClient, update: dict) -> None:
    """
    Справка по боту (/help): контакты привязанной УК и аварийной службы.
    """
    user_id, chat_id = extract_ids(update)
    state = conv_store.get(user_id)
    log.info("Команда /help: запрос справки user_id=%s, привязанная УК=%s", user_id, state.uk_id if state else None)
    
    text = "Бот диспетчерской ЖКХ. Позволяет подать заявку мастеру или вызвать аварийную службу.\n\n"
    if state and state.uk_id:
        uk_info = get_uk_by_id(state.uk_id)
        if uk_info:
            text += f"Ваша управляющая компания: {uk_info.uk_name}\nТелефон УК: {uk_info.uk_phone}\nАварийная служба: {uk_info.emergency_phone}"
        else:
            text += "Управляющая компания не найдена. Попробуйте ввести адрес заново через команду /start."
    else:
        text += "Чтобы начать работу, отправьте команду /start и укажите ваш адрес."
        
    await client.send_message(chat_id=chat_id, user_id=user_id, text=text)


async def handle_status(client: MaxBotClient, update: dict) -> None:
    """
    Просмотр статуса активных заявок пользователя (/status).
    """
    user_id, chat_id = extract_ids(update)
    appeals = appeal_service.get_user_appeals(user_id)
    log.info("Команда /status: запрос статуса заявок user_id=%s, найдено заявок: %d", user_id, len(appeals))
    
    if not appeals:
        await client.send_message(chat_id=chat_id, user_id=user_id, text="У вас нет активных заявок.")
        return
        
    for appeal in appeals:
        status_ru = {
            "open": "Открыта",
            "scheduled": "Назначена",
            "in_progress": "В работе",
            "done": "Завершена",
            "cancelled": "Отменена",
            "needs_clarification": "Требует уточнения",
        }.get(str(appeal.status).lower(), str(appeal.status))

        text = f"Заявка #{appeal.id} | Категория: {appeal.category} | Статус: {status_ru} | Смена: {appeal.window_label or 'без смены'}"
        attachments = []
        if appeal.status in ("open", "scheduled"):
            attachments.append({
                "type": "inline_keyboard",
                "payload": {
                    "buttons": [
                        [{"type": "callback", "text": "Отменить заявку", "payload": f"appeal:cancel:{appeal.id}"}]
                    ]
                }
            })
        await client.send_message(chat_id=chat_id, user_id=user_id, text=text, attachments=attachments if attachments else None)


async def handle_admin(client: MaxBotClient, update: dict) -> None:
    """
    Панель диспетчера (/admin) для пользователей из списка ADMIN_USER_IDS.
    Выводит список открытых заявок.
    """
    user_id, chat_id = extract_ids(update)
    settings = get_settings()
    
    # Проверка прав администратора — молча игнорируем, не раскрывая существование команды
    if user_id not in settings.ADMIN_USER_IDS:
        log.warning("Игнорирование /admin: пользователь %s не является администратором", user_id)
        return
        
    appeals = appeal_service.get_all_appeals()
    open_appeals = [a for a in appeals if a.status in ("open", "scheduled")]
    log.info("Команда /admin: доступ разрешен для admin_id=%s, открытых заявок: %d", user_id, len(open_appeals))
    
    if not open_appeals:
        await client.send_message(chat_id=chat_id, user_id=user_id, text="Нет открытых заявок.")
        return
        
    text = "Список открытых заявок:\n"
    for a in open_appeals[:10]:
        text += f"#{a.id} | Пользователь: {a.user_id} | {a.category} | {a.responsibility} | {a.status} | {a.window_label or 'без смены'}\n"
        
    attachments = []
    if len(open_appeals) > 10:
        attachments.append({
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [{"type": "callback", "text": "Следующая страница", "payload": "admin:page:1"}]
                ]
            }
        })
        
    await client.send_message(chat_id=chat_id, user_id=user_id, text=text, attachments=attachments if attachments else None)
