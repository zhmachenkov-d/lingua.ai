from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UnitSpan:
    """Zero-based inclusive page span for one mintable unit_ref."""

    textbook_id: str
    code: str
    title: str
    page_start: int
    page_end: int

    @property
    def unit_ref(self) -> str:
        return f"{self.textbook_id}/{self.code}"

    @property
    def page_count(self) -> int:
        return self.page_end - self.page_start + 1
