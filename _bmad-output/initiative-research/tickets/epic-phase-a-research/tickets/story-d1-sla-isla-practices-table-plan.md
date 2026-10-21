---
title: "D1 SLA/ISLA practices table"
type: "chore"
ticket: "3"
created: "2026-10-21"
status: "built"
baseline_revision: "fbdd71569c5183eb0282e904d97e5b2f039"
route: "oneshot"
route_source: "auto"
risk: "medium"
review: "quick"
review_source: "pinned"
lenses_ran: ["quick"]
review_loop_iteration: 0
context:
  - "{project-root}/_bmad-output/initiative-research/brief-research/brief-research.md"
  - "{project-root}/_bmad-output/initiative-research/tickets/epic-phase-a-research/prd-phase-a-research/prd-phase-a-research.md"
  - "{project-root}/_bmad-output/initiative-research/research-phase-a-learning-algorithms-mastery-revi/research-phase-a-learning-algorithms-mastery-revi.md"
  - "{project-root}/_bmad-output/initiative-research/docs/r19-mastery-and-error-thresholds.md"
  - "{project-root}/_bmad-output/initiative-research/docs/research-package.md"
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Phase A research-package §1 (D1) is still `_Placeholder_`; R3 needs a Russian Practice → principle → agent → metric table for the brief’s ten SLA/ISLA practices, with FSRS/Learned and remediation aligned to PRD §6.3 and citing R19 thresholds.

**Approach:** Replace only §1 in `docs/research-package.md` with that table (plus a short source key), binding §6.3 algorithm picks and R19 numbers; leave §0 and §2–§10 unchanged (including the existing R19 appendix pointer).

</frozen-after-approval>

## Implementation Notes

Oneshot: docs-only fill of one Russian section (~10-row table + source key); no production code; risk medium because wrong algorithm/threshold wording misleads Phase B and owner go/no-go.

- Replaced `docs/research-package.md` §1 `_Placeholder_` with a 10-row Russian table (Practice → principle → agent → source → metric) covering the brief minimum list.
- Bound FSRS/Learned and error/remediation rows to PRD §6.3 + R19 (S≥21d, k=3, ≥3 modalities; ≥3 same-type errors / 7d); pointed source key at recon appendix [1]–[23].
- Left §0 and §2–§10 unchanged (including existing R19 appendix pointer); no «Фаза A — на ревью» mark.
- Review patch: fixed CEFR cites ([15][16][19] not [4]); sentence-based Nation [15]+Sinclair; microlearning Buchem & Hamelmann + [10]; named Teacher Agent/Lesson on explicit+implicit; ~90% i+1 gate; delayed CF policy; Russian metrics.

## Plan Change Log

## Review Triage Log

- 2026-10-21 quick: 7 findings → patched (medium): wrong recon [4] on CEFR; weak sentence/microlearning cites; missing component on explicit+implicit; underspecified ~90% and delayed CF; EN metrics vs RU package tone. All verified real and patched in §1.

## Verification

**Manual checks (if no CLI):**

- `docs/research-package.md` §1 is a table covering all ten brief practices (FSRS vs SM-2 rationale; i+1; TBLT; Focus on Form; error-based learning; microlearning; formative feedback; CEFR/mastery; sentence-based; explicit+implicit)
- Each row has principle, agent/component, verification metric, and a cited source
- FSRS/Learned and error/remediation rows cite R19 (`docs/r19-mastery-and-error-thresholds.md`) and match PRD §6.3 (FSRS DSR + badge; hybrid review; mix remediation)
- §2–§9 and §0 remain placeholders; §10 still points at the R19 note; no «Фаза A — на ревью» mark yet
