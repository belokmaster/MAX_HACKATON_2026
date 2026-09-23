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

log = logging.getLogger(__name__)


def extract_ids(update: dict) -> tuple[int, int]:
    """Извлечение идентификатора пользователя и идентификатора чата из события."""
    payload = update.get("payload", {})
    if "user" in payload:
        return payload["user"]["user_id"], payload["chat_id"]
    msg = payload.get("message", {})
    user_id = msg.get("sender", {}).get("user_id", 0)
    chat_id = payload.get("chat_id") or user_id
    return user_id, chat_id


async def handle_message(client: MaxBotClient, update: dict) -> None:
    """Обработка текстового сообщения от пользователя."""
    user_id, chat_id = extract_ids(update)
    payload = update.get("payload", {})
    message = payload.get("message", {})
    text = message.get("body", {}).get("text", "").strip()
    
    if not text:
        return
        
    # Команды бота обрабатываются отдельными обработчиками
    if text.startswith("/"):
        return
        
    state = conv_store.get_or_create(user_id, chat_id)
        
    if state.step == DialogStep.IDLE:
        state.step = DialogStep.AWAIT_PROBLEM
        
    if state.step == DialogStep.AWAIT_ADDRESS:
        matches = find_uk(text)
        if len(matches) == 1:
            match = matches[0]
            state.uk_id = match.uk_id
            state.step = DialogStep.AWAIT_PROBLEM
            conv_store.save(state)
            
            await client.send_message(
                chat_id=chat_id,
                text=f"Нашел ваш дом! Обслуживает **{match.uk_name}**.\nТеперь опишите вашу проблему:"
            )
        elif len(matches) > 1 and len(matches) <= 3:
            buttons = []
            for i, match in enumerate(matches):
                buttons.append([{"type": "callback", "text": match.address, "payload": f"address:{match.uk_id}"}])
                
            attachments = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
            await client.send_message(
                chat_id=chat_id,
                text="Найдено несколько похожих адресов. Пожалуйста, выберите ваш:",
                attachments=attachments
            )
        else:
            await client.send_message(
                chat_id=chat_id,
                text="Адрес не найден в базе. Попробуйте уточнить (например: «ул. Пушкина, д. 10») или свяжитесь с диспетчерской УК."
            )
            
    elif state.step == DialogStep.AWAIT_PROBLEM:
        state.original_text = text
        result = await classify(text)
        
        state.category = result.category.value if hasattr(result.category, "value") else str(result.category)
        
        if result.responsibility == Responsibility.EMERGENCY:
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
                category=state.category,
                responsibility="emergency",
                description=text,
            )
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
            
            windows = scheduler_store.get_available_windows(state.category, state.uk_id or "uk_01", 3, 4)
            formatted_windows = scheduler_service.format_windows_for_chat(windows)
            await client.send_message(
                chat_id=chat_id,
                text="Это зона ответственности УК. Ремонт бесплатный. Выберите удобное время визита мастера:",
                attachments=[shift_windows_keyboard(formatted_windows)]
            )
            state.step = DialogStep.AWAIT_BOOKING
            conv_store.save(state)
            
        elif result.responsibility == Responsibility.RESIDENT and result.confidence >= 0.8:
            state.responsibility = "resident"
            await client.send_message(
                chat_id=chat_id,
                text="Это зона вашей ответственности (платная услуга от 500 рублей). Вызвать мастера УК?",
                attachments=[resident_choice_keyboard()]
            )
            state.step = DialogStep.CLARIFYING
            conv_store.save(state)
            
        else:
            state.step = DialogStep.CLARIFYING
            conv_store.save(state)
            await client.send_message(
                chat_id=chat_id,
                text="Уточните, пожалуйста, где именно находится неисправность:",
                attachments=[clarification_zone_keyboard(state.category)]
            )
            
    elif state.step in [DialogStep.CLARIFYING, DialogStep.AWAIT_BOOKING]:
        await client.send_message(
            chat_id=chat_id,
            text="Пожалуйста, воспользуйтесь кнопками в сообщении выше для продолжения."
        )
