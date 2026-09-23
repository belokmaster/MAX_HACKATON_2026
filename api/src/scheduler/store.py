from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict

from src.data.specialists import ShiftType, get_specialists, Specialist


# Хранилище бронирований конкретных специалистов:
# ключ: f"{date_str}:{shift}:{specialist_id}" -> список appeal_id
_specialist_bookings: Dict[str, list[str]] = {}


@dataclass
class ShiftWindow:
    """Окно рабочей смены для категории работ и управляющей компании."""
    date_str: str  # Формат ISO: "2026-09-24"
    shift: ShiftType
    speciality: str
    uk_id: str
    max_capacity: int = 4  # Максимальная нагрузка на одного специалиста за смену
    booked_appeal_ids: list[str] = field(default_factory=list)

    @property
    def window_id(self) -> str:
        """Уникальный идентификатор смены."""
        shift_val = self.shift.value if hasattr(self.shift, "value") else str(self.shift)
        return f"{self.date_str}:{shift_val}:{self.speciality}:{self.uk_id}"

    @property
    def is_available(self) -> bool:
        """
        Проверка доступности смены.
        Смена доступна, если хотя бы один специалист, обслуживающий данную УК,
        имеет свободные места с учетом его занятости во всех закрепленных за ним УК.
        """
        specs = get_specialists(self.speciality, self.uk_id)
        if not specs:
            return False
        shift_val = self.shift.value if hasattr(self.shift, "value") else str(self.shift)
        for s in specs:
            key = f"{self.date_str}:{shift_val}:{s.id}"
            booked = len(_specialist_bookings.get(key, []))
            if booked < self.max_capacity:
                return True
        return False

    @property
    def booked_count(self) -> int:
        """Общее число заявок, назначенных на специалистов этой смены."""
        specs = get_specialists(self.speciality, self.uk_id)
        if not specs:
            return 0
        shift_val = self.shift.value if hasattr(self.shift, "value") else str(self.shift)
        return sum(len(_specialist_bookings.get(f"{self.date_str}:{shift_val}:{s.id}", [])) for s in specs)

    @property
    def available_slots(self) -> int:
        """Количество оставшихся свободных слотов у специалистов данной смены."""
        specs = get_specialists(self.speciality, self.uk_id)
        shift_val = self.shift.value if hasattr(self.shift, "value") else str(self.shift)
        return sum(
            max(0, self.max_capacity - len(_specialist_bookings.get(f"{self.date_str}:{shift_val}:{s.id}", [])))
            for s in specs
        )


_windows: Dict[str, ShiftWindow] = {}


def _ensure_windows(speciality: str, uk_id: str, n_days: int, capacity: int) -> None:
    """Создание слотов смен ShiftWindow на сегодня и следующие n_days дней при их отсутствии."""
    today = date.today()
    for day_offset in range(n_days + 1):
        d = today + timedelta(days=day_offset)
        date_str = d.isoformat()
        for shift in (ShiftType.MORNING, ShiftType.AFTERNOON):
            win = ShiftWindow(
                date_str=date_str,
                shift=shift,
                speciality=speciality,
                uk_id=uk_id,
                max_capacity=capacity,
            )
            if win.window_id not in _windows:
                _windows[win.window_id] = win


def get_available_windows(
    speciality: str,
    uk_id: str,
    n_days: int = 3,
    capacity: int = 4,
) -> list[ShiftWindow]:
    """
    Возвращает доступные для записи смены мастеров, отсортированные по дате и времени.
    Учитывает занятость мастеров, работающих на несколько УК одновременно.
    """
    _ensure_windows(speciality, uk_id, n_days, capacity)
    today = date.today()
    max_date = today + timedelta(days=n_days)

    available: list[ShiftWindow] = []
    for win in _windows.values():
        if win.speciality == speciality and win.uk_id == uk_id and win.is_available:
            win_date = date.fromisoformat(win.date_str)
            if today <= win_date <= max_date:
                available.append(win)

    def _shift_order(shift: ShiftType) -> int:
        val = shift.value if hasattr(shift, "value") else str(shift)
        return 0 if "morning" in val.lower() else 1

    available.sort(key=lambda w: (w.date_str, _shift_order(w.shift)))
    return available


def book_window(window_id: str, appeal_id: str) -> ShiftWindow | None:
    """
    Бронирование смены для указанной заявки.
    Заявка распределяется на наименее загруженного мастера, обслуживающего данную УК.
    Нагрузка мастера учитывается сквозным образом во всех УК, где он работает.
    """
    win = _windows.get(window_id)
    parts = window_id.split(":")
    if len(parts) < 4:
        return None
    date_str, shift_str, speciality, uk_id = parts[0], parts[1], parts[2], parts[3]

    if win is None:
        _ensure_windows(speciality, uk_id)
        win = _windows.get(window_id)

    if win is None:
        return None

    if appeal_id in win.booked_appeal_ids:
        return win

    if not win.is_available:
        return None

    specs = get_specialists(speciality, uk_id)
    if not specs:
        return None

    # Поиск доступных мастеров со свободными слотами
    available_specs: list[tuple[int, Specialist]] = []
    for s in specs:
        key = f"{date_str}:{shift_str}:{s.id}"
        booked = len(_specialist_bookings.get(key, []))
        if booked < win.max_capacity:
            available_specs.append((booked, s))

    if not available_specs:
        return None

    # Выбираем мастера с наименьшим количеством бронирований на эту смену
    available_specs.sort(key=lambda item: item[0])
    chosen_spec = available_specs[0][1]

    spec_key = f"{date_str}:{shift_str}:{chosen_spec.id}"
    _specialist_bookings.setdefault(spec_key, []).append(appeal_id)

    win.booked_appeal_ids.append(appeal_id)
    return win


def unbook_appeal(appeal_id: str) -> None:
    """Освобождение места мастера при отмене заявки."""
    for key, appeal_list in _specialist_bookings.items():
        if appeal_id in appeal_list:
            appeal_list.remove(appeal_id)

    for win in _windows.values():
        if appeal_id in win.booked_appeal_ids:
            win.booked_appeal_ids.remove(appeal_id)


def get_window(window_id: str) -> ShiftWindow | None:
    """Получение объекта смены по ее уникальному идентификатору."""
    return _windows.get(window_id)
