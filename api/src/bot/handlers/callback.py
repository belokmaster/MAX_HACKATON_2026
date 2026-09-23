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
from src.scheduler import store as scheduler_store, service as scheduler_service

log = logging.getLogger(__name__)


def extract_callback(update: dict) -> tuple[int, int, str, str, str]:
    """Извлечение данных callback-события: user_id, chat_id, callback_id, payload, message_id."""
    payload_obj = update.get("payload", {})
    callback_id = payload_obj["callback_id"]
    user_id = payload_obj["user"]["user_id"]
    message = payload_obj.get("message", {})
    chat_id = message.get("recipient", {}).get("chat_id") or user_id
    payload = payload_obj.get("payload", "")
    message_id = message.get("body", {}).get("mid", "")
    return user_id, chat_id, callback_id, payload, message_id


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
    
    # КРИТИЧНО: всегда первым делом подтверждаем получение callback
    await client.answer_callback(callback_id)
    
    state = conv_store.get_or_create(user_id, chat_id)
    if not state:
        return
        
    if payload == "clarify:zone:uk":
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
        
        await client.send_message(
            chat_id=chat_id,
            text="Это зона ответственности УК. Ремонт бесплатный. Пожалуйста, выберите время визита мастера:",
            attachments=[shift_windows_keyboard(formatted_windows)]
        )
        state.step = DialogStep.AWAIT_BOOKING
        conv_store.save(state)
        
    elif payload == "clarify:zone:resident":
        state.responsibility = "resident"
        await client.send_message(
            chat_id=chat_id,
            text="Это зона вашей ответственности (платная услуга от 500 рублей). Вызвать мастера УК?",
            attachments=[resident_choice_keyboard()]
        )
        state.step = DialogStep.CLARIFYING
        conv_store.save(state)
        
    elif payload == "clarify:zone:emergency":
        uk_info = get_uk_by_id(state.uk_id) if state.uk_id else None
        emergency_phone = uk_info.emergency_phone if uk_info else "+7 000 000-00-00"
        await client.send_message(
            chat_id=chat_id,
            text=f"ВНИМАНИЕ: ЭТО АВАРИЯ! Пожалуйста, немедленно свяжитесь с аварийной службой: {emergency_phone}"
        )
        appeal_service.create_appeal(
            user_id=user_id,
            chat_id=chat_id,
            uk_id=state.uk_id or "uk_01",
            category="emergency",
            responsibility="emergency",
            description=state.original_text,
        )
        reset_to_problem(state)
        
    elif payload == "resident:confirm":
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
        
        await client.send_message(
            chat_id=chat_id,
            text="Выберите время для визита платного мастера:",
            attachments=[shift_windows_keyboard(formatted_windows)]
        )
        state.step = DialogStep.AWAIT_BOOKING
        conv_store.save(state)
        
    elif payload == "resident:cancel":
        reset_to_problem(state)
        await client.send_message(chat_id=chat_id, text="Заявка отменена. Если потребуется помощь — обращайтесь.")
        
    elif payload.startswith("book:"):
        action_or_window = payload[5:]  # отрезаем префикс "book:"
        
        if action_or_window == "cancel":
            if state.pending_appeal_id:
                appeal_service.cancel_appeal(state.pending_appeal_id)
            reset_to_problem(state)
            await client.send_message(chat_id=chat_id, text="Оформление заявки отменено.")
        else:
            window_id = action_or_window
            if state.pending_appeal_id:
                scheduler_store.book_window(window_id, state.pending_appeal_id)
                window_label = scheduler_service.get_window_label(window_id)
                appeal_service.update_window(state.pending_appeal_id, window_id, window_label)
                
                category_display = state.category or "мастер"
                
                await client.send_message(
                    chat_id=chat_id,
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
        await client.send_message(
            chat_id=chat_id,
            text=f"Адрес подтвержден! Обслуживает **{uk_name}**.\nТеперь опишите вашу проблему:"
        )
        
    elif payload.startswith("appeal:cancel:"):
        appeal_id = payload.split("appeal:cancel:")[1]
        appeal_service.cancel_appeal(appeal_id)
        await client.send_message(chat_id=chat_id, text=f"Заявка #{appeal_id} успешно отменена.")
        
    elif payload.startswith("admin:page:"):
        n = int(payload.split(":")[2])
        await client.send_message(chat_id=chat_id, text=f"Страница списка заявок {n}.")
        
    elif payload == "menu:problem":
        await client.send_message(chat_id=chat_id, text="Пожалуйста, опишите вашу проблему:")
        state.step = DialogStep.AWAIT_PROBLEM
        conv_store.save(state)
