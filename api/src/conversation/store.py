from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from src.conversation.state import ConversationState, DialogStep

_users_file: Path = Path("data/users.json")
_states: Dict[int, ConversationState] = {}


def configure(users_file: str | Path) -> None:
    """Настройка пути к файлу сохранения привязок пользователей к УК."""
    global _users_file
    _users_file = Path(users_file)


def _load_persisted_users() -> dict[str, str]:
    """Загрузка сохраненных привязок пользователей user_id -> uk_id из JSON."""
    if not _users_file.exists():
        return {}
    try:
        with open(_users_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _persist_user_uk(user_id: int, uk_id: str) -> None:
    """Сохранение привязки пользователя к УК в файл JSON."""
    data = _load_persisted_users()
    data[str(user_id)] = uk_id
    try:
        _users_file.parent.mkdir(parents=True, exist_ok=True)
        with open(_users_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_or_create(user_id: int, chat_id: int) -> ConversationState:
    """
    Получение текущего состояния пользователя или создание нового.
    Если ранее была привязана УК, она восстанавливается, а шаг переключается на AWAIT_PROBLEM.
    """
    if user_id in _states:
        state = _states[user_id]
        state.chat_id = chat_id
        return state

    saved_users = _load_persisted_users()
    saved_uk_id = saved_users.get(str(user_id))

    if saved_uk_id:
        state = ConversationState(
            user_id=user_id,
            chat_id=chat_id,
            step=DialogStep.AWAIT_PROBLEM,
            uk_id=saved_uk_id,
        )
    else:
        state = ConversationState(
            user_id=user_id,
            chat_id=chat_id,
            step=DialogStep.AWAIT_ADDRESS,
        )

    _states[user_id] = state
    return state


def get(user_id: int) -> ConversationState | None:
    """Получение состояния пользователя из оперативной памяти."""
    return _states.get(user_id)


def save(state: ConversationState) -> None:
    """Сохранение состояния пользователя в памяти и привязки УК на диск."""
    _states[state.user_id] = state
    if state.uk_id:
        _persist_user_uk(state.user_id, state.uk_id)


def reset_to_problem(state: ConversationState) -> ConversationState:
    """Сброс полей текущей проблемы и перевод на шаг ожидания новой проблемы."""
    state.step = DialogStep.AWAIT_PROBLEM
    state.original_text = ""
    state.category = None
    state.responsibility = None
    state.clarification_step = 0
    state.pending_appeal_id = None
    state.last_bot_message_id = None
    save(state)
    return state
