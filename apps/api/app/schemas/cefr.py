"""CEFR map validation for the api profile write path (FR-7 / AD-4).

Closed level set and allowed keys only. Invalid tokens and unknown keys are
rejected (422) and never stored. Omit or null ``overall`` clears it so empty
overall stays detectable for later Tutor gating.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

CefrLevel = Literal["A1", "A2", "B1", "B2", "C1", "C2"]


class CefrBySkill(BaseModel):
    """Bare CEFR map: ``overall`` plus optional skills / ``vocab``."""

    model_config = ConfigDict(extra="forbid")

    overall: CefrLevel | None = None
    reading: CefrLevel | None = None
    listening: CefrLevel | None = None
    speaking: CefrLevel | None = None
    writing: CefrLevel | None = None
    vocab: CefrLevel | None = None

    def to_stored_map(self) -> dict[str, str]:
        """Full-replace payload: null/omitted keys are absent (not stored as null)."""
        return self.model_dump(exclude_none=True)
