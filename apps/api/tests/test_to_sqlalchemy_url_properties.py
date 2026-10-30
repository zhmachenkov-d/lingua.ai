"""Property-based checks for ``to_sqlalchemy_url`` (pure URL prefix rewrite)."""

from __future__ import annotations

from app.db.config import to_sqlalchemy_url
from hypothesis import given
from hypothesis import strategies as st

_DRIVER = "postgresql+psycopg://"


@given(
    rest=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        max_size=80,
    )
)
def test_postgresql_prefix_rewrites_to_psycopg_driver(rest: str) -> None:
    url = "postgresql://" + rest
    assert to_sqlalchemy_url(url) == _DRIVER + rest


@given(
    rest=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        max_size=80,
    )
)
def test_postgres_prefix_rewrites_to_psycopg_driver(rest: str) -> None:
    url = "postgres://" + rest
    assert to_sqlalchemy_url(url) == _DRIVER + rest


@given(
    url=st.text(min_size=1, max_size=120).filter(
        lambda u: not u.startswith(("postgresql://", "postgres://"))
    )
)
def test_other_schemes_unchanged(url: str) -> None:
    assert to_sqlalchemy_url(url) == url
