from __future__ import annotations

import re

try:
    from .categories import Category, ClassifyResult, Responsibility
except ImportError:
    from categories import Category, ClassifyResult, Responsibility


EMERGENCY_KEYWORDS: list[str] = [
    "прорвало",
    "хлещет",
    "затопило",
    "газ",
    "запах газа",
    "искрит кабель",
    "горит проводка",
    "пожар",
    "дым",
    "замыкание",
    "угарный",
]

ELECTRIC_KEYWORDS: list[str] = [
    "свет",
    "электрика",
    "электричество",
    "розетка",
    "выключатель",
    "счётчик",
    "провод",
    "щиток",
    "лампочка",
    "обесточен",
    "напряжение",
    "пробки",
    "автомат",
]

PLUMBING_KEYWORDS: list[str] = [
    "вода",
    "труба",
    "течёт",
    "течет",
    "протечка",
    "кран",
    "смеситель",
    "унитаз",
    "батарея",
    "радиатор",
    "отопление",
    "горячая вода",
    "засор",
    "канализация",
    "стояк",
]

ELEVATOR_KEYWORDS: list[str] = [
    "лифт",
    "подъемник",
]

CARPENTRY_KEYWORDS: list[str] = [
    "дверь",
    "замок",
    "домофон",
    "ручка двери",
    "петли",
]

GENERAL_KEYWORDS: list[str] = [
    "крыша",
    "подвал",
    "козырек",
    "фасад",
    "лестница",
    "перила",
    "мусоропровод",
    "подъезд",
    "парадная",
]

UK_INDICATORS: list[str] = [
    "подъезд",
    "парадная",
    "подвал",
    "крыша",
    "стояк",
    "общедомовой",
    "в доме",
    "во дворе",
    "лестничная",
    "общий щиток",
    "этаж",
]

RESIDENT_INDICATORS: list[str] = [
    "в квартире",
    "у меня дома",
    "на кухне",
    "в ванной",
    "в туалете",
    "в комнате",
    "в спальне",
    "в коридоре",
]

CATEGORY_KEYWORD_MAP: dict[Category, list[str]] = {
    Category.ELECTRIC: ELECTRIC_KEYWORDS,
    Category.PLUMBING: PLUMBING_KEYWORDS,
    Category.ELEVATOR: ELEVATOR_KEYWORDS,
    Category.CARPENTRY: CARPENTRY_KEYWORDS,
    Category.GENERAL: GENERAL_KEYWORDS,
}


def _match_single_word(text_e: str, word: str) -> bool:
    """Сопоставление основы отдельного слова по границе слова."""
    stem = word
    for ending in (
        "ая", "ое", "ий", "ый", "ые", "ие", "ка", "ки", "ку", "ке",
        "ой", "ей", "ем", "ом", "а", "я", "о", "е", "у", "ю", "ы", "и", "ь",
    ):
        if stem.endswith(ending) and len(stem) - len(ending) >= 3:
            stem = stem[:-len(ending)]
            break
    pattern = r"(?:\b|^|\s)" + re.escape(stem)
    return bool(re.search(pattern, text_e))


def _match_keyword(text_norm: str, keyword: str) -> bool:
    """Сопоставление ключевого слова или фразы с нормализованным текстом.
    Учитывает основы русских слов и предотвращает ложные срабатывания.
    """
    text_e = text_norm.replace("ё", "е")
    kw_e = keyword.lower().strip().replace("ё", "е")

    if not kw_e or not text_e:
        return False

    # Проверка точного вхождения подстроки по границе слова
    if kw_e in text_e:
        idx = 0
        while True:
            idx = text_e.find(kw_e, idx)
            if idx == -1:
                break
            is_start_boundary = (idx == 0 or not text_e[idx - 1].isalnum())
            if is_start_boundary:
                return True
            idx += 1

    # Проверка многословных фраз или отдельных основ слов
    words = kw_e.split()
    if len(words) > 1:
        return all(_match_single_word(text_e, w) for w in words)
    else:
        return _match_single_word(text_e, words[0])


def classify(text: str) -> ClassifyResult:
    """Классификация текста обращения с помощью правил ключевых слов."""
    # 1. Нормализация текста: нижний регистр, очистка пробелов
    text_norm = (text or "").lower().strip()
    if not text_norm:
        return ClassifyResult(
            category=Category.UNKNOWN,
            responsibility=Responsibility.UNKNOWN,
            confidence=0.0,
            clarification_question="Уточните: неисправность в подъезде (общедомовое) или в вашей квартире?",
        )

    # 2. Проверка на аварийную ситуацию (наивысший приоритет)
    is_emergency = any(_match_keyword(text_norm, kw) for kw in EMERGENCY_KEYWORDS)

    # 3. Определение категории по наборам ключевых слов
    category_scores: dict[Category, int] = {}
    for cat, kws in CATEGORY_KEYWORD_MAP.items():
        score = sum(1 for kw in kws if _match_keyword(text_norm, kw))
        if score > 0:
            category_scores[cat] = score

    # Определение категории с учетом приоритета специального оборудования над общими фразами
    priority_order = [
        Category.ELECTRIC,
        Category.PLUMBING,
        Category.ELEVATOR,
        Category.CARPENTRY,
        Category.GENERAL,
    ]

    selected_category = Category.UNKNOWN
    if category_scores:
        # Сортировка по количеству совпадений (по убыванию) и приоритету
        sorted_cats = sorted(
            category_scores.keys(),
            key=lambda c: (-category_scores[c], priority_order.index(c) if c in priority_order else 99),
        )
        selected_category = sorted_cats[0]
    elif is_emergency:
        # Определение категории для аварий при отсутствии явных ключевых слов
        if any(_match_keyword(text_norm, kw) for kw in ["прорвало", "хлещет", "затопило"]):
            selected_category = Category.PLUMBING
        elif any(_match_keyword(text_norm, kw) for kw in ["искрит кабель", "горит проводка", "замыкание"]):
            selected_category = Category.ELECTRIC

    # 4. Определение зоны ответственности (УК / Жилец / Авария)
    if is_emergency:
        responsibility = Responsibility.EMERGENCY
    else:
        # Специальные правила зон ответственности
        special_resp: Responsibility | None = None

        if selected_category == Category.ELEVATOR:
            special_resp = Responsibility.UK
        elif selected_category == Category.CARPENTRY and _match_keyword(text_norm, "домофон"):
            special_resp = Responsibility.UK
        elif selected_category == Category.PLUMBING and _match_keyword(text_norm, "стояк"):
            special_resp = Responsibility.UK
        elif selected_category == Category.PLUMBING and any(
            _match_keyword(text_norm, kw) for kw in ["смеситель", "кран", "унитаз"]
        ):
            special_resp = Responsibility.RESIDENT
        elif selected_category == Category.ELECTRIC and (
            _match_keyword(text_norm, "щиток подъезда")
            or _match_keyword(text_norm, "общий щиток")
            or (
                _match_keyword(text_norm, "щиток")
                and (_match_keyword(text_norm, "подъезд") or _match_keyword(text_norm, "парадная"))
            )
        ):
            special_resp = Responsibility.UK
        elif selected_category == Category.ELECTRIC and any(
            _match_keyword(text_norm, kw) for kw in ["розетка", "в квартире"]
        ):
            special_resp = Responsibility.RESIDENT

        if special_resp is not None:
            responsibility = special_resp
        else:
            # Определение по индикаторам местоположения
            has_uk = any(_match_keyword(text_norm, kw) for kw in UK_INDICATORS)
            has_resident = any(_match_keyword(text_norm, kw) for kw in RESIDENT_INDICATORS)

            if has_uk and not has_resident:
                responsibility = Responsibility.UK
            elif has_resident and not has_uk:
                responsibility = Responsibility.RESIDENT
            else:
                responsibility = Responsibility.UNKNOWN

    # 5. Уточняющий вопрос при неизвестной зоне ответственности
    clarification_question: str | None = None
    if responsibility == Responsibility.UNKNOWN:
        if selected_category == Category.ELECTRIC:
            clarification_question = "Уточните: неисправность в подъезде или в вашей квартире?"
        elif selected_category == Category.PLUMBING:
            clarification_question = "Уточните: это общедомовой стояк или трубы/краны внутри квартиры?"
        else:
            clarification_question = "Уточните: неисправность в подъезде (общедомовое) или в вашей квартире?"

    # 6. Оценка уверенности: 1.0 если зона определена, 0.5 если требуется уточнение
    if responsibility == Responsibility.EMERGENCY:
        confidence = 1.0
    elif selected_category == Category.UNKNOWN:
        confidence = 0.0
    elif responsibility == Responsibility.UNKNOWN:
        confidence = 0.5
    else:
        confidence = 1.0

    return ClassifyResult(
        category=selected_category,
        responsibility=responsibility,
        confidence=confidence,
        clarification_question=clarification_question,
    )
