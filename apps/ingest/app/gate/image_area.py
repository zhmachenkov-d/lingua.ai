from __future__ import annotations

from pathlib import Path


def image_area_ratio(
    pdf_path: Path | str,
    page_start: int,
    page_end: int,
) -> float:
    """Mean-of-pages clipped raster image bbox area / page area for a span.

    Per page: sum of raster image bbox areas clipped to the page rect, divided
    by page area (sum, not union). Drawings/vectors are ignored. Mean is over
    the full page span; pages outside the document count as 0.0. Empty span
    (page_end < page_start) yields 0.0.
    """
    import pymupdf

    path = Path(pdf_path)
    doc = pymupdf.open(path)
    try:
        if page_end < page_start:
            return 0.0
        ratios: list[float] = []
        last = len(doc) - 1
        for page_no in range(page_start, page_end + 1):
            if page_no < 0 or page_no > last:
                # Still count toward the span mean (missing page → 0.0).
                ratios.append(0.0)
                continue
            page = doc[page_no]
            page_rect = page.rect
            page_area = abs(page_rect.width * page_rect.height)
            if page_area <= 0:
                ratios.append(0.0)
                continue
            total = 0.0
            for info in page.get_image_info(hashes=False, xrefs=True):
                bbox = pymupdf.Rect(info["bbox"])
                clipped = bbox & page_rect
                if clipped.is_empty:
                    continue
                total += abs(clipped.width * clipped.height)
            ratios.append(total / page_area)
        return sum(ratios) / len(ratios)
    finally:
        doc.close()
