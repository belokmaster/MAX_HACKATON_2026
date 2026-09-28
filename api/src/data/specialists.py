from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ShiftType(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"


class Speciality(str, Enum):
    ELECTRIC = "electric"
    PLUMBING = "plumbing"
    ELEVATOR = "elevator"
    GENERAL = "general"
    CARPENTRY = "carpentry"


@dataclass
class Specialist:
    """Модель специалиста управляющей компании с поддержкой работы на несколько УК."""
    id: str
    speciality: Speciality
    uk_ids: list[str] = field(default_factory=list)  # Список обслуживаемых УК
    display_name: str = ""  # Название роли (без указания личных ФИО), например: "Дежурный электрик"
    uk_id: str | None = None  # Основная УК для обратной совместимости

    def __post_init__(self) -> None:
        if self.uk_id and self.uk_id not in self.uk_ids:
            self.uk_ids.append(self.uk_id)
        if not self.uk_id and self.uk_ids:
            self.uk_id = self.uk_ids[0]


SPECIALISTS: list[Specialist] = [
    # Электрики
    Specialist(
        id="spec_elec_1",
        speciality=Speciality.ELECTRIC,
        uk_ids=["uk_01"],
        display_name="Дежурный электрик",
    ),
    Specialist(
        id="spec_elec_2",
        speciality=Speciality.ELECTRIC,
        uk_ids=["uk_01", "uk_02"],  # Обслуживает обе УК: УК Комфорт и УК Уют
        display_name="Дежурный электрик",
    ),
    Specialist(
        id="spec_elec_3",
        speciality=Speciality.ELECTRIC,
        uk_ids=["uk_02"],
        display_name="Дежурный электрик",
    ),
    # Сантехники
    Specialist(
        id="spec_plumb_1",
        speciality=Speciality.PLUMBING,
        uk_ids=["uk_01"],
        display_name="Дежурный сантехник",
    ),
    Specialist(
        id="spec_plumb_2",
        speciality=Speciality.PLUMBING,
        uk_ids=["uk_01", "uk_02"],  # Обслуживает обе УК: УК Комфорт и УК Уют
        display_name="Дежурный сантехник",
    ),
    Specialist(
        id="spec_plumb_3",
        speciality=Speciality.PLUMBING,
        uk_ids=["uk_02"],
        display_name="Дежурный сантехник",
    ),
    # Мастер по лифтам (совмещает работу в обеих УК)
    Specialist(
        id="spec_elev_1",
        speciality=Speciality.ELEVATOR,
        uk_ids=["uk_01", "uk_02"],
        display_name="Мастер по лифтам",
    ),
    # Мастер общего профиля (совмещает работу в обеих УК)
    Specialist(
        id="spec_gen_1",
        speciality=Speciality.GENERAL,
        uk_ids=["uk_01", "uk_02"],
        display_name="Мастер общего профиля",
    ),
    # Плотник (совмещает работу в обеих УК)
    Specialist(
        id="spec_carp_1",
        speciality=Speciality.CARPENTRY,
        uk_ids=["uk_01", "uk_02"],
        display_name="Плотник",
    ),
]


def get_specialists(speciality: Speciality | str, uk_id: str) -> list[Specialist]:
    """Получение списка мастеров по специальности и управляющей компании (с учетом работы на несколько УК)."""
    spec_val = speciality.value if hasattr(speciality, "value") else str(speciality).lower()
    return [
        s for s in SPECIALISTS
        if uk_id in s.uk_ids and (
            s.speciality == speciality 
            or s.speciality.value == spec_val 
            or s.speciality.value.lower() == spec_val
        )
    ]


def get_specialist_by_id(specialist_id: str) -> Specialist | None:
    """Поиск специалиста по его уникальному идентификатору."""
    for s in SPECIALISTS:
        if s.id == specialist_id:
            return s
    return None


def get_specialists_by_uk(uk_id: str) -> list[Specialist]:
    """Получение всех специалистов, обслуживающих указанную управляющую компанию."""
    return [s for s in SPECIALISTS if uk_id in s.uk_ids]


def shift_label(shift: ShiftType) -> str:
    """Получение понятного человеку диапазона времени для смены."""
    if shift == ShiftType.MORNING or shift == "morning":
        return "09:00 — 13:00"
    elif shift == ShiftType.AFTERNOON or shift == "afternoon":
        return "13:00 — 18:00"
    raise ValueError(f"Неизвестный тип смены: {shift}")


def shift_start_hour(shift: ShiftType) -> int:
    """Получение часа начала смены (9 или 13)."""
    if shift == ShiftType.MORNING or shift == "morning":
        return 9
    elif shift == ShiftType.AFTERNOON or shift == "afternoon":
        return 13
    raise ValueError(f"Неизвестный тип смены: {shift}")
