---
title: 'technical research: Phase A D3 tech: PDF/OCR, FSRS libs, stack criteria'
type: 'technical'
topic: 'Phase A D3 tech: PDF/OCR, FSRS libs, stack criteria'
decision: 'Recommend Phase A D3 approach for PDF/OCR of scanned textbooks, Python FSRS library, and criteria+shortlist for remaining D3 stack rows under Python 3.13 + Angular + Docker Compose'
source: 'native-run'
status: complete
preset: 'standard'
validation: 'normal'
verified_claims: 10
unverified_claims: 4
created: '2026-10-21T06:13:29+00:00'
updated: '2026-10-21T06:20:57+00:00'
---

# technical research: Phase A D3 tech: PDF/OCR, FSRS libs, stack criteria

**Decision this research serves:** Recommend Phase A D3 approach for PDF/OCR of scanned textbooks, Python FSRS library, and criteria+shortlist for remaining D3 stack rows under Python 3.13 + Angular + Docker Compose

## Executive summary

**Do this for Phase A D3:** (1) Ingest scans with **Marker (`marker-pdf`) + a product-owned Poor-quality gate** behind a thin parse adapter; fall back to OCRmyPDF or Google Document AI when GPU ops or structure needs flip [1][3][4][7]. (2) Name **`pip install fsrs`** (OSR py-fsrs) as the FSRS library; keep `fsrs-rs-python` as Anki-parity swap [8][9][10][11]. (3) Fill the rest of the D3 table with the **criteria weights + shortlists** below; use the **provisional lean bundle** only as a starting point the owner re-weights — not a forced pick per row [13]–[26].

**What drives that:** Solo Compose ops dominate (Dify’s ~15 containers is a cautionary ceiling) [18]; cloud OCR/lexicon floors are real (£50/mo Oxford Lite entry; Google OCR $1.50/1k after free tier) [4][21]; FSRS packaging is clear and low-risk [8][9].

**Biggest caveats:** Marker accuracy is vendor self-reported [2]; Oxford full display/redistribution license text was not public this run [22]; Russian LLM quality has **no vendor SLA** — must be an eval gate [14]; several community retros and local ASR/TTS docs were blocked or unfetched.

---

## OCR / scanned textbook ingest

**Question:** Which PDF/OCR + layout stack should Phase A D3 recommend for English textbook scans, with a Poor-quality refuse path, under Python 3.13 + Docker Compose solo ops?

**Landscape.** Evidenced finalists: **Marker** (`marker-pdf` 2.0.0 — local PDF→markdown/JSON with Surya OCR on garbled/scanned pages) [1][2]; **OCRmyPDF** (searchable text layer on scans, official Docker, weak structure rebuild) [3]; cloud **Google Document AI** (Enterprise OCR + Layout Parser) [4]; hosted **LlamaParse** (scans + multi-column; pricing page 404 this run) [5]; **docTR** (local OCR + layout predictor; vendor SOTA claims) [6]. PaddleOCR / EasyOCR / unstructured / Textract were **unscreened** (fetch/search gaps). Born-digital-only extractors fail the scan hard gate as primary path.

**Integration / ops.** Marker pulls `surya-ocr` + `torch` — Dockerizable but GPU-preferred for `balanced`; CPU `fast` is documented [1][2]. OCRmyPDF is the lightest local ops path [3]. Cloud options minimize model ops, raise lock-in and quota work [4][5]. **No retrieved vendor documents a turnkey Poor-quality reject status** — product must own blur/skew/low-yield gates upstream [7].

**Select verdict — OCR:** Pick **Marker (`marker-pdf`) + custom Poor-quality gate** (adapter: `parse(pdf) → {text, structure, quality}`). Default `fast` on CPU / `balanced` if GPU. Runner-up: **Google Document AI** when zero GPU ops and SLA matter ($1.50/1k pages after 1k free for Enterprise OCR; Layout Parser $10/1k) [4]; **OCRmyPDF** if structure recovery is deferred. **Against pick:** torch/GPU burden; olmOCR scores are vendor self-reported [2]; PyPI Apache-2.0 vs historical OpenRAIL note needs license diligence [1][2]; nested forms/exercises called out as weak. **Hedge:** thin ingest adapter with OCRmyPDF fallback + optional cloud escape hatch.

*Spot-check (normal):* Marker 2.0.0 / Apache-2.0 / `surya-ocr`+`torch` / olmOCR 76.0% in description — **verified** via PyPI JSON [1]. OCRmyPDF scan+Docker purpose — **verified** via official docs [3]. Google Enterprise OCR $1.50/1k after 1k free — **verified** via pricing page [4]. Poor-quality turnkey absence — **unverified** (absence claim; multi-doc synthesis) [7].

---

## FSRS Python library

**Question:** Given FSRS is the chosen algorithm, which Python package should D3 name for item scheduling under Python 3.13?

**Landscape.** Install name is **`fsrs`** (repo `open-spaced-repetition/py-fsrs`); PyPI `py-fsrs` **404** [8]. Latest `fsrs` **6.3.2**: MIT, `requires-python >=3.10`, default dep `typing-extensions`, CI covers 3.13 [8][9]. API: `Card` D/S/`due`, `Scheduler.review_card`, `get_card_retrievability`; optional `fsrs[optimizer]` (torch) [9]. Runner-up **`fsrs-rs-python` 0.9.3**: PyO3 bindings to Rust `fsrs` **6.6.2** (same version Anki pins), cp313 wheels, optimize without torch; thinner docs; SPDX undeclared on PyPI (parent crate BSD-3) [10][11]. No first-party Anki Python FSRS embed package [11]. SM-2 only as import fallback (`sm-2` MIT; avoid AGPL `anki-sm-2`) [12].

**Cost / lock-in.** Both free OSS. Exit cost low if the app persists review logs + D + S + `due` behind a thin adapter (`review_card` vs `next_states`) [9][10].

**Select verdict — FSRS lib:** Pick **`pip install fsrs`** (OSR py-fsrs). Runner-up **`fsrs-rs-python`** when Anki numerical parity or torch-free optimize matters more than ergonomics. **Against pick:** Anki uses Rust `fsrs` 6.6.2; py-fsrs README warns optimizer numbers may differ slightly [9][11]. **Hedge:** persist D/S/due + logs in your schema; one-file scheduler adapter.

*Spot-check (normal):* `fsrs` 6.3.2 MIT ≥3.10 — **verified** PyPI [8]. `py-fsrs` 404 — **verified** [8]. Anki `Cargo.toml` pins `fsrs` 6.6.2 — **verified** [11]. `fsrs-rs-python` 0.9.3 + cp313 wheels — **verified** PyPI [10].

---

## D3 stack criteria & shortlists

**Question:** What evaluation criteria and 3–5-candidate shortlists should Phase A D3 use for LLM, orchestration, vector DB, dictionary API, ASR/TTS, and profile storage — without forcing a final pick per row?

### Suggested weights (solo Phase A)

| Criterion | Weight | Why |
|-----------|--------|-----|
| Ops burden | **0.30** | Dify Compose alone starts ~15 containers (7 core + 8 deps), ≥2 CPU / ≥4 GiB (≥8 GiB on macOS VM) [18] |
| Cost (API + infra) | **0.25** | Token floors ~$0.05–$10+/MTok [13][15][16]; Oxford from £50/mo [21]; Pinecone Builder $20 / Standard $50 min [20] |
| RU quality (UI + content) | **0.20** | No vendor RU chat SLA on pricing pages — **eval gate**, not catalog claim [14]; Oxford RU is translations, not EN Entries [23] |
| Lock-in | **0.15** | Managed-only vectors / proprietary agents raise exit cost [20]; LiteLLM on Thoughtworks Trial as abstraction pattern [17] |
| Maturity | **0.10** | Thoughtworks Vol 34: young AI tools hard to assess; LangGraph **Trial** not Adopt [17] |

Owner may re-weight (e.g. RU → 0.30 if existential).

### Shortlists (pass hard gates: Python/HTTP + Compose-friendly + solo-operable)

| Row | Shortlist (3–5) | Notes |
|-----|-----------------|-------|
| **A LLM** | OpenAI mini/nano; Anthropic Haiku/Sonnet; Gemini Flash-Lite (+ Free); open-weight local/vLLM; LiteLLM multi-backend | Cost leaders: Gemini Free / OpenAI nano for spikes [13][15][16]; RU = scorecard later [14] |
| **B Orchestration** | Custom Python state machine; LangGraph; LangChain agents; Dify (conditional); Coze **unevidenced** | Prefer custom/thin LangGraph; Dify fails “lean solo” unless visual builder required [17][18][19] |
| **C Vector DB** | pgvector on Postgres; Qdrant; Chroma; Pinecone (conditional); Weaviate (peer) | pgvector = one less service [24]; Pinecone floors $20–$50 [20] |
| **D Dictionary** | Oxford Dictionaries API; Free Dictionary API; Merriam-Webster | Oxford: Sandbox 500; Lite from £50/mo (1k calls / £0.10 overage per pricing digest — exact tier table **medium**); Growing £200+; Enterprise £5k+/lang/yr commercial [21][22][23]; full display license **not public** [22]; Free Dict for prototype [25] |
| **E ASR/TTS** | OpenAI Whisper / gpt-*-transcribe; OpenAI TTS; local Whisper/Piper (**docs thin this run**); Gemini audio | Whisper $0.006/min; tts-1 $15/1M chars [13]; local = spike first |
| **F Profile storage** | Postgres relational; Postgres + JSONB; Mongo (extra service); SQLite; Redis-only (not SoR) | Evidence favors **relational + JSONB** [26] |

### Provisional lean bundle (labeled provisional)

OpenAI mini/nano **or** Gemini Flash-Lite · custom / thin LangGraph · **pgvector** · Free Dictionary → Oxford if license/gates pass · defer ASR/TTS (then OpenAI) · **Postgres + JSONB**. Swap conditions: RU eval fail → provider swap; durable HITL → LangGraph; vector scale → Qdrant before Pinecone; lexicon legal → Oxford Growing/cache; offline audio → local spike; schema chaos → JSONB before new DB.

*Spot-check (normal):* Oxford plans from £50/mo (9 Jan 2025 update) — **verified** [21]. Pinecone Builder $20 / Standard $50 min — **verified** [20]. Dify ≥2 CPU / ≥4 GiB and 7 core + 8 dep containers — **verified** [18]. Exact Oxford Lite 1k/£0.10 table — **unverified** this landing (digest-only; pricing SPA empty in curl). RU LLM SLA absence — **unverified** gap claim [14].

---

## Cross-dimension insights

1. **Torch appears twice:** Marker (OCR) and optional `fsrs[optimizer]` — a solo Compose image that already carries torch for Marker can absorb FSRS optimize later; if Marker stays CPU-`fast` only, prefer `fsrs-rs-python` for torch-free optimize [1][9][10].
2. **Ops budget is the scarce resource:** Marker GPU + Dify-class platforms + separate vector DB stack can exhaust solo ops before LLM quality matters [1][18][24]. Default to fewer containers (Postgres+pgvector, custom agents).
3. **Paid floors cluster:** Oxford Lite £50/mo and Pinecone $20–$50/mo are easy to underestimate next to token cents [20][21] — Phase A D3 table should show **monthly floor** columns, not only $/tok.
4. **Adapters beat picks:** OCR parse adapter + FSRS schedule adapter + LLM gateway mirror the same reversibility pattern across dimensions [7][9][17].

---

## Recommendations

| # | Recommendation | Feeds | Confidence |
|---|---------------|-------|------------|
| 1 | D3 OCR row: **Marker + custom Poor-quality gate**; document OCRmyPDF / Google Doc AI as runner-ups; require ingest adapter | Epic R5/R18, PRD FR ingest | **High** for local layout path existence; **medium** for Marker as accuracy winner (vendor bench) |
| 2 | D3 SRS row: name library **`fsrs` (py-fsrs) 6.3.x**; metric = schedule retention vs desired R; badge policy remains product (Run 1) | Epic R5, PRD FR-19 | **High** |
| 3 | D3 remaining rows: publish **weights + shortlists + provisional lean bundle**; owner re-weights before locking | Epic R5 D3 table | **Medium** (criteria evidenced; picks provisional) |
| 4 | Before Oxford spend: fetch **display/redistribution license**; until then Free Dictionary for prototype | D3 dictionary row | **High** on license gap |
| 5 | Before LLM lock: run **RU UI + EN pedagogy prompt pack** across OpenAI / Anthropic / Gemini | D3 LLM row | **High** that eval is required; quality TBD |

---

## Open questions

1. Marker LICENSE diligence (Apache-2.0 vs historical OpenRAIL) and textbook-scan bake-off vs Google Layout — what delta on English File pages?
2. Exact Oxford Lite call quotas / overage and app-display rights after account access?
3. RU LLM scorecard results (not run this research)?
4. Coze primary docs + comparison to Dify container tax?
5. Local Whisper.cpp / Piper Compose footprint and quality for lesson audio?
6. pgvector vs Qdrant latency at expected corpus size (no perf numbers this run)?

---

## Source appendix

| [n] | Claim / finding | Publisher | Pub date | Accessed | Confidence |
|-----|-----------------|-----------|----------|----------|------------|
| [1] | marker-pdf 2.0.0 Apache-2.0; Python ≥3.10; deps surya-ocr + torch | [PyPI marker-pdf](https://pypi.org/project/marker-pdf/) | 2025-07 | 2026-10-21 | high |
| [2] | Marker olmOCR balanced ~76% (vendor) | [Marker releases](https://github.com/datalab-to/marker/releases) / PyPI | 2025-07 | 2026-10-21 | medium |
| [3] | OCRmyPDF OCR layer for scanned PDFs + Docker | [OCRmyPDF docs](https://ocrmypdf.readthedocs.io/en/latest/) | living | 2026-10-21 | high |
| [4] | Google Doc AI Enterprise OCR $1.50/1k after 1k free; Layout Parser $10/1k | [Google Document AI pricing](https://cloud.google.com/document-ai/pricing) | living | 2026-10-21 | high |
| [5] | LlamaParse scans + multi-column; pricing URL 404 | [LlamaParse docs](https://developers.llamaindex.ai/python/cloud/llamaparse/) | living | 2026-10-21 | medium |
| [6] | docTR OCR + layout predictors | [docTR docs](https://mindee.github.io/doctr/) | living | 2026-10-21 | medium |
| [7] | No vendor turnkey Poor-quality reject (synthesis) | multiple OCR docs | 2026-10 | 2026-10-21 | unverified |
| [8] | PyPI `fsrs` 6.3.2 MIT ≥3.10; `py-fsrs` 404 | [PyPI fsrs](https://pypi.org/project/fsrs/) | 2026-08 | 2026-10-21 | high |
| [9] | fsrs Card D/S/due + review_card + retrievability | [py-fsrs README](https://github.com/open-spaced-repetition/py-fsrs) | living | 2026-10-21 | high |
| [10] | fsrs-rs-python 0.9.3 cp313 wheels | [PyPI fsrs-rs-python](https://pypi.org/project/fsrs-rs-python/) | 2026-08 | 2026-10-21 | high |
| [11] | Anki pins Rust fsrs 6.6.2 | [ankitects/anki Cargo.toml](https://github.com/ankitects/anki/blob/main/Cargo.toml) | living | 2026-10-21 | high |
| [12] | SM-2 fallback packages; anki-sm-2 AGPL | [PyPI sm-2](https://pypi.org/project/sm-2/) | 2024-12 | 2026-10-21 | high |
| [13] | OpenAI API token + Whisper/TTS rates | [OpenAI pricing](https://platform.openai.com/docs/pricing) | living | 2026-10-21 | high |
| [14] | No public RU LLM quality SLA on vendor pricing pages | gap this run | — | 2026-10-21 | unverified |
| [15] | Anthropic API model rates | [Anthropic pricing](https://www.anthropic.com/pricing#api) | living | 2026-10-21 | high |
| [16] | Gemini Free/Paid; flash-lite rates | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) | living | 2026-10-21 | high |
| [17] | LangGraph Trial; LiteLLM Trial; durability caution | [Thoughtworks Radar](https://www.thoughtworks.com/radar) Vol 34 | 2026-04 | 2026-10-21 | high |
| [18] | Dify Compose ≥2 CPU ≥4 GiB; 7 core + 8 dep containers | [Dify Docker Compose](https://docs.dify.ai/en/getting-started/install-self-hosted/docker-compose) | living | 2026-10-21 | high |
| [19] | LangGraph low-level Python agent runtime | [LangGraph docs](https://docs.langchain.com/langgraph) | living | 2026-10-21 | high |
| [20] | Pinecone Builder $20 flat; Standard $50/mo min | [Pinecone pricing](https://www.pinecone.io/pricing/) | living | 2026-10-21 | high |
| [21] | Oxford API plans from £50/mo (Lite/Growing relaunch) | [Oxford API updates](https://developer.oxforddictionaries.com/updates) | 2025-01-09 | 2026-10-21 | high |
| [22] | Oxford Lite tier details / full display license incomplete publicly | [Oxford pricing](https://account.oxforddictionaries.com/pricing) + gap | 2025+ | 2026-10-21 | medium / gap |
| [23] | Oxford REST v2 shape; RU = translations | [Oxford making requests](https://developer.oxforddictionaries.com/documentation/making-requests-to-the-api) / [languages](https://developer.oxforddictionaries.com/documentation/languages) | living | 2026-10-21 | high |
| [24] | pgvector Postgres extension | [pgvector/pgvector](https://github.com/pgvector/pgvector) | living | 2026-10-21 | medium |
| [25] | Free Dictionary API public JSON shape | [dictionaryapi.dev](https://dictionaryapi.dev/) | living | 2026-10-21 | medium |
| [26] | Postgres JSON/JSONB types | [PostgreSQL JSON docs](https://www.postgresql.org/docs/current/datatype-json.html) | living | 2026-10-21 | high |

---

## Staleness map

AI-adjacent pricing/versions age fastest (≤1–3 mo). Earliest re-check: OpenAI/Anthropic/Gemini/Pinecone/Oxford pricing pages and Marker/`fsrs` PyPI versions. Ecosystem ops claims (Dify Compose footprint, Thoughtworks Trial) ≤6 mo. Landscape patterns ≤12 mo.

| Claim class | Example refs | Freshness bar | Re-check by (approx) |
|-------------|--------------|---------------|----------------------|
| version / compatibility | [1][8][10][11] | ≤1 mo | 2026-11-21 |
| pricing | [4][13][15][16][20][21] | ≤3 mo | 2027-01-21 |
| AI-adjacent landscape | [17][19] | ≤3 mo | 2027-01-21 |
| ops / ecosystem | [3][18][24] | ≤6 mo | 2027-04-21 |
| patterns / storage | [26] | ≤24 mo | 2028-10-21 |

**Earliest refresh work order:** PyPI Marker + `fsrs` versions; LLM/Pinecone/Oxford pricing; then Dify Compose footprint if still a candidate.
