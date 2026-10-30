"""Shared CEFR mixin — gate read + band policy (§7.5 Always rules)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.mixins.cefr import (
    CEFR_LADDER,
    format_band_annotation,
    read_overall_cefr,
    resolve_target_band,
)
from app.schemas.cefr import CefrLevel
from hypothesis import given
from hypothesis import strategies as st

_LEVELS = st.sampled_from(list(CEFR_LADDER))


@given(overall=_LEVELS)
def test_band_ceiling_is_overall_or_plus_one_never_plus_two(overall: CefrLevel) -> None:
    band = resolve_target_band(overall)
    assert band is not None
    assert band.overall == overall
    idx = CEFR_LADDER.index(overall)
    expected_ceiling = CEFR_LADDER[min(idx + 1, len(CEFR_LADDER) - 1)]
    assert band.ceiling == expected_ceiling
    # Never +2: ceiling index - overall index is in {0, 1}.
    assert CEFR_LADDER.index(band.ceiling) - idx in (0, 1)


@given(
    junk=st.one_of(
        st.none(),
        st.just(""),
        st.just("  "),
        st.just("A3"),
        st.just("Z9"),
    )
)
def test_invalid_overall_yields_undefined_band(junk: str | None) -> None:
    assert resolve_target_band(junk) is None  # type: ignore[arg-type]


def test_c2_ceiling_stays_c2() -> None:
    band = resolve_target_band("C2")
    assert band is not None
    assert band.overall == "C2"
    assert band.ceiling == "C2"
    assert format_band_annotation(band) == "[CEFR target: C2]"


def test_a2_annotation_shows_overall_to_ceiling() -> None:
    band = resolve_target_band("A2")
    assert band is not None
    assert format_band_annotation(band) == "[CEFR target: A2–B1]"


def test_read_overall_cefr_missing_profile() -> None:
    async def _run() -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        assert await read_overall_cefr(session) is None

    asyncio.run(_run())


def test_read_overall_cefr_empty_and_invalid() -> None:
    async def _run() -> None:
        session = AsyncMock()

        empty = MagicMock()
        empty.cefr_by_skill = {}
        session.get = AsyncMock(return_value=empty)
        assert await read_overall_cefr(session) is None

        invalid = MagicMock()
        invalid.cefr_by_skill = {"overall": "Z9"}
        session.get = AsyncMock(return_value=invalid)
        assert await read_overall_cefr(session) is None

        whitespace_overall = MagicMock()
        whitespace_overall.cefr_by_skill = {"overall": "  "}
        session.get = AsyncMock(return_value=whitespace_overall)
        assert await read_overall_cefr(session) is None

    asyncio.run(_run())


def test_read_overall_cefr_valid_ignores_by_skill() -> None:
    async def _run() -> None:
        session = AsyncMock()
        profile = MagicMock()
        profile.cefr_by_skill = {"overall": "B1", "reading": "C2", "speaking": "A1"}
        session.get = AsyncMock(return_value=profile)
        assert await read_overall_cefr(session) == "B1"

    asyncio.run(_run())
