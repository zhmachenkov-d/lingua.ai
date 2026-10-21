---
tracker_id: "3"
remote: "https://github.com/zhmachenkov-d/lingua.ai/issues/3"
tracker_status: backlog
type: epic
title: "Phase A — Research package (D1–D3)"
parent: initiative-research
covers: ["R1", "R3", "R4", "R5", "R12", "R15", "R16", "R17", "R18"]
sources:
  [
    "_bmad-output/initiative-research/initiative-research.md",
    "_bmad-output/initiative-research/tickets/epic-phase-a-research/prd-phase-a-research/prd-phase-a-research.md",
  ]
companions:
  [
    "_bmad-output/initiative-research/tickets/epic-phase-a-research/prd-phase-a-research/prd-phase-a-research.md",
    "_bmad-output/initiative-research/tickets/epic-phase-a-research/prd-phase-a-research/addendum.md",
    "_bmad-output/initiative-research/tickets/epic-phase-a-research/prd-phase-a-research/review-rubric.md",
    "_bmad-output/initiative-research/research-phase-a-learning-algorithms-mastery-revi/research-phase-a-learning-algorithms-mastery-revi.md",
    "_bmad-output/initiative-research/research-phase-a-d3-tech-pdf-ocr-fsrs-libs-stack/research-phase-a-d3-tech-pdf-ocr-fsrs-libs-stack.md",
    "_bmad-output/initiative-research/research-phase-a-d2-competitive-duolingo-anki-lin/research-phase-a-d2-competitive-duolingo-anki-lin.md",
  ]
after: []
refined: true
risk: medium
---

# Phase A — Research package (D1–D3)

## Description

Produce the Phase A intermediate package: modern SLA/ISLA practices (D1), competitive analysis (D2), and tech research (D3) in the shared Russian document skeleton, marked «Фаза A — на ревью». Tech choices respect the owner MVP baseline (Python 3.13, Angular, Docker Compose) and PDF/OCR ingestion of scanned textbooks (R18), bind owner-approved algorithm/tech/competitive decisions (PRD §6.3–6.5), and state trade-offs explicitly. Dictionary row: Free Dictionary primary; Oxford runner-up pending owner T&Cs after signup.

## Outcome

The owner can confirm or reject Phase A before any design (D4–D9) is written.

## Requirements

- R1 (parent R1): The Phase A package shows how textbook work, dictionary vocabulary (Free Dictionary primary; Oxford runner-up after license T&Cs), and modern SLA/ISLA practices combine for the designed agent, consistent with PRD vision and §6.3–6.5.
- R3 (parent R3): Deliver D1 as a table Practice → principle → agent implementation → verification metric covering at least the brief’s practice list (FSRS vs SM-2 with rationale aligned to §6.3; i+1; TBLT; Focus on Form; error-based learning; microlearning; formative feedback; CEFR/mastery; sentence-based learning; explicit+implicit balance). Each practice cites a source, names an architecture component, and names a metric; Learned-badge and frequent-error thresholds cite R19.
- R4 (parent R4): Deliver D2 competitive analysis (≥8 products, including the brief set) with strengths, weaknesses, borrow/avoid, and applicable/not; rows reflect PRD §6.5 white space, borrow, and avoid.
- R5 (parent R5): Deliver D3 tech research table for LLM (RU UI + cost; primary/runner-up from R20), agent orchestration, vector DB, SRS (`pip install fsrs`; runner-up `fsrs-rs-python`), dictionary (Free Dictionary recommend; Oxford runner-up + license gate), optional ASR/TTS, profile storage, and textbook PDF/OCR including scans (Marker + Poor-quality gate; runner-ups OCRmyPDF / Document AI). Baseline: Python 3.13 + ruff/mypy, Angular quality toolchain, Docker Compose (R15–R17). Every recommendation states a trade-off; Oxford lists fields and risk flags without claiming display/redistribution rights cleared.
- R12 (parent R12): Deliver Phase A as one document skeleton at `_bmad-output/initiative-research/docs/research-package.md` with sections 1–3 filled and marked «Фаза A — на ревью»; do not start D4–D9 content in this epic.
- R15 (parent R15): D3 treats Docker Compose local deploy as MVP baseline (trade-offs only, not silent defaults).
- R16 (parent R16): D3 treats Python 3.13 with ruff (lint + format) and mypy as required server quality gates.
- R17 (parent R17): D3 treats Angular web client with a complete code-quality toolchain as MVP client baseline.
- R18 (parent R18): D3 researches and recommends PDF/OCR for scanned textbooks with explicit trade-offs (Marker + product Poor-quality gate per §6.4).
- R19 (prd §8 Q13–Q14, FR-19, FR-23): Exact Learned-badge thresholds (e.g. stability floor + last _k_ successful retrievals) and frequent-error frequency threshold are decided and recorded so D1 can cite them.
- R20 (prd §8 Q11): RU LLM quality scorecard across OpenAI mini/nano, Anthropic Haiku/Sonnet, and Gemini Flash-Lite names Phase A/MVP primary and runner-up so D3 can cite them.

## Constraints

- C1 (parent C1): No production code in this epic.
- C2 (parent C2): No visual UI/UX design — document and scenario logic only.
- C3 (parent C3): No legal opinion on Oxford API licenses — product policy and risk flags only (Free Dictionary primary until owner reads Oxford T&Cs).
- C8 (parent C8): Phase B and C must not begin until Phase A review is confirmed.
- C9 (parent C9): D3 treats Docker Compose, Python 3.13 toolchain, and Angular as MVP baseline; alternatives only as documented trade-offs.

## Done when

1. D1, D2, and D3 meet R3–R5 (and R15–R18 where they bind D3).
2. The document is marked «Фаза A — на ревью» with sections 1–3 filled (R12).
3. R19 thresholds are recorded and cited from D1.
4. R20 LLM primary/runner-up are recorded and cited from D3.
5. Self-review answers: enough to decide whether to proceed to design.
6. Dictionary and algorithm/tech/competitive rows match PRD §6.3–6.5 and the Free Dictionary primary decision.

## Boundaries

- In: D1 practices table, D2 competitors, D3 stack/API research including textbook PDF/OCR for scans; threshold spike; RU LLM scorecard spike; Phase A review HITL.
- Out: D4–D9 content (C8); production code (C1); visual UI (C2); paid Oxford as MVP-primary lexicon; legal counsel on licenses (C3).
- Must not change: initiative Requirements; Phase B/C wait on this epic’s owner confirmation.

## References

- parent — `_bmad-output/initiative-research/initiative-research.md`, Requirements R1, R3–R5, R12, R15–R18
- brief — `_bmad-output/initiative-research/brief-research/brief-research.md`, §4 D1–D3, §5 Phase A, §9
- prd — `_bmad-output/initiative-research/tickets/epic-phase-a-research/prd-phase-a-research/prd-phase-a-research.md`
- addendum — `_bmad-output/initiative-research/tickets/epic-phase-a-research/prd-phase-a-research/addendum.md`
- review-rubric — `_bmad-output/initiative-research/tickets/epic-phase-a-research/prd-phase-a-research/review-rubric.md`
- recon-algorithms — `_bmad-output/initiative-research/research-phase-a-learning-algorithms-mastery-revi/research-phase-a-learning-algorithms-mastery-revi.md`
- recon-tech — `_bmad-output/initiative-research/research-phase-a-d3-tech-pdf-ocr-fsrs-libs-stack/research-phase-a-d3-tech-pdf-ocr-fsrs-libs-stack.md`
- recon-competitive — `_bmad-output/initiative-research/research-phase-a-d2-competitive-duolingo-anki-lin/research-phase-a-d2-competitive-duolingo-anki-lin.md`

## Notes

- Decision: 2026-10-20 — Epic cut by brief phase gate (one reviewable research package), not one epic per deliverable.
- Decision: 2026-10-20 — Document path: `_bmad-output/initiative-research/docs/research-package.md`. Competitor set: brief minimum. Textbook name not required for Phase A tables.
- Decision: 2026-10-20 — Six stories draft approved; later expanded after PRD/recon (see 2026-10-21).
- Decision: 2026-10-20 — Owner requires PRD and deep-recon before epic Requirements and `refined: true`.
- Decision: 2026-10-20 — Consistency pass instead of default Refactor sweep (research docs, not code).
- Decision: 2026-10-21 — Adopt finalized PRD + three deep-recon reports as companions; refine epic and plan stories.
- Decision: 2026-10-21 — Oxford display/redistribution: policy A — Free Dictionary primary for Phase A/MVP lexicon recommend; Oxford runner-up until owner reads T&Cs after signup (closes PRD Q10 for D3 lock).
- Decision: 2026-10-21 — Learned S/k and FR-23 frequency thresholds in a dedicated spike before D1 (not inline in D1 alone).
- Decision: 2026-10-21 — RU LLM scorecard (PRD Q11) policy C: Phase A spike (entry 8) before D3; owner picks primary/runner-up from OpenAI / Anthropic / Gemini shortlist.
- Decision: 2026-10-21 — Tracer bullet: entry 1 (document skeleton). Build order: skeleton → thresholds spike → D1 → D2 → RU LLM spike → D3 → consistency → review.
- Assumption: Exemplar corpus `textbooks/*.pdf` is enough for Phase A OCR discussion; naming one primary title can wait for Phase B.
