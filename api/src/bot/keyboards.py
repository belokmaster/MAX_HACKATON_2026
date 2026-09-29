from typing import Any

def clarification_zone_keyboard(category: str) -> dict[str, Any]:
    """
    Клавиатура для уточнения зоны ответственности.
    Место неисправности не определяет ответственность: общедомовые системы
    могут проходить внутри квартиры.
    """
    return {
        "type": "inline_keyboard",
        "payload": {
            "buttons": [
                [
                    {
                        "type": "callback",
                        "text": "Общедомовая система (УК)",
                        "payload": "clarify:zone:uk",
                    }
                ],
                [
                    {
                        "type": "callback",
                        "text": "Личное оборудование (жилец)",
                        "payload": "clarify:zone:resident",
                    }
                ],
                [
                    {
                        "type": "callback",
                        "text": "Авария / срочно",
                        "payload": "clarify:zone:emergency",
                    }
                ],
            ]
        }
    }

def shift_windows_keyboard(windows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Клавиатура для выбора смены мастера.
    Каждая доступная смена выводится отдельной строкой. Если свободных смен
    нет, пользователь может передать заявку диспетчеру без выбора времени.
    Последняя кнопка — Отмена.
    """
    buttons = []
    for window in windows[:6]:
        buttons.append([
            {"type": "callback", "text": window["label"], "payload": f"book:{window['window_id']}"}
        ])

    if not windows:
        buttons.append([
            {
                "type": "callback",
                "text": "Вызвать мастера",
                "payload": "book:dispatcher",
            }
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
