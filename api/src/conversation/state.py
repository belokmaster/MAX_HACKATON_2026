from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DialogStep(str, Enum):
    """Этапы диалога с пользователем."""
    AWAIT_ADDRESS = "await_address"   # Ожидание ввода адреса дома
    AWAIT_PROBLEM = "await_problem"   # Ожидание описания проблемы
    CLARIFYING = "clarifying"         # Ожидание уточнения зоны ответственности кнопками
    AWAIT_BOOKING = "await_booking"   # Ожидание выбора смены мастера
    IDLE = "idle"                     # Заявка создана, готов к приему новой проблемы


@dataclass
class ConversationState:
    """Состояние сессии взаимодействия с пользователем."""
    user_id: int
    chat_id: int
    step: DialogStep = DialogStep.AWAIT_ADDRESS
    uk_id: str | None = None
    original_text: str = ""
    category: str | None = None
    responsibility: str | None = None
    clarification_step: int = 0
    pending_appeal_id: str | None = None
    last_bot_message_id: str | None = None
