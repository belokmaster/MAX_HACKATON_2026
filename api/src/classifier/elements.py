from __future__ import annotations

from dataclasses import dataclass

from src.classifier.categories import Category, Responsibility as R


@dataclass(frozen=True)
class Element:
    key: str
    label: str
    zone: R
    reason: str | None = None  # основание, которое показывается пользователю


# Таблица «что сломалось -> чья зона». Правила лежат в данных, а не в коде:
# их проверяет юрист/УК и заменяют при переносе в другой регион.
# ВАЖНО: формулировки оснований нужно сверить с Правилами содержания общего
# имущества (Постановление Правительства РФ № 491).
ELEMENTS: dict[Category, list[Element]] = {
    Category.PLUMBING: [
        Element("faucet", "Кран / смеситель", R.RESIDENT,
                "Сантехника в квартире после первого отключающего устройства — зона собственника."),
        Element("toilet", "Унитаз / бачок", R.RESIDENT,
                "Сантехнические приборы в квартире — зона собственника."),
        Element("riser", "Стояк / общая труба", R.UK,
                "Стояки и ответвления до первого отключающего устройства — общее имущество дома."),
        Element("rad_no_valve", "Радиатор без крана перед ним", R.UK,
                "Радиатор без отключающего устройства входит в общедомовую систему отопления."),
        Element("rad_valve", "Радиатор с краном перед ним", R.RESIDENT,
                "Радиатор с отключающим устройством — оборудование собственника."),
        Element("leak_above", "Течёт сверху / от соседей", R.UNKNOWN),
        Element("burst", "Прорыв, хлещет вода", R.EMERGENCY),
    ],
    Category.ELECTRIC: [
        Element("socket", "Розетка / выключатель", R.RESIDENT,
                "Внутриквартирная электропроводка и приборы — зона собственника."),
        Element("stair_light", "Свет в подъезде / на этаже", R.UK,
                "Освещение мест общего пользования — зона УК."),
        Element("stair_panel", "Щиток в подъезде", R.UK,
                "Этажные и вводные щитки — общее имущество."),
        Element("flat_no_power", "В квартире нет света совсем", R.UNKNOWN),
        Element("sparks", "Искрит, горит проводка", R.EMERGENCY),
    ],
    Category.ELEVATOR: [
        Element("lift", "Лифт не работает", R.UK, "Лифты — общее имущество дома."),
        Element("lift_stuck", "Застрял в лифте", R.EMERGENCY),
    ],
    Category.CARPENTRY: [
        Element("intercom", "Домофон / дверь подъезда", R.UK,
                "Двери и домофон подъезда — общее имущество."),
        Element("stair_window", "Окно в подъезде", R.UK,
                "Окна в местах общего пользования — общее имущество."),
        Element("flat_door", "Дверь / окно в квартире", R.RESIDENT,
                "Заполнения проёмов квартиры — зона собственника."),
    ],
    Category.GENERAL: [
        Element("roof", "Крыша / чердак / подвал / фасад", R.UK,
                "Ограждающие и несущие конструкции — общее имущество."),
        Element("yard", "Двор / мусор / территория", R.UK,
                "Придомовая территория — зона УК."),
    ],
}


def _to_category(category):
    try:
        return Category(category)
    except ValueError:
        return None


def elements_for(category) -> list[Element]:
    cat = _to_category(category)
    return ELEMENTS.get(cat, []) if cat else []


def find_element(category, key: str) -> Element | None:
    return next((e for e in elements_for(category) if e.key == key), None)
