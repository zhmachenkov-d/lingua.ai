from __future__ import annotations

import logging
from pathlib import Path

from ingest.parse.types import ParseResult

logger = logging.getLogger(__name__)


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
        self._converter = None

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
        try:
            from marker.output import text_from_rendered

            converter = self._get_converter()
            rendered = converter(str(pdf_path))
            text, _, _images = text_from_rendered(rendered)
            text = text or ""
            if not text.strip():
                return ParseResult(
                    text="",
                    path="failed",
                    page_count=_page_count_from_rendered(rendered, text),
                    error="Marker returned empty text",
                )
            return ParseResult(
                text=text,
                path="marker",
                page_count=_page_count_from_rendered(rendered, text),
            )
        except Exception as exc:
            logger.exception("MarkerAdapter failed for %s", pdf_path)
            return ParseResult(
                text="",
                path="failed",
                page_count=0,
                error=f"Marker failed: {exc}",
            )
