# Addendum — Phase A PRD companions

Technical and competitive depth that supports the PRD but does not belong in the FR narrative. PRD: `prd-phase-a-research.md` (status: final).

## Deep recon companions

| Run | Topic                                     | Path                                                                                  | PRD binding       |
| --- | ----------------------------------------- | ------------------------------------------------------------------------------------- | ----------------- |
| 1   | Mastery / review / remediation algorithms | `_bmad-output/initiative-research/research-phase-a-learning-algorithms-mastery-revi/` | §6.3, FR-10/19/24 |
| 2   | PDF/OCR, FSRS Python lib, D3 criteria     | `_bmad-output/initiative-research/research-phase-a-d3-tech-pdf-ocr-fsrs-libs-stack/`  | §6.4, R5/R18      |
| 3   | Competitive D2 (≥10 products)             | `_bmad-output/initiative-research/research-phase-a-d2-competitive-duolingo-anki-lin/` | §6.5, R4          |

## Tech notes (from Run 2 — not product FRs)

- **OCR:** Marker (`marker-pdf`) + custom Poor-quality gate; adapter `parse(pdf) → {text, structure, quality}`; runner-ups OCRmyPDF / Google Document AI.
- **FSRS lib:** `pip install fsrs` (OSR py-fsrs); runner-up `fsrs-rs-python` for Anki parity.
- **Provisional lean stack:** OpenAI mini/nano or Gemini Flash-Lite · custom/thin LangGraph · pgvector · Free Dictionary→Oxford if license gates pass · defer ASR/TTS · Postgres+JSONB. Owner may re-weight before D3 table lock.
- **Dictionary policy (2026-10-21):** Free Dictionary primary; Oxford runner-up until owner reads T&Cs after signup (closes PRD Q10 for D3).
- **RU LLM (2026-10-21):** Q11 policy C — Phase A scorecard spike before D3; primary/runner-up owner-picked from OpenAI / Anthropic / Gemini.

## Competitive notes (from Run 3 — feeds D2 table)

- **White space:** textbook OCR + dictionary-in-context + transparent FSRS + Teacher Agent.
- **Borrow / avoid / applicable:** see PRD §6.5 and Run 3 master table.
- Speaking v1 caution: prefer dialogue + course/TTS over untrusted pronunciation scoring (ELSA pattern).

## Rejected / deferred alternatives (logged)

- Telegram ingest/lesson notify in MVP → Stage 2.
- FSRS-alone on whole lessons → rejected for hybrid (§6.3).
- SM-2 as primary scheduler → runner-up only.
- Dify as default orchestration → ops tax (~15 containers); custom/thin LangGraph preferred unless visual builder required.
