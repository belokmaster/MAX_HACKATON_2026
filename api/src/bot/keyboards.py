from typing import Any

def clarification_zone_keyboard(category: str) -> dict[str, Any]:
    """
    Клавиатура для уточнения зоны ответственности (УК или жилец).
    Две кнопки выбора и кнопка аварийной ситуации при необходимости.
    """
    return {
        "type": "inline_keyboard",
        "payload": {
            "buttons": [
                [
                    {"type": "callback", "text": "В подъезде (УК)", "payload": "clarify:zone:uk"},
                    {"type": "callback", "text": "В квартире (жилец)", "payload": "clarify:zone:resident"}
                ]
            ]
        }
    }

def shift_windows_keyboard(windows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Клавиатура для выбора смены мастера.
    Каждая доступная смена выводится отдельной строкой.
    Последняя кнопка — Отмена.
    """
    buttons = []
    for window in windows[:6]:
        buttons.append([
            {"type": "callback", "text": window["label"], "payload": f"book:{window['window_id']}"}
        ])
    
    buttons.append([
        {"type": "callback", "text": "Отмена", "payload": "book:cancel"}
    ])
    
    return {
        "type": "inline_keyboard",
        "payload": {
            "buttons": buttons
        }
    }

def resident_choice_keyboard() -> dict[str, Any]:
    """
    Клавиатура для платных услуг жильца: подтверждение вызова платного мастера или отмена.
    """
    return {
        "type": "inline_keyboard",
        "payload": {
            "buttons": [
                [{"type": "callback", "text": "Да, запишите платного мастера", "payload": "resident:confirm"}],
                [{"type": "callback", "text": "Отмена", "payload": "resident:cancel"}]
            ]
        }
    }

def main_menu_keyboard() -> dict[str, Any]:
    """
    Главное меню бота: кнопка создания новой заявки.
    """
    return {
        "type": "inline_keyboard",
        "payload": {
            "buttons": [
                [{"type": "callback", "text": "Описать проблему", "payload": "menu:problem"}]
            ]
        }
    }
