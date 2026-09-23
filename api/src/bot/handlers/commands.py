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
    """Извлечение идентификатора пользователя и идентификатора чата из события."""
    payload = update.get("payload", {})
    if "user" in payload:  # Событие запуска бота (bot_started)
        return payload["user"]["user_id"], payload["chat_id"]
    msg = payload.get("message", {})
    user_id = msg.get("sender", {}).get("user_id", 0)
    chat_id = payload.get("chat_id") or user_id
    return user_id, chat_id


async def handle_start(client: MaxBotClient, update: dict) -> None:
    """
    Обработка запуска бота (bot_started) и команды /start.
    Сбрасывает диалоговое состояние и запрашивает адрес дома.
    """
    user_id, chat_id = extract_ids(update)
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
        text="Добро пожаловать! Я помогу вам быстро оформить заявку в управляющую компанию.\nПожалуйста, укажите адрес вашего дома (например: «ул. Пушкина, д. 10»):"
    )


async def handle_help(client: MaxBotClient, update: dict) -> None:
    """
    Справка по боту (/help): контакты привязанной УК и аварийной службы.
    """
    user_id, chat_id = extract_ids(update)
    state = conv_store.get(user_id)
    
    text = "Бот диспетчерской ЖКХ. Позволяет подать заявку мастеру или вызвать аварийную службу.\n\n"
    if state and state.uk_id:
        uk_info = get_uk_by_id(state.uk_id)
        if uk_info:
            text += f"Ваша управляющая компания: {uk_info.uk_name}\nТелефон УК: {uk_info.uk_phone}\nАварийная служба: {uk_info.emergency_phone}"
        else:
            text += "Управляющая компания не найдена. Попробуйте ввести адрес заново через команду /start."
    else:
        text += "Чтобы начать работу, отправьте команду /start и укажите ваш адрес."
        
    await client.send_message(chat_id=chat_id, text=text)


async def handle_status(client: MaxBotClient, update: dict) -> None:
    """
    Просмотр статуса активных заявок пользователя (/status).
    """
    user_id, chat_id = extract_ids(update)
    appeals = appeal_service.get_user_appeals(user_id)
    
    if not appeals:
        await client.send_message(chat_id=chat_id, text="У вас нет активных заявок.")
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
        await client.send_message(chat_id=chat_id, text=text, attachments=attachments if attachments else None)


async def handle_admin(client: MaxBotClient, update: dict) -> None:
    """
    Панель диспетчера (/admin) для пользователей из списка ADMIN_USER_IDS.
    Выводит список открытых заявок.
    """
    user_id, chat_id = extract_ids(update)
    settings = get_settings()
    
    # Проверка прав администратора
    if user_id not in settings.ADMIN_USER_IDS:
        return
        
    appeals = appeal_service.get_all_appeals()
    open_appeals = [a for a in appeals if a.status in ("open", "scheduled")]
    
    if not open_appeals:
        await client.send_message(chat_id=chat_id, text="Нет открытых заявок.")
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
        
    await client.send_message(chat_id=chat_id, text=text, attachments=attachments if attachments else None)
