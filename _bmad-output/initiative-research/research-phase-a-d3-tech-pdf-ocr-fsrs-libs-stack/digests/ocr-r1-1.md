# Digest: ocr round 1

**Research firewall:** web primary sources only this run. WebSearch tool calls failed (approval prompt); evidence is from WebFetch of official docs / GitHub releases / PyPI / vendor pricing. Accessed **2026-10-21**.

**Decision context (constraints, not evidence):** English textbook PDFs with scanned pages; Python 3.13 + Docker Compose solo backend; refuse bad scans with Poor-quality status; OCR language English.

---

## Findings (claims)

### Hard-gate / landscape screening

- claim: OCRmyPDF is designed to add an OCR text layer to **scanned** PDFs; ships a **Docker image**; exposes a Python API (`ocrmypdf.ocr` / `OcrOptions`, v17+); languages selectable (e.g. `languages=['eng']`).
- source: https://ocrmypdf.readthedocs.io/en/latest/ ; https://ocrmypdf.readthedocs.io/en/latest/api.html
- publisher: OCRmyPDF documentation (jbarlow83)
- pub_date: living
- accessed: 2026-10-21
- confidence: high
- class: ops | version | landscape

- claim: OCRmyPDF can preprocess scans (deskew, `unpaper` clean, timeouts, skip oversized images) but **cannot rebuild PDF structure trees** to match newly recognized text; forced OCR discards logical structure — weak as a **layout-recovery** primary for multi-column textbooks.
- source: https://ocrmypdf.readthedocs.io/en/latest/advanced.html
- publisher: OCRmyPDF documentation
- pub_date: living
- accessed: 2026-10-21
- confidence: high
- class: performance | ops

- claim: OCRmyPDF public API includes an `ocrmypdf.quality` module (API reference lists it); page content for quality heuristics was not successfully retrieved this run (dedicated quality.html 404).
- source: https://ocrmypdf.readthedocs.io/en/latest/apiref.html
- publisher: OCRmyPDF documentation
- pub_date: living
- accessed: 2026-10-21
- confidence: medium
- class: ops

- claim: **Marker 2.0.0** (package `marker-pdf`) converts PDFs to markdown/JSON; uses Surya OCR for garbled/scanned pages; modes `balanced` / `fast` / disable-OCR; pip-installable; Python `>=3.10,<4`; PyPI license field **Apache-2.0**; depends on `surya-ocr`, `torch`.
- source: https://pypi.org/project/marker-pdf/ ; https://github.com/datalab-to/marker/releases
- publisher: Datalab / Vik Paruchuri (PyPI + GitHub)
- pub_date: 2025-07 (GitHub release “20 Jul”; year not printed on page — treat as ≤12 mo landscape, **not** ≤1 mo version-fresh)
- accessed: 2026-10-21
- confidence: high
- class: version | landscape | license

- claim: Marker 2.0 reports **olmOCR-bench** scores: balanced 76.0% overall (83.5% digital-only), fast 66.6%, fast no-OCR 43.6%; throughput on one B200: 2.9 / 7.4 / 23.7 pg/s respectively; `fast --disable_ocr` is full CPU; device-aware default (balanced on GPU, fast on CPU/MPS). Same numbers appear on GitHub release notes and PyPI long description (two-source for performance cells).
- source: https://github.com/datalab-to/marker/releases ; https://pypi.org/project/marker-pdf/
- publisher: Datalab
- pub_date: 2025-07 (release notes)
- accessed: 2026-10-21
- confidence: medium
- class: performance
- note: Vendor self-reported bench; no independent third-party production retrospective retrieved this run.

- claim: Marker limitations include very complex layouts (nested tables/forms); `--use_llm` / `--force_ocr` flagged as mitigations; optional hosted Datalab API / on-prem commercial offering.
- source: https://pypi.org/project/marker-pdf/
- publisher: Datalab (PyPI README)
- pub_date: living (package page)
- accessed: 2026-10-21
- confidence: high
- class: performance | pricing | lock-in

- claim: GitHub Marker release **v1.8.5** notes an **OpenRAIL** license change (historical); conflicts with current PyPI `Apache-2.0` metadata — license diligence required before commercial use.
- source: https://github.com/datalab-to/marker/releases (v1.8.5 notes)
- publisher: Datalab
- pub_date: 2025-08 (release list relative order)
- accessed: 2026-10-21
- confidence: medium
- class: license

- claim: **docTR** (Mindee) is a PyTorch OCR toolkit with detection+recognition predictors, a **layout analysis** predictor (tables, figures, headers, …), CPU & GPU inference, and claims performance comparable to Google Vision / AWS Textract on public datasets (vendor claim).
- source: https://mindee.github.io/doctr/
- publisher: Mindee
- pub_date: living
- accessed: 2026-10-21
- confidence: medium
- class: landscape | performance

- claim: **LlamaParse / LlamaCloud Parse** is a hosted, layout-aware document parser for PDFs including **scanned pages**, multi-column layouts, tables/charts; Python SDK (`llama-cloud`); tiers Agentic Plus / Agentic / Cost Effective / Fast; OCR language configurable (e.g. `en`); Fast tier returns text/spatial only (no markdown).
- source: https://developers.llamaindex.ai/python/cloud/llamaparse/ ; https://developers.llamaindex.ai/python/cloud/llamaparse/getting_started/
- publisher: LlamaIndex
- pub_date: living
- accessed: 2026-10-21
- confidence: high
- class: landscape | ops | pricing

- claim: LlamaParse pricing page URL attempted (`.../llamaparse/pricing/`) returned **404** this run; docs link “Pricing & credits” but dollar amounts not retrieved — treat cloud $ as **unverified** beyond free-credit mentions elsewhere in ecosystem.
- source: https://developers.llamaindex.ai/python/cloud/llamaparse/getting_started/ (resources link only)
- publisher: LlamaIndex
- pub_date: living
- accessed: 2026-10-21
- confidence: low
- class: pricing

- claim: **Google Document AI** Enterprise Document OCR: first 1,000 pages/month free, then **$1.50 / 1,000 pages** (up to 5M), then **$0.60 / 1,000**; Layout Parser **$10.00 / 1,000 pages** (list prices USD on pricing page).
- source: https://cloud.google.com/document-ai/pricing
- publisher: Google Cloud
- pub_date: living
- accessed: 2026-10-21
- confidence: high
- class: pricing

- claim: **Azure Document Intelligence** offers Read / Layout / Prebuilt / Custom; Free tier **0–500 pages/month**; pay-as-you-go and container options; pricing table on page uses placeholder `$` (amounts not readable in fetch) — exact $/1k pages **unverified** this run; neural custom training overage cited as **$3/hour** after 10 free hours.
- source: https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/
- publisher: Microsoft Azure
- pub_date: living
- accessed: 2026-10-21
- confidence: medium (capability high; dollar amounts low)
- class: pricing | ops

- claim: PaddleOCR GitHub describes PDF/image → structured data OCR toolkit, 100+ languages; fetch returned near-empty README body (stars/forks zeroed by scraper) — **insufficient primary text** this run for version, license, or layout claims beyond the tagline.
- source: https://github.com/PaddlePaddle/PaddleOCR
- publisher: PaddlePaddle
- pub_date: living
- accessed: 2026-10-21
- confidence: low
- class: landscape

### Cuts (hard gates)

- claim: **pdfplumber / PyMuPDF** (hypothesis) are born-digital text extractors; they fail the hard gate “works on scans not only born-digital text” as a primary OCR path. Not fetched this run — cut as **hypothesis fail**, not evidenced failure.
- source: n/a (not retrieved)
- publisher: n/a
- pub_date: n/a
- accessed: 2026-10-21
- confidence: low
- class: landscape
- note: Unverified belief from screening brief; omit as positive claim.

- claim: **EasyOCR**, **unstructured**, **AWS Textract**, standalone **pytesseract** (without ocrmypdf wrapper) were **not successfully evidenced** this run (WebSearch blocked; no primary fetch). Treat as **unscreened / omit from finalists**, not as rejected-with-evidence.
- source: n/a
- publisher: n/a
- pub_date: n/a
- accessed: 2026-10-21
- confidence: low
- class: landscape

### Quality-gate product requirement

- claim: None of the retrieved primaries document a turnkey **“Poor-quality” reject status** matching the product need. Closest evidenced controls: OCRmyPDF image preprocess / timeouts / skip-big; Marker selective OCR when text layer is “garbled”; cloud parsers may fail jobs but thresholds for blur/skew reject are **not documented** in fetched pages. Solo stack must implement a **custom quality gate** (e.g. image metrics + OCR confidence threshold) upstream of ingest.
- source: synthesis of https://ocrmypdf.readthedocs.io/en/latest/advanced.html ; https://pypi.org/project/marker-pdf/ ; LlamaParse / cloud docs above
- publisher: multiple
- pub_date: living
- accessed: 2026-10-21
- confidence: medium
- class: ops

---

## Select matrix (brief)

| Candidate | Acc. textbook layouts | Layout/structure | EN | Local vs $ | Ops (solo) | License | Maturity / freshness | Hard gates |
|---|---|---|---|---|---|---|---|---|
| **Marker + Surya** | Vendor olmOCR 76% balanced [[rel](https://github.com/datalab-to/marker/releases)][[pypi](https://pypi.org/project/marker-pdf/)] | Markdown/JSON, columns/tables via layout+VLM; nested forms weak | EN via OCR models (EN textbooks OK; lang pack story less explicit than Tesseract) | Local; GPU preferred for balanced; CPU `fast`; optional Datalab API | pip + torch; Dockerize; GPU ops burden | PyPI Apache-2.0; OpenRAIL history caution | **v2.0.0** release ~Jul (stale vs ≤1 mo version gate) | Pass: Python, scans, Dockerizable; quality gate DIY |
| **OCRmyPDF + Tesseract** | Strong searchable text; weak multi-column **structure** [[adv](https://ocrmypdf.readthedocs.io/en/latest/advanced.html)] | Text layer only; no structure rebuild | `eng` first-class [[api](https://ocrmypdf.readthedocs.io/en/latest/api.html)] | Local CPU; $0 API | Lowest solo ops; official Docker | (not re-fetched; classic open-source — license claim omitted) | Living docs; v17 API | Pass scans/Docker/Python; layout recovery weak |
| **docTR** | Vendor claims SOTA vs cloud OCR [[doctr](https://mindee.github.io/doctr/)] | Layout predictor present | Typically Latin/EN models (detail not fetched) | Local CPU/GPU | PyTorch stack | Not fetched | Living docs | Pass Python/scans; quality DIY |
| **LlamaParse** | Marketed for multi-column + scans [[lp](https://developers.llamaindex.ai/python/cloud/llamaparse/)] | Generative layout→md/JSON | `ocr_parameters.languages: ["en"]` | Cloud lock-in; $ unverified (404) | Minimal ops; API key | SaaS ToS | Living SDK docs | Pass scans/Python; quality DIY; exit cost high |
| **Google Doc AI** | Enterprise OCR + Layout Parser [[pricing](https://cloud.google.com/document-ai/pricing)] | Layout Parser $10/1k pp | Cloud EN | OCR $1.50/1k after 1k free | Cloud account + quotas | SaaS | Living pricing | Pass; lock-in; DIY quality |
| **Azure Doc Intelligence** | Layout feature listed [[azure](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/)] | Layout extract | Cloud EN | $ obfuscated in fetch; free 500 pp | Cloud/container | SaaS | Living | Pass; lock-in |
| **PaddleOCR** | Insufficient README fetch | Unverified | 100+ langs claim (tagline) | Local typical | Unverified | Unverified | Unverified | **Parked** — evidence gap |
| **pdfplumber/pymupdf** | n/a for scans | Born-digital | n/a | Local | Low | n/a | n/a | **Cut** — scan gate (hypothesis) |

**Leaders (evidenced):** Marker (local layout+OCR), LlamaParse / Google Doc AI (cloud layout+OCR).  
**Challengers:** OCRmyPDF (ops), docTR (research-grade local OCR+layout).  
**Wildcard:** Marker `fast` CPU + cloud spillover (LlamaParse/Google) only on pages failing local quality/OCR confidence.

---

## Verdict draft

| Role | Choice |
|---|---|
| **Pick** | **Marker (`marker-pdf`) in Docker Compose**, default **`fast` on CPU** / **`balanced` if GPU available**; English textbooks via scan OCR path; **custom Poor-quality gate before Marker** (blur/contrast/skew + empty/low-yield text heuristics — product-owned, not vendor-native). Use born-digital text-layer path when present (`--disable_ocr` / selective OCR already in Marker). |
| **Runner-up** | **Google Document AI** (Enterprise OCR ± Layout Parser) for accuracy without GPU ops; **or OCRmyPDF** if the product only needs searchable English text + preprocess, not rich markdown structure. |
| **When runner-up wins** | No GPU and Marker CPU too slow/noisy on exercise layouts; need SLA’d OCR with vendor support; or layout recovery must be cloud-grade on day one with zero model ops. OCRmyPDF wins if structure recovery is deferred and solo ops must stay minimal. |
| **Strongest argument against pick** | Solo **GPU/torch ops** + **self-reported** benches only; **version freshness** fails ≤1 mo gate (2.0.0 ~Jul); **license ambiguity** (OpenRAIL history vs PyPI Apache-2.0); nested textbook exercises/forms called out as weak; no built-in Poor-quality status. |
| **Cheapest reversibility hedge** | Thin **ingest adapter** (`parse(pdf) → {text, structure, quality}`) with (1) image-quality reject shared by all backends, (2) Marker as default, (3) OCRmyPDF as cheap searchable fallback, (4) optional Google/LlamaParse page-level escape hatch — swap backend without changing product status enum. |

---

## Leads

1. Fetch Marker LICENSE file + Datalab commercial terms to resolve Apache vs OpenRAIL.
2. Independent olmOCR-bench / textbook-scan bake-off (Marker vs docTR vs Google Layout) — two-source performance still vendor-heavy.
3. LlamaParse Pricing & credits page (correct URL) for lock-in math.
4. Azure calculator or regional pricing JSON for readable $/1k Layout vs Read.
5. Tesseract mean confidence / `ocrmypdf.quality` source code for concrete Poor-quality thresholds.
6. PaddleOCR PP-Structure / PP-OCRv4 official docs (README fetch failed).
7. Production retrospectives (≤6–12 mo) for Marker or LlamaParse on textbooks — none retrieved this run.

---

## Looked for but not found

- Working **WebSearch** this run (all calls rejected) — limited discovery of secondary retrospectives.
- Marker docs.datalab.to page (HTTP 500).
- OCRmyPDF `quality.html` (404); module exists in API index only.
- LlamaParse `/pricing/` (404); no $/credit schedule retrieved.
- Azure dollar amounts (page placeholders).
- Usable PaddleOCR / EasyOCR / unstructured / AWS Textract primary pages.
- Any vendor documenting a productized **Poor-quality scan reject** status matching the decision brief.
- Independent (non-vendor) accuracy study ≤12 mo comparing Marker vs cloud Doc AI on multi-column English textbooks.
