from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Category(str, Enum):
    ELECTRIC = "ELECTRIC"
    PLUMBING = "PLUMBING"
    ELEVATOR = "ELEVATOR"
    GENERAL = "GENERAL"
    CARPENTRY = "CARPENTRY"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            val_upper = value.upper()
            for member in cls:
                if member.value == val_upper or member.name == val_upper:
                    return member
        return None


class Responsibility(str, Enum):
    UK = "UK"
    RESIDENT = "RESIDENT"
    EMERGENCY = "EMERGENCY"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            val_upper = value.upper()
            for member in cls:
                if member.value == val_upper or member.name == val_upper:
                    return member
        return None


@dataclass
class ClassifyResult:
    """Результат классификации обращения пользователя."""
    category: Category
    responsibility: Responsibility
    confidence: float
    clarification_question: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.category, Category):
            self.category = Category(self.category)
        if not isinstance(self.responsibility, Responsibility):
            self.responsibility = Responsibility(self.responsibility)
        self.confidence = float(self.confidence)

    @property
    def needs_clarification(self) -> bool:
        """Флаг необходимости уточнения зоны ответственности или категории."""
        return self.confidence < 0.7 or self.responsibility == Responsibility.UNKNOWN
