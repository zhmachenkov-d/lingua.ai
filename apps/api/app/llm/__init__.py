"""In-process DeepSeek LLM adapter (AD-8)."""

from app.llm.adapter import (
    BACKUP_NOTICE,
    ClassifyResult,
    LlmMisconfigured,
    LlmUnavailable,
    classify_turn,
)

__all__ = [
    "BACKUP_NOTICE",
    "ClassifyResult",
    "LlmMisconfigured",
    "LlmUnavailable",
    "classify_turn",
]
