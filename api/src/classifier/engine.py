from __future__ import annotations

import logging

try:
    from .categories import Category, ClassifyResult, Responsibility
    from .llm import classify_with_llm
    from .stub import classify as stub_classify
except ImportError:
    from categories import Category, ClassifyResult, Responsibility
    from llm import classify_with_llm
    from stub import classify as stub_classify

logger = logging.getLogger(__name__)


async def classify(text: str, context: str = "") -> ClassifyResult:
    """Классификация текста обращения с помощью базового алгоритма и fallback на LLM при уверенности < 0.3."""
    result = stub_classify(text)

    if result.confidence < 0.3:
        logger.info(
            "Низкая уверенность (%.2f < 0.3) базового классификатора, обращение к LLM",
            result.confidence,
        )
        return await classify_with_llm(text, context=context)

    return result
