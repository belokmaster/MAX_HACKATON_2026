from __future__ import annotations

import logging

try:
    from .categories import Category, ClassifyResult, Responsibility
except ImportError:
    from categories import Category, ClassifyResult, Responsibility

logger = logging.getLogger(__name__)

DISPATCHER_MESSAGE = (
    "Не удалось автоматически определить категорию обращения. "
    "Пожалуйста, опишите проблему подробнее или свяжитесь с диспетчерской службой."
)


async def classify_with_llm(text: str, context: str = "") -> ClassifyResult:
    """Заглушка вызова LLM-классификатора, возвращающая статус UNKNOWN с рекомендацией связаться с диспетчером."""
    logger.info(
        "Вызов заглушки классификатора LLM для текста: '%s' (контекст: '%s')",
        text[:100] if text else "",
        context,
    )
    return ClassifyResult(
        category=Category.UNKNOWN,
        responsibility=Responsibility.UNKNOWN,
        confidence=0.0,
        clarification_question=DISPATCHER_MESSAGE,
    )
