from __future__ import annotations

from dataclasses import dataclass
import re

STOPWORDS: set[str] = {"д", "дом", "ул", "улица", "пр", "проспект", "пер", "переулок"}


@dataclass
class UKInfo:
    uk_id: str
    uk_name: str
    uk_phone: str
    emergency_phone: str
    address: str


HOUSING_REGISTRY: list[UKInfo] = [
    # uk_01: УК Комфорт
    UKInfo(
        uk_id="uk_01",
        uk_name="УК Комфорт",
        uk_phone="+7 495 111-22-33",
        emergency_phone="+7 495 000-11-01",
        address="ул. Пушкина, д. 10",
    ),
    UKInfo(
        uk_id="uk_01",
        uk_name="УК Комфорт",
        uk_phone="+7 495 111-22-33",
        emergency_phone="+7 495 000-11-01",
        address="ул. Пушкина, д. 12",
    ),
    UKInfo(
        uk_id="uk_01",
        uk_name="УК Комфорт",
        uk_phone="+7 495 111-22-33",
        emergency_phone="+7 495 000-11-01",
        address="пр. Садовый, д. 3",
    ),
    UKInfo(
        uk_id="uk_01",
        uk_name="УК Комфорт",
        uk_phone="+7 495 111-22-33",
        emergency_phone="+7 495 000-11-01",
        address="пер. Кузнецкий, д. 7",
    ),
    # uk_02: УК Уют
    UKInfo(
        uk_id="uk_02",
        uk_name="УК Уют",
        uk_phone="+7 495 222-33-44",
        emergency_phone="+7 495 000-22-02",
        address="пр. Ленина, д. 5",
    ),
    UKInfo(
        uk_id="uk_02",
        uk_name="УК Уют",
        uk_phone="+7 495 222-33-44",
        emergency_phone="+7 495 000-22-02",
        address="пр. Ленина, д. 8",
    ),
    UKInfo(
        uk_id="uk_02",
        uk_name="УК Уют",
        uk_phone="+7 495 222-33-44",
        emergency_phone="+7 495 000-22-02",
        address="ул. Советская, д. 15",
    ),
]


def _normalize(text: str) -> str:
    """Нормализация строки адреса: нижний регистр, очистка пунктуации и пробелов."""
    text = text.lower().strip()
    text = re.sub(r"[.,\-]", " ", text)
    return " ".join(text.split())


def find_uk(query: str) -> list[UKInfo]:
    """
    Нечеткий поиск обслуживающей управляющей компании по адресу дома.
    Оценка совпадения строится по пересечению значимых слов.
    Возвращает до 3 наиболее подходящих адресов.
    """
    norm_query = _normalize(query)
    query_words = set(norm_query.split())
    if not query_words:
        return []

    scored: list[tuple[int, UKInfo]] = []
    for entry in HOUSING_REGISTRY:
        canonical_words = [
            w for w in _normalize(entry.address).split()
            if w not in STOPWORDS
        ]
        score = sum(1 for w in canonical_words if w in query_words)
        if score > 0:
            scored.append((score, entry))

    # Сортировка по убыванию релевантности
    scored.sort(key=lambda x: x[0], reverse=True)

    # Дедупликация по адресу с лимитом в 3 результата
    results: list[UKInfo] = []
    seen_addresses: set[str] = set()
    for _, entry in scored:
        if entry.address not in seen_addresses:
            seen_addresses.add(entry.address)
            results.append(entry)
            if len(results) == 3:
                break

    return results


def get_uk_by_id(uk_id: str) -> UKInfo | None:
    """Получение информации об управляющей компании по её идентификатору."""
    for entry in HOUSING_REGISTRY:
        if entry.uk_id == uk_id:
            return entry
    return None
