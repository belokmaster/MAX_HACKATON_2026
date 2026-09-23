from __future__ import annotations

from datetime import date, timedelta

from src.scheduler.store import (
    ShiftWindow,
    book_window,
    get_available_windows,
    get_window,
)

WEEKDAYS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}

MONTHS = {
    1: "янв",
    2: "фев",
    3: "мар",
    4: "апр",
    5: "мая",
    6: "июн",
    7: "июл",
    8: "авг",
    9: "сен",
    10: "окт",
    11: "ноя",
    12: "дек",
}


def format_windows_for_chat(windows: list[ShiftWindow]) -> list[dict]:
    """
    Форматирование списка доступных смен для сообщений и кнопок в чате.
    Возвращает список словарей: window_id, label, date_str, shift.
    Пример: "Сегодня: 09:00 — 13:00" или "Пн, 25 сен: 13:00 — 18:00".
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)
    results: list[dict] = []

    for w in windows:
        win_date = date.fromisoformat(w.date_str)
        if win_date == today:
            date_prefix = "Сегодня"
        elif win_date == tomorrow:
            date_prefix = "Завтра"
        else:
            w_name = WEEKDAYS.get(win_date.weekday(), "")
            m_name = MONTHS.get(win_date.month, "")
            date_prefix = f"{w_name}, {win_date.day} {m_name}"

        shift_str = w.shift.value if hasattr(w.shift, "value") else str(w.shift)
        if "morning" in shift_str.lower():
            time_slot = "09:00 — 13:00"
        else:
            time_slot = "13:00 — 18:00"

        label = f"{date_prefix}: {time_slot}"

        results.append({
            "window_id": w.window_id,
            "label": label,
            "date_str": w.date_str,
            "shift": shift_str,
        })

    return results


def get_window_label(window_id: str) -> str:
    """Получение понятного человеку описания смены по её идентификатору."""
    w = get_window(window_id)
    if w is None:
        parts = window_id.split(":")
        if len(parts) >= 2:
            return f"{parts[0]} ({parts[1]})"
        return window_id

    formatted = format_windows_for_chat([w])
    if formatted:
        return formatted[0]["label"]
    return window_id


__all__ = [
    "get_available_windows",
    "book_window",
    "get_window",
    "format_windows_for_chat",
    "get_window_label",
]
