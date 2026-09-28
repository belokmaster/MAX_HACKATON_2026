from __future__ import annotations

from src.conversation.state import ConversationState


def can_proceed_to_booking(state: ConversationState) -> bool:
    """Проверка возможности перехода к выбору смены (категория и зона ответственности определены)."""
    if not state.category or not state.responsibility:
        return False
    return state.responsibility.lower() in ("uk", "resident")


def is_emergency(state: ConversationState) -> bool:
    """Проверка, является ли обращение аварийной ситуацией."""
    if state.responsibility and state.responsibility.lower() == "emergency":
        return True
    if state.category and state.category.lower() == "emergency":
        return True
    return False


def is_max_clarifications(state: ConversationState) -> bool:
    """Проверка достижения лимита шагов уточнения (максимум 2 шага)."""
    return state.clarification_step >= 2
