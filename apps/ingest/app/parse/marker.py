from __future__ import annotations

import logging
import time
from pathlib import Path

from app.parse.result import ParseResult, compute_yield_metrics

logger = logging.getLogger(__name__)

ADAPTER_ID = "marker"


def _page_count_from_rendered(rendered: object, text: str) -> int:
    metadata = getattr(rendered, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("page_count", "pages", "page_stats"):
            value = metadata.get(key)
            if isinstance(value, int) and value > 0:
                return value
            if isinstance(value, list) and value:
                return len(value)
    return 1 if text.strip() else 0


class MarkerAdapter:
    """Primary parse path: Marker / marker-pdf CPU ``fast`` mode."""

    def __init__(self, mode: str = "fast") -> None:
        self._mode = mode
        self._converter: object | None = None

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    def _get_converter(self) -> object:
        if self._converter is not None:
            return self._converter
        from marker.config.parser import ConfigParser
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict

        config_parser = ConfigParser(
            {"mode": self._mode, "output_format": "markdown"}
        )
        config_dict = config_parser.generate_config_dict()
        config_dict["mode"] = self._mode
        self._converter = PdfConverter(
            config=config_dict,
            artifact_dict=create_model_dict(),
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
            llm_service=config_parser.get_llm_service(),
        )
        return self._converter

    def parse(self, pdf_path: Path) -> ParseResult:
        started = time.perf_counter()
        try:
            from marker.output import text_from_rendered

            converter = self._get_converter()
            rendered = converter(str(pdf_path))
            text, _, _images = text_from_rendered(rendered)
            text = text or ""
            page_count = _page_count_from_rendered(rendered, text)
            mean, printable = compute_yield_metrics(text, page_count)
            wall_ms = int((time.perf_counter() - started) * 1000)
            # Empty / near-empty extract still counts as primary success (status=ok);
            # yield metrics support later gate calibration — do not silently fall back.
            return ParseResult(
                text=text,
                page_count=page_count,
                mean_chars_per_page=mean,
                printable_ratio=printable,
                wall_time_ms=wall_ms,
                adapter_id=ADAPTER_ID,
                status="ok",
            )
        except Exception as exc:
            wall_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("MarkerAdapter failed for %s", pdf_path)
            return ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=wall_ms,
                adapter_id=ADAPTER_ID,
                status="parse_failed",
                error=f"Marker failed: {exc}",
            )
