---
title: 'academic-lit research: Phase A learning algorithms (mastery, review, remediation)'
type: 'academic-lit'
topic: 'Phase A learning algorithms: mastery, review, remediation'
decision: 'Select word mastery algorithm, auto review/reinforcement scheduler, and frequent-error remediation pattern for textbook-led adult English self-study'
source: 'run'
status: complete
preset: 'standard'
validation: 'normal'
created: '2026-10-20'
updated: '2026-10-20'
---

# academic-lit research: Phase A learning algorithms (mastery, review, remediation)

**Decision this research serves:** Select (1) word / **Learned Word** mastery algorithm, (2) automatic review/reinforcement scheduling algorithm, (3) frequent-error remediation pattern (Review Lesson vs Vocab Session vs inject into later lessons vs mix) for an adult self-study English agent with a textbook spine.

## Executive summary

**Do this:** (1) Schedule vocabulary with **FSRS DSR** (stability / difficulty / retrievability → `next_review`); treat “Learned Word” as a **product policy badge** on top of FSRS (e.g. stability and recent pass streak)—not a native FSRS terminal state [1][2][3]. (2) For lessons/topics use a **hybrid**: sequential Next-Lesson progression + spaced effortful **topic/task** reviews + FSRS for atomic items—not FSRS-alone on whole lessons and not mastery-gate-alone [4][5][6][7]. (3) Remediate frequent errors with a **mix**: short dedicated Review Lesson (grammar/system) or Vocab Session (lexical), then **spaced inject** into later lessons—avoid massed-only blocked review [8][9][10].

**Caveat:** No peer-reviewed numeric “after N errors → remediate” trigger was found; threshold remains a product design choice to tune and measure [11].

## Requirements (select shape — agreed)

Hard gates: adult self-study; textbook spine; RU UI / EN target; named algorithm + metric; Python-later implementable.

Weighted preferences: published rationale; fit sequential Next Lesson; coexist with learner-set rhythm.

## Dimension: Word mastery / Learned Word

FSRS models memory as Difficulty, Stability, and Retrievability and schedules to a **desired retention**; it does **not** define a forever-mastered flag [1][2]. SM-2 / Anki “graduate” and “mature (≥21d interval)” are scheduling/reporting states, not linguistic mastery [3][12]. Vocabulary *assessment* literature separates breadth/depth and receptive/productive measures; Lexical Quality is multi-dimensional, not a single interval [13][14]. Frequency/CEFR size targets (Nation, Milton) govern syllabus coverage, not per-item graduation [15][16]. HLR is a strong lexeme-level alternative where rich exercise features exist [17].

**Select verdict — mastery:** Pick **FSRS DSR** as the scheduler (map to stability/difficulty/next_review). Define **Learned Word** as an explicit product rule (e.g. S above a chosen floor *and* last *k* successful retrievals across required drill modalities). Optional later: multi-aspect form–meaning gate (lexical-quality-lite). Runner-up: SM-2 + mature badge if interpretability beats prediction. **Against the pick:** FSRS optimizes schedule retention, not productive use or collocations [1].

*Spot-check:* FSRS DSR definitions reconfirmed via Anki docs / FSRS wiki this run (status: verified against independent official docs) [1][2].

## Dimension: Automatic review / reinforcement (lessons & topics)

Spacing and retrieval practice improve long-term retention; expanding intervals are **not** reliably better than equal spacing overall [4][5]. TBLT task-repetition benefits adults; spacing mediates which CAF gains appear; interval choice in the literature is weakly systematized [6][18]. FSRS-class optimizers excel at **item** grain, not multi-skill lessons as atomic units [7]. Mastery gates without later distributed practice risk later forgetting [19]. Interleaving helps discrimination of confusable forms (preprint; medium confidence) [20].

**Select verdict — review scheduling:** Pick **hybrid**: (a) sequential curriculum gate for forward progress, (b) spaced topic/task retrieval reviews (effortful, not passive reread), (c) FSRS for vocabulary/micro-items, (d) interleave confusable topics in review sessions. Manual Review Lessons should be credited as retrieval (update schedule) or pure practice mode—pick one policy to avoid thrash. Runner-up: calendar spaced topic review alone (simpler, weaker adaptation).

## Dimension: Frequent-error remediation pattern

Corrective feedback has a medium durable effect; shorter targeted treatments can be potent [8]. Prompts / negotiation-of-form outperform recasts for learner-generated repair in classic classroom data [21]. Isolated and integrated form-focused instruction are **complementary** [9]. Spaced/distributed practice beats massed for L2 retention [10]. Immediate CF is often ≥ delayed; no universal timing winner [22][23]. Error journals support select→rewrite→new production, then recycling—not a fixed N-error trigger [11].

**Select verdict — remediation:** Pick **mix**: detect recurring/frequent error → short **Review Lesson** (grammar/systemic) or **Vocab Session** (lexical) → **inject** targets into later lessons on a spaced schedule → prefer prompt-style feedback when interactive. Do **not** rely on massed blocked review alone.

## Cross-dimension insights

FSRS is the right **item** engine for both Learned Word timing and vocab remediation drills, but lesson-level review and grammar remediation need **task/topic** scheduling and FFI mix logic—one algorithm cannot own all three decisions. Spacing evidence unifies review scheduling and remediation injection: whatever you isolate briefly must reappear distributed later [4][10].

## Recommendations (feeds Phase A D1 / PRD FR-10, FR-19, FR-24)

1. **FR-19 Learned Word:** Implement FSRS (e.g. `py-fsrs`) for item scheduling; document product badge rule + metric (e.g. retention at desired R; % words meeting badge). Confidence: **high** for scheduler; **medium** for exact badge thresholds (product choice).
2. **FR-10 Auto review:** Hybrid lesson/topic spaced retrieval + FSRS items; metric = delayed topic quiz / task re-performance success. Confidence: **high** for hybrid direction; **medium** for concrete calendar defaults.
3. **FR-24 Remediation:** Mix Review/Vocab + spaced inject by error type; metric = recurrence rate of error type after remediation window. Confidence: **high** for mix; **low** for numeric trigger (open).

## Open questions

1. Exact numeric trigger for “frequent” errors (not found in literature).
2. Exact Learned Word badge thresholds (S days, *k* passes, which drill modalities).
3. Policy: does manual Review Lesson advance/delay FSRS / topic schedule?
4. Head-to-head product RCTs of Review vs inject-only (not found).

## Source appendix

| Ref | Supports | Publisher | Pub date | Accessed | Confidence |
|---|---|---|---|---|---|
| [1] | FSRS DSR model; no terminal mastered state | [open-spaced-repetition FSRS wiki](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm) | living / 2026 | 2026-10-20 | high |
| [2] | Anki FSRS FAQ DSR + grades | [Anki docs](https://docs.ankiweb.net/faqs/what-spaced-repetition-algorithm) | living | 2026-10-20 | high |
| [3] | Anki mature ≥21d; retention stats | [Anki stats](https://docs.ankiweb.net/stats.html) | living | 2026-10-20 | high |
| [4] | Spacing/retrieval in education | [Carpenter et al. Nat Rev Psychol 2022](https://www.nature.com/articles/s44159-022-00089-1) | 2022-08 | 2026-10-20 | high |
| [5] | Spacing meta; expanding ≈ equal | [Latimier et al. Educ Psych Rev 2020](https://link.springer.com/article/10.1007/s10648-020-09572-8) | 2020-10 | 2026-10-20 | high |
| [6] | TBLT task repetition × spacing | [Bui et al. System 2019](https://doi.org/10.1016/j.system.2018.12.006) | 2019 | 2026-10-20 | medium-high |
| [7] | FSRS/SSP item scheduling at scale | [Ye et al. KDD 2022](https://doi.org/10.1145/3534678.3539081) | 2022-08 | 2026-10-20 | high |
| [8] | CF meta medium durable effect | [Li Language Learning 2010](https://doi.org/10.1111/j.1467-9922.2010.00561.x) | 2010 | 2026-10-20 | high |
| [9] | Isolated + integrated FFI complementary | [Spada & Lightbown TESOL Q 2008](https://doi.org/10.1002/j.1545-7249.2008.tb00115.x) | 2008 | 2026-10-20 | high |
| [10] | L2 spaced practice meta | [Kim & Webb Language Learning 2022](https://doi.org/10.1111/lang.12479) | 2022 | 2026-10-20 | high |
| [11] | Error diary pedagogy (no N-trigger) | [Stillwell MEXTESOL](https://www.mextesol.net/journal/public/files/045eeca337fc17c1d8d9ba7f002d3fe4.pdf) | n.d. | 2026-10-20 | lower |
| [12] | SM-2 algorithm spec | [SuperMemo SM-2](https://www.super-memory.com/english/ol/sm2.htm) | 1990/1998 | 2026-10-20 | high |
| [13] | Measuring vocab growth review | [Albalawi VLI 2024](https://doi.org/10.29140/vli.v13n2.1604) | 2024-09 | 2026-10-20 | high |
| [14] | Lexical Quality Hypothesis | [Perfetti 2007](https://doi.org/10.1080/10888430701530730) | 2007 | 2026-10-20 | high |
| [15] | Nation coverage / vocabulary size | [Nation 2006 PDF](https://lextutor.ca/cover/papers/nation_2006.pdf) | 2006 | 2026-10-20 | high |
| [16] | CEFR–vocabulary breadth | [Milton EuroSLA](http://www.eurosla.org/monographs/EM01/211-232Milton.pdf) | EM01 | 2026-10-20 | medium-high |
| [17] | Half-life regression Duolingo | [Settles & Meeder ACL 2016](https://aclanthology.org/P16-1174.pdf) | 2016 | 2026-10-20 | high |
| [18] | Task-repetition spacing review | [Rogers LTR 2025](https://doi.org/10.1177/13621688251323047) | 2025-03 | 2026-10-20 | high |
| [19] | Mastery threshold + distribute practice | [JEDM mastery follow-up](https://jedm.educationaldatamining.org/index.php/JEDM/article/view/900) | 2020s | 2026-10-20 | medium |
| [20] | Interleaving Romance grammar | [Pan et al. PsyArXiv 2024](https://doi.org/10.31234/osf.io/bnky8) | 2024 | 2026-10-20 | medium (preprint) |
| [21] | CF types & uptake | [Lyster & Ranta SSLA 1997](https://doi.org/10.1017/s0272263197001034) | 1997 | 2026-10-20 | high |
| [22] | CF timing systematic review | [Fu & Li Front Psychol 2023](https://doi.org/10.3389/fpsyg.2023.1026174) | 2023 | 2026-10-20 | high |
| [23] | CF timing survey | [Li Language Teaching 2025](https://doi.org/10.1017/S026144482400043X) | 2025 | 2026-10-20 | high |

## Staleness map

Fastest-aging: FSRS wiki/Anki docs (re-check ≤3–6 mo); Rogers 2025 / Kim & Webb spacing metas (≤12 mo for SOTA claims); classic FFI/CF papers stable as canon. Earliest refresh: algorithm docs + Anki FSRS FAQ.
