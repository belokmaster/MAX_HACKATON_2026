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


CATEGORY_RU: dict[str, str] = {
    "electric": "Электрика",
    "plumbing": "Сантехника",
    "elevator": "Лифт",
    "carpentry": "Двери, окна, домофон",
    "general": "Общедомовое имущество",
    "emergency": "Авария",
    "unknown": "Не определена",
}

ZONE_RU: dict[str, str] = {
    "uk": "УК (бесплатно)",
    "resident": "жилец (платно)",
    "emergency": "аварийная служба",
    "unknown": "уточняет диспетчер",
}

STATUS_RU: dict[str, str] = {
    "open": "Открыта",
    "scheduled": "Назначена",
    "in_progress": "В работе",
    "done": "Завершена",
    "cancelled": "Отменена",
    "needs_clarification": "Требует уточнения",
}

SPECIALIST_RU: dict[str, str] = {
    "electric": "Дежурный электрик",
    "plumbing": "Дежурный сантехник",
    "elevator": "Мастер по лифтам",
    "carpentry": "Плотник / мастер по дверям",
    "general": "Мастер по общедомовому имуществу",
}


def format_category_ru(cat: str | Category | None) -> str:
    """Возвращает русское наименование категории."""
    if not cat:
        return "Общая"
    val = (cat.value if hasattr(cat, "value") else str(cat)).lower()
    return CATEGORY_RU.get(val, str(cat))


def format_specialist_ru(cat: str | Category | None) -> str:
    """Возвращает наименование специалиста на русском языке."""
    if not cat:
        return "Дежурный мастер"
    val = (cat.value if hasattr(cat, "value") else str(cat)).lower()
    if val in SPECIALIST_RU:
        return SPECIALIST_RU[val]
    cat_ru = format_category_ru(cat).lower()
    return f"Дежурный мастер ({cat_ru})"
