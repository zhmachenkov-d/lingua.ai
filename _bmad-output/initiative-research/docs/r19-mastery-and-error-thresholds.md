# R19 — Mastery and error-frequency thresholds

Owner-approved Phase A spike decisions (2026-10-21). D1 cites these for FR-19 Learned badge and FR-23 Teacher notify. Shape follows PRD §6.3 / recon: FSRS DSR schedules; Learned is a product badge on top; frequent-error uses mix remediation (FR-24).

## Learned Word badge (FR-19 / Q13)

A vocabulary item is **Learned** when **both** of these hold:

1. **Stability floor:** FSRS stability **S ≥ 21 days** (Anki “mature” ≥21d interval is the named analogy only—not a linguistic mastery claim).
2. **Last _k_ successes with modality spread:** the last **k = 3** successful retrievals include **≥ 3 distinct** of the six v1 drills (translate EN→RU, RU→EN, match, write, cloze, listen-and-spell).

Scheduling remains FSRS DSR; this badge does not replace difficulty / stability / next_review fields.

**Suggested D1 metric:** retention at desired retrievability R among badge-qualified words; % of active vocab meeting the badge.

## Frequent-error Teacher notify (FR-23 / Q14)

| Parameter | Value |
|-----------|--------|
| Trigger | **≥ 3 errors of the same error type within 7 days** |
| Scope | Lessons **and** Vocab Sessions |
| Action | Teacher Agent **in-app** notify: need review + Topic + error types (Telegram = Stage 2) |
| Remediation | Unchanged mix pattern (FR-24): short Review Lesson and/or Vocab Session + spaced inject |

No peer-reviewed N-error trigger exists; this is an MVP product policy to tune later (metric: error-type recurrence after remediation window).

## Cite from D1

Reference this note as **R19** when filling D1 rows for FSRS/Learned and error-based learning / remediation.
