from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ingest.parse.types import ParsePath

OPENRAIL_M_BLURB = (
    "Marker **code** is Apache-2.0; **model weights** use a modified AI Pubs "
    "OpenRAIL-M license (field-of-use): free for research, personal use, and "
    "startups under $5M funding/revenue. Commercial use of weights beyond that "
    "requires a Datalab commercial arrangement. Review the full terms before any "
    "non-personal deploy: "
    "https://github.com/datalab-to/marker/blob/master/MODEL_LICENSE"
)


@dataclass(frozen=True)
class PdfSpikeRow:
    pdf_name: str
    path: ParsePath
    peak_rss_mb: float | None
    mean_chars_per_page: float | None
    printable_ratio: float | None
    error: str | None = None


def render_spike_note(
    *,
    spike_date: date,
    job_peak_rss_mb: float,
    rows: list[PdfSpikeRow],
    install_notes: str | None = None,
) -> str:
    lines = [
        f"# Marker Compose CPU spike — {spike_date.isoformat()}",
        "",
        "## OpenRAIL-M",
        "",
        OPENRAIL_M_BLURB,
        "",
        "## Metrics",
        "",
        (
            "Job peak RSS (max observed, cgroup/process-tree): "
            f"**{job_peak_rss_mb:.1f} MiB**"
        ),
        "",
        "| PDF | path | peak_rss_mb | mean_chars_per_page | printable_ratio | notes |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        peak = (
            f"{row.peak_rss_mb:.1f}" if row.peak_rss_mb is not None else "—"
        )
        mean = (
            f"{row.mean_chars_per_page:.1f}"
            if row.mean_chars_per_page is not None
            else "—"
        )
        ratio = (
            f"{row.printable_ratio:.4f}"
            if row.printable_ratio is not None
            else "—"
        )
        notes = ""
        if row.error:
            notes = " ".join(row.error.split()).replace("|", "\\|")
        lines.append(
            f"| {row.pdf_name} | `{row.path}` | {peak} | {mean} | {ratio} | {notes} |"
        )
    lines.extend(
        (
            "",
            "## Go / no-go",
            "",
            "- [ ] go / no-go — owner after confirming peak RSS",
            "",
        )
    )
    if install_notes:
        lines.extend(
            (
                "## Install / run notes",
                "",
                install_notes,
                "",
            )
        )
    return "\n".join(lines)


def write_spike_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
