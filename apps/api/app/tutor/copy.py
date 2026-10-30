"""EXPERIENCE-aligned RU strings for Tutor gate / refuse paths."""

from typing import Final

CEFR_MISSING: Final = "Укажи общий уровень CEFR, чтобы начать Ready Tutor."
NO_READY: Final = (
    "Tutor не может начать: нет Ready unit Students' Book. "
    "Подожди ingest или выбери агента."
)
EMPTY_RAG: Final = "Этот unit сейчас нельзя вести. Выбери другой Ready unit или агента."
WORKBOOK_ONLY: Final = (
    "Workbook не Ready для Tutor. Выбери Ready unit Students' Book или агента."
)
NULL_UNIT: Final = "Unit не выбран. Выбери Ready unit Students' Book."
READY_LOSS: Final = (
    "Unit больше не Ready. Остановились. Выбери другой unit или агента."
)
OFF_UNIT: Final = (
    "Этот запрос не про текущий unit. Вернись к unit или выбери агента."
)
SESSION_PERSIST_FAIL: Final = (
    "Не удалось сохранить ход. Остаёмся в сессии — повтори или отмени переход."
)
UNIT_CHANGE_CONFIRM: Final = "Сменить unit? Текущий ход Tutor будет завершён."
