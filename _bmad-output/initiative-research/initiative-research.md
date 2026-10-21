---
tracker_id: "1"
remote: "https://github.com/zhmachenkov-d/lingua.ai/milestone/1"
tracker_status: backlog
type: initiative
title: "Research and design an AI English learning agent"
parent: none
sources:
  - _bmad-output/initiative-research/brief-research/brief-research.md
companions: []
after: []
risk: medium
---

# Research and design an AI English learning agent

## Description

Produce a decision-ready research and design package for an AI agent that helps adults self-study English by combining a primary textbook, Oxford Dictionaries data, and modern SLA/ISLA practices. The package must be usable for a build/go decision and for handoff into implementation (MVP → Stage 2 → Stage 3), not a literature survey.

## Outcome

For the project owner: a single Russian-language project document that enables a go/no-go on development within five minutes of reading the Executive Summary, and that lets builders start the MVP without further research.

## Requirements

- R1 (§1): The designed agent combines textbook work (structured units, grammar), Oxford Dictionary vocabulary (definitions, examples, audio, collocations), and modern SLA/ISLA practices (SRS, i+1, TBLT, microlearning, focus on form, formative assessment, CEFR alignment).
- R2 (§1, §7): Output is applicable project documentation — architecture, data models, prompts, scenarios, and an implementation plan — sufficient for a development decision and handoff MVP → Stage 2 → Stage 3.
- R3 (§4 D1): Deliver D1 as a table Practice → principle → agent implementation → verification metric covering at least: FSRS vs SM-2 with choice rationale; comprehensible input / i+1 / ~90% understanding; TBLT pre/main/post; Focus on Form in communicative context; error-based learning with error journal and delayed feedback; generative microlearning; formative interpretable feedback; CEFR alignment and mastery progression; sentence-based (not isolated-word) learning; balanced explicit + implicit instruction. Each practice cites a source, names an architecture component, and names a metric.
- R4 (§4 D2): Deliver D2 competitive analysis (≥8 products) including Duolingo, Anki, LingQ, Busuu, Memrise, Quizlet, Elsa Speak, ChatGPT tutors, and specialized SRS apps; each row has strengths, weaknesses, borrow/avoid, and applicable/not with rationale.
- R5 (§4 D3): Deliver D3 tech research table for LLM (incl. Russian UI and cost), agent orchestration (LangGraph / Dify / Coze / custom), vector DB (Qdrant / Chroma / Pinecone / pgvector), SRS (FSRS libs vs SM-2), Oxford Dictionaries API (endpoints, limits, license flags, response shape), optional ASR/TTS, profile storage (relational vs document), and textbook PDF ingestion including scanned pages (OCR/layout — R18). Baseline stack to evaluate against (not reopen without trade-off): Python 3.13 server, Angular web client, Docker Compose local deploy (R15–R17). Every recommendation states a trade-off; Oxford lists concrete fields to use (definition, examples, audio, synonyms, collocations, CEFR tag if any); SRS names the FSRS library/implementation; PDF/OCR names the library/pipeline and what fails on hard scans.
- R6 (§4 D4): Deliver D4 architecture with four layers Perception → Cognitive/Planning → Memory → Actions/Tools; agent table for Router, Tutor, Vocabulary, Review, and Critic (Stage 3) with role, I/O, tools, trigger; agent handoff scheme; short-term vs long-term memory split; Mermaid-reproducible diagram; per-agent system prompt contract; explicit mapping of each D1 practice into the architecture.
- R7 (§4 D5): Deliver D5 data model with typed fields and relationships for LearnerProfile, VocabularyItem (Unseen→Learning→Review→Mastered; SRS stability/difficulty/next_review), ErrorLog, TextbookUnit, Session, ReviewRecord; show how SRS uses VocabularyItem fields and how ErrorLog links to ReviewRecord and VocabularyItem.
- R8 (§4 D6): Deliver D6 six flows — textbook unit → SRS; Oxford word lookup → SRS; daily review; 5-minute microlearning; TBLT session; error-journal remediation — each naming agents and data read/write and the D1 practice served; Mermaid sequence diagrams for TBLT and daily review.
- R9 (§4 D7): Deliver D7 prompt pack: Router, Tutor (RAG textbook), Vocabulary (Oxford-only definitions, no invented defs), Review (formative feedback tied to source), CEFR limiter (i+1 mixer), Context Generator; each with role, variables, rules, output format, anti-hallucination/CEFR limits; 2–3 few-shot examples per prompt in the document.
- R10 (§4 D8): Deliver D8 roadmap MVP (Router + Tutor + Vocabulary + simple SRS + CEFR templates + error log; Angular client + Python 3.13 server + Docker Compose per R15–R17) → Stage 2 (Review, TBLT, microlearning, formative assessment) → Stage 3 (voice, authentic tasks, Critic, Anki export) with tasks, DoD, success metrics, effort ranges, dependencies, and explicit MVP anti-scope.
- R11 (§4 D9): Deliver D9 risk register Risk → probability → impact → actionable mitigation covering at least Oxford API limits/cost, LLM hallucinations, learner overload, textbook RAG quality, LLM scale cost, missing Oxford CEFR tags, SRS miscalibration; call out MVP-blocking risks.
- R12 (§5, §9): Work in phases — A: D1–D3; B: D4–D7; C: D8–D9 — with a self-review after each phase. Deliver Phase A as the same document skeleton with sections 1–3 filled and marked «Фаза A — на ревью». Do not start D4–D9 until Phase A is confirmed.
- R13 (§6): Final package is one Russian-language document with structure §0 Executive Summary through §10 Appendices; professional tone; every decision with rationale and trade-off; Mermaid or text diagrams; concrete JSON/prompt/table examples; no filler sections.
- R14 (§7): Package is done when: MVP can start without further research; all nine deliverables meet their acceptance criteria; every D1 practice traces to a concrete D4/D6/D7 component; roadmap has measurable DoD and anti-scope; mitigations are actionable; Executive Summary supports a five-minute owner decision.
- R15 (owner 2026-10-20): The designed MVP is a client-server application that a developer can run locally with Docker Compose.
- R16 (owner 2026-10-20): The designed MVP server uses Python 3.13 with ruff (lint + formatter) and mypy as required quality gates in the roadmap and architecture.
- R17 (owner 2026-10-20): The designed MVP client is an Angular web app with a complete code-quality toolchain (lint, format, typecheck, and related quality scripts as recommended in D3/D8).
- R18 (owner 2026-10-20): The designed MVP can ingest textbook PDFs including scanned pages (OCR and layout recovery), not only born-digital text PDFs; Phase A D3 researches and recommends the approach with explicit trade-offs.

## Constraints

- C1 (§3.2): No production code in this initiative.
- C2 (§3.2): No visual UI/UX design — scenario and screen logic only.
- C3 (§3.2): No legal opinion on Oxford API licenses — risk flags only.
- C4 (§3.2): No marketing or monetization work.
- C5 (§8): Learner-facing explanations in Russian; target language English.
- C6 (§8): Moderate LLM budget — prefer strong price/quality models.
- C7 (§8): Architecture must allow adding textbooks beyond the one primary book.
- C8 (§9): Phase B and C must not begin until Phase A review is confirmed.
- C9 (owner 2026-10-20): D3, D4, and D8 treat Docker Compose local deploy, Python 3.13 server toolchain (ruff lint/format, mypy), and Angular web client as MVP baseline; alternatives only as documented trade-offs, not silent defaults.

## Done when

1. All nine deliverables (D1–D9) exist and meet the brief’s acceptance criteria (R3–R11, R14).
2. Phase A package was reviewed and confirmed before Phase B/C content was written (R12, C8).
3. Every D1 practice traces to a named architecture/flow/prompt component (R6, R8, R9, R14).
4. Roadmap includes measurable DoD, metrics, effort ranges, dependencies, MVP anti-scope, and the client-server Docker Compose / Python 3.13 / Angular baseline (R10, R15–R17).
5. Risk register has actionable mitigations and calls out MVP blockers (R11).
6. Executive Summary enables a five-minute go/no-go decision (R13, R14).

## Boundaries

- In: research, competitive analysis, tech selection, system design, data model, flows, prompts, roadmap, and risks for the AI English learning agent.
- Out: production code; visual UI/UX; Oxford license legal counsel; marketing and monetization.
- Out: building the product itself — that is a follow-on build initiative after this package is accepted.
- Touch point: Oxford Dictionaries API — documented and field-scoped here; access and contract remain with the owner (A1).
- Touch point: primary textbook content — assumed provided as PDF (including scans); ingestion/OCR/RAG design is in scope, content licensing is not.
- Touch point: MVP runtime — Angular web client + Python 3.13 API, local via Docker Compose (R15–R17); Telegram bot is not MVP unless re-added.
- Tracer path: Phase A (practices + competitors + stack) → Phase B (architecture, data, flows, prompts) → Phase C (roadmap + risks) → owner go/no-go → build initiative.

## References

- brief — `_bmad-output/initiative-research/brief-research/brief-research.md` (§1–§9)

## Notes

- Assumption: A1 (§8) — Owner will provide or confirm Oxford Dictionaries API access before MVP.
- Assumption: A2 (§8, revised) — One primary textbook will be named. MVP delivery shape is Angular web + Python 3.13 server via Docker Compose (R15–R17); brief’s Telegram-or-web option is superseded for MVP.
- Decision: 2026-10-20 — Adopted `brief-research/brief-research.md` as the sole source; closed prior open questions about subject and input.
- Decision: 2026-10-20 — First buildable work after Requirements approval is Phase A (D1–D3) only, per R12/C8.
- Decision: 2026-10-20 — Owner fixed MVP baseline: client-server, Docker Compose local deploy; Python 3.13 + ruff (lint/format) + mypy; Angular web with full quality toolchain (R15–R17, C9).
- Decision: 2026-10-20 — Owner confirmed Requirements scope; sliced into three epics by brief phase gates (A research D1–D3 → B design D4–D7 → C roadmap/risks/final package). Exec Summary + appendices assemble in Phase C.
- Decision: 2026-10-20 — MVP must parse textbook PDFs including scans (R18); D3 covers PDF/OCR stack. Phase A stories (6) approved in draft; later refined to 7 entries after PRD + deep-recon.
- Decision: 2026-10-21 — Epic Phase A refined (`refined: true`); Free Dictionary primary for lexicon; Oxford runner-up pending T&Cs; threshold spike before D1.
