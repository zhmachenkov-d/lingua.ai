from __future__ import annotations

import io
import json
from pathlib import Path

from app.cli import run_metrics_job
from app.parse.result import METRIC_JSON_KEYS, ParseResult


class FakeAdapter:
    def __init__(self, adapter_id: str, mapping: dict[str, ParseResult]) -> None:
        self._adapter_id = adapter_id
        self.mapping = mapping

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    def parse(self, pdf_path: Path) -> ParseResult:
        return self.mapping[pdf_path.name]


def test_json_key_contract_and_adapter_selection(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    (textbooks / "a.pdf").write_bytes(b"%PDF")
    (textbooks / "b.pdf").write_bytes(b"%PDF")

    primary = FakeAdapter(
        "marker",
        {
            "a.pdf": ParseResult(
                text="aaa",
                page_count=1,
                mean_chars_per_page=3.0,
                printable_ratio=1.0,
                wall_time_ms=10,
                adapter_id="marker",
                status="ok",
            ),
            "b.pdf": ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=20,
                adapter_id="marker",
                status="parse_failed",
                error="Marker boom",
            ),
        },
    )
    fallback = FakeAdapter(
        "pymupdf_text",
        {
            "b.pdf": ParseResult(
                text="layer",
                page_count=2,
                mean_chars_per_page=2.5,
                printable_ratio=1.0,
                wall_time_ms=5,
                adapter_id="pymupdf_text",
                status="ok",
            ),
        },
    )

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_metrics_job(
        textbooks=textbooks,
        pdf_names=("a.pdf", "b.pdf"),
        primary=primary,
        fallback=fallback,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 2
    payloads = [json.loads(ln) for ln in lines]
    for payload in payloads:
        assert set(payload) >= set(METRIC_JSON_KEYS)
        for key in METRIC_JSON_KEYS:
            assert key in payload
    assert payloads[0]["status"] == "ok"
    assert payloads[0]["adapter_id"] == "marker"
    assert payloads[1]["status"] == "fallback"
    assert payloads[1]["adapter_id"] == "pymupdf_text"
    assert isinstance(payloads[0]["peak_rss_bytes"], int)
    assert payloads[0]["peak_rss_bytes"] > 0


def test_missing_pdf_fail_fast_no_fabricated_json(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    (textbooks / "present.pdf").write_bytes(b"%PDF")

    primary = FakeAdapter(
        "marker",
        {
            "present.pdf": ParseResult(
                text="ok",
                page_count=1,
                mean_chars_per_page=2.0,
                printable_ratio=1.0,
                wall_time_ms=1,
                adapter_id="marker",
                status="ok",
            ),
        },
    )
    fallback = FakeAdapter("pymupdf_text", {})

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_metrics_job(
        textbooks=textbooks,
        pdf_names=("present.pdf", "missing.pdf"),
        primary=primary,
        fallback=fallback,
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 1
    assert stdout.getvalue().strip() == ""
    err = stderr.getvalue()
    assert "missing.pdf" in err
    assert "missing required PDF" in err


def test_parse_failed_status_when_both_fail(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    (textbooks / "bad.pdf").write_bytes(b"%PDF")

    primary = FakeAdapter(
        "marker",
        {
            "bad.pdf": ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=1,
                adapter_id="marker",
                status="parse_failed",
                error="Marker boom",
            ),
        },
    )
    fallback = FakeAdapter(
        "pymupdf_text",
        {
            "bad.pdf": ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=1,
                adapter_id="pymupdf_text",
                status="parse_failed",
                error="empty",
            ),
        },
    )

    stdout = io.StringIO()
    code = run_metrics_job(
        textbooks=textbooks,
        pdf_names=("bad.pdf",),
        primary=primary,
        fallback=fallback,
        stdout=stdout,
        stderr=io.StringIO(),
    )

    assert code == 0
    payload = json.loads(stdout.getvalue().strip())
    assert payload["status"] == "parse_failed"
    assert set(METRIC_JSON_KEYS) <= set(payload)
