from __future__ import annotations
from src.clock import now_msk

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class AppealStatus(str, Enum):
    """Статусы жизненного цикла заявки."""
    OPEN = "open"               # Новая заявка
    SCHEDULED = "scheduled"     # Смена мастера назначена
    IN_PROGRESS = "in_progress" # Заявка в работе
    DONE = "done"               # Заявка выполнена
    CANCELLED = "cancelled"     # Заявка отменена
    NEEDS_CLARIFICATION = "needs_clarification"  # Требуется дополнительное уточнение


@dataclass
class Appeal:
    """Модель заявки жильца в управляющую компанию."""
    id: str
    user_id: int
    chat_id: int
    uk_id: str
    category: str            # Категория ("plumbing", "electric" и т.д.)
    responsibility: str      # Зона ответственности ("uk", "resident", "emergency")
    description: str         # Исходный текст обращения
    status: AppealStatus = AppealStatus.OPEN
    window_id: str | None = None     # Идентификатор забронированной смены
    window_label: str | None = None  # Текстовое описание смены для человека
    created_at: str = field(default_factory=lambda: now_msk().isoformat())
    updated_at: str = field(default_factory=lambda: now_msk().isoformat())

    def to_dict(self) -> dict:
        """Сериализация заявки в словарь."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "uk_id": self.uk_id,
            "category": self.category,
            "responsibility": self.responsibility,
            "description": self.description,
            "status": self.status.value if isinstance(self.status, AppealStatus) else self.status,
            "window_id": self.window_id,
            "window_label": self.window_label,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Appeal:
        """Создание экземпляра заявки из словаря."""
        status_val = data.get("status", AppealStatus.OPEN)
        if isinstance(status_val, AppealStatus):
            status = status_val
        else:
            try:
                status = AppealStatus(str(status_val).lower())
            except (ValueError, TypeError):
                status = AppealStatus.OPEN

        return cls(
            id=str(data["id"]),
            user_id=int(data["user_id"]),
            chat_id=int(data["chat_id"]),
            uk_id=str(data["uk_id"]),
            category=str(data["category"]),
            responsibility=str(data["responsibility"]),
            description=str(data["description"]),
            status=status,
            window_id=data.get("window_id"),
            window_label=data.get("window_label"),
            created_at=data.get("created_at") or now_msk().isoformat(),
            updated_at=data.get("updated_at") or now_msk().isoformat(),
        )
