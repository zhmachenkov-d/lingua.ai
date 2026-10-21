---
type: epic
title: "Phase B — Design package (D4–D7)"
parent: initiative-research
covers: ["R6", "R7", "R8", "R9", "R12", "R14"]
sources: []
companions: []
after: ["epic-phase-a-research"]
refined: false
risk: medium
---

# Phase B — Design package (D4–D7)

## Description

Design architecture, data model, user flows, and prompts from confirmed Phase A findings. Every D1 practice must map to a concrete architecture component, flow, or prompt.

## Outcome

Builders have implementable design specs (D4–D7) grounded in the researched practices and stack.

## Done when

1. D4–D7 meet brief acceptance criteria (R6–R9).
2. Each D1 practice traces to a named D4/D6/D7 component (R14).
3. Architecture and flows assume Angular client + Python 3.13 server (R15–R17) without reopening the baseline except as documented trade-offs (C9).
4. Self-review: design is enough to plan MVP implementation.

## Boundaries

- In: D4 architecture, D5 data model, D6 flows, D7 prompts.
- Out: D8–D9 (Phase C); production code; work before Phase A confirmation (C8).
- Waits on epic-phase-a-research because: owner must confirm D1–D3 first.

## References

- parent — `_bmad-output/initiative-research/initiative-research.md`, Requirements R6–R9, R12, R14
- brief — `_bmad-output/initiative-research/brief-research/brief-research.md`, §4 D4–D7, §5 Phase B
- after — `_bmad-output/initiative-research/tickets/epic-phase-a-research/epic-phase-a-research.md`

## Notes

- Decision: 2026-10-20 — Starts only after Phase A owner confirmation (R12, C8).
