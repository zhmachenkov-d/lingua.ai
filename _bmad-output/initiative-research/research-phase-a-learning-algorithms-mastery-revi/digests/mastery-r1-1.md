# Digest: mastery-r1-1

**Decision served:** Select a word-mastery / "learned word" algorithm for adult English self-study with spaced practice.  
**Epistemics:** Claims below are grounded only in sources retrieved this run (accessed:2026-10-20). No project context used.  
**Budget:** 8 search calls; 8 distinct sources read.

---

## Findings

### Spaced-repetition “mastery” / graduation (scheduling states)

- **claim:** SM-2 has no explicit “mastered” flag; success is continuous scheduling. After quality *q* &lt; 3, the item restarts from I(1)=1 day / I(2)=6 days without changing E-Factor; session-local items with *q* &lt; 4 are re-drilled until *q* ≥ 4. E-Factor floor is 1.3. Woźniak reported ~92% retention when excluding recently memorized items with intervals below 3 weeks.  
  **source URL:** https://www.super-memory.com/english/ol/sm2.htm  
  **publisher:** SuperMemo / P.A. Woźniak (adapted from master’s thesis)  
  **pub_date:** 1990 (thesis); web adaptation noted 1998-05-10  
  **accessed:** 2026-10-20  
  **confidence:** high  
  **class:** primary algorithm spec (seminal; not peer-reviewed journal article)

- **claim:** In Anki, a card “graduates” from learning to review when the learner presses Good on the final learning step, or Easy at any learning step. Lapses return a review card to relearning until relearning steps complete. This is a state transition, not a linguistic mastery judgment.  
  **source URL:** https://docs.ankiweb.net/faqs/what-spaced-repetition-algorithm  
  **publisher:** Anki / Ankitects (official docs)  
  **pub_date:** living documentation (fetched 2026-10-20; describes Anki ≥23.10 dual SM-2/FSRS)  
  **accessed:** 2026-10-20  
  **confidence:** high  
  **class:** official product documentation

- **claim:** Anki’s statistics treat a review card as “mature” when its interval is ≥21 days (young: interval &lt;21 days). True Retention counts Again as Fail and Hard/Good/Easy as Pass (first review per day). Under FSRS, true retention is expected to track the user’s *desired retention*; mismatch prompts parameter optimization / presets / leech handling—not a binary graduate rule.  
  **source URL:** https://docs.ankiweb.net/stats.html  
  **publisher:** Anki / Ankitects (official docs)  
  **pub_date:** living documentation (fetched 2026-10-20)  
  **accessed:** 2026-10-20  
  **confidence:** high  
  **class:** official product documentation

- **claim:** FSRS models each card’s memory state as Difficulty (D), Stability (S), and Retrievability (R). S is the time (days) for R to fall from 100% to 90%; scheduling targets a chosen desired retention (commonly ~80–95%). FSRS does not define a separate “mastered/graduated forever” criterion—items remain scheduled while R decays. D ∈ [1,10]; grades 1–4 update S and D.  
  **source URL:** https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm  
  **publisher:** open-spaced-repetition (Jarrett Ye et al.; official FSRS wiki)  
  **pub_date:** wiki page current as of fetch (Ye edits noted into 2026 on related wiki pages)  
  **accessed:** 2026-10-20  
  **confidence:** high  
  **class:** official algorithm documentation (implementation primary); peer-reviewed origins cited elsewhere as Ye et al. KDD 2022 (not fully read this run)

- **claim:** Anki’s FSRS FAQ mirrors the DSR definitions and states that after at least one review a card gets DSR values; Again → relearning + large S drop / D rise; Hard/Good/Easy adjust S/D without a terminal mastery state. Users should set desired retention rather than hand-tune parameters.  
  **source URL:** https://docs.ankiweb.net/faqs/what-spaced-repetition-algorithm  
  **publisher:** Anki / Ankitects  
  **pub_date:** living documentation  
  **accessed:** 2026-10-20  
  **confidence:** high  
  **class:** official product documentation

### Measuring vocabulary learning success (surveys / assessment)

- **claim:** A 2024 methodological review of measuring vocabulary *growth* argues that success measurement must satisfy validity, reliability, and practicality; distinguish breadth vs depth, receptive vs productive, recognition vs recall; and watch sampling rate (≈30 items per 1k frequency band recommended) and cognate/loanword bias. Common instruments: VLT/UVLT, VST, CATSS (four form–meaning strengths), checklists. Longitudinal L2 vocabulary growth research remains sparse; recognition tests may overestimate, recall underestimate.  
  **source URL:** https://doi.org/10.29140/vli.v13n2.1604  
  **publisher:** Vocabulary Learning and Instruction (Castledown)  
  **pub_date:** 2024-09-17  
  **accessed:** 2026-10-20  
  **confidence:** high  
  **class:** peer-reviewed methodological survey (≤12 mo at access date)

- **claim:** Lexical Quality Hypothesis: high-quality word knowledge = well-specified, partly redundant orthography/phonology plus flexible semantics enabling rapid, reliable meaning retrieval; low quality causes form–meaning confusions and comprehension cost. “Mastery” in this frame is multi-dimensional representation quality, not a single SRS interval.  
  **source URL:** https://doi.org/10.1080/10888430701530730  
  **publisher:** Scientific Studies of Reading (Taylor & Francis)  
  **pub_date:** 2007-09-26 (online); Perfetti  
  **accessed:** 2026-10-20  
  **confidence:** high (abstract + secondary confirmation; full PDF not exhaustively re-read)  
  **class:** peer-reviewed seminal theory paper

### Frequency / CEFR-linked thresholds (curriculum “mastery,” not per-item SRS)

- **claim:** Nation (2006): if ~98% coverage is required for unassisted comprehension, learners need ~8,000–9,000 word families for written English and ~6,000–7,000 for spoken. Frequency-band coverage is a *size/comprehension* criterion, not a per-word stability estimate.  
  **source URL:** https://lextutor.ca/cover/papers/nation_2006.pdf (CMLR 63.1)  
  **publisher:** Canadian Modern Language Review / University of Toronto Press  
  **pub_date:** 2006-09  
  **accessed:** 2026-10-20  
  **confidence:** high  
  **class:** peer-reviewed seminal empirical paper

- **claim:** Milton (EuroSLA monograph chapter): vocabulary breadth can be tied to CEFR levels with language-dependent size estimates; e.g., ~2,000 of the most frequent 5,000 associated with A2-type performance across some tests; ~3,000 of top 5,000 for moving beyond elementary; C1/C2 associated with near-complete recognition of the most frequent 5,000—aligning directionally with Nation’s large size goals. Estimates vary by L2 and word source; samples often small—caution warranted.  
  **source URL:** http://www.eurosla.org/monographs/EM01/211-232Milton.pdf  
  **publisher:** EuroSLA Monographs  
  **pub_date:** chapter in EM01 (post-2001 CEFR era; PDF accessed 2026-10-20)  
  **accessed:** 2026-10-20  
  **confidence:** medium–high  
  **class:** peer-reviewed monograph chapter (seminal CEFR–VS linkage; not ≤12 mo)

### Trainable language-learning SRS with stability-like fields

- **claim:** Half-life regression (HLR) estimates each lexeme’s memory half-life *h* from practice features; recall probability *p* = 2^(−Δ/*h*). Compared with Leitner/Pimsleur/logistic baselines on Duolingo data, HLR cut recall-prediction MAE by 45%+ and improved daily engagement ~12% in a production study. Half-life is the stability analog; there is no published binary “graduated word” rule in the paper—scheduling follows predicted *p*.  
  **source URL:** https://aclanthology.org/P16-1174.pdf  
  **publisher:** ACL (Association for Computational Linguistics)  
  **pub_date:** 2016 (ACL proceedings)  
  **accessed:** 2026-10-20  
  **confidence:** high  
  **class:** peer-reviewed conference paper (seminal HLR; superseded in industry by later FSRS-class models for flashcards, still relevant for lexeme-tagged apps)

### Hard limits / assumptions (synthesized from the same sources)

| Approach | Hard limits / assumptions |
| --- | --- |
| **SM-2** | Assumes discrete quality grades and multiplicative intervals; *q*&lt;3 full reset can trap hard items; E-Factor heuristics; no probabilistic retention target; English-vocab anecdote retention ≠ validated L2 depth mastery. |
| **Anki graduate / mature** | Graduation = finished learning steps; mature = interval ≥21d reporting cutoff—not CEFR or lexical quality. Ease hell historically under SM-2; FSRS docs warn long learning steps distort first review. |
| **FSRS DSR** | Assumes review history + rating honesty; unitary memory item (one fact/card); ML parameters need data (defaults from large corpora otherwise); optimizes *schedule retention*, not productive use, collocations, or orthographic quality. Desired retention trades workload vs R. |
| **HLR** | Fit to Duolingo exercise logs (lexeme-tagged); half-life features may not transfer to pure flashcard apps without feature redesign; predicts recall, not depth/CEFR. |
| **Lexical quality** | Theoretical/psycholinguistic; no off-the-shelf S/D/next_review fields; hard to operationalize from binary correct/incorrect alone. |
| **Frequency / CEFR size** | Population/coverage thresholds, not per-item memory state; CEFR–VS mappings language- and test-dependent; adjacent CEFR levels often not statistically separable (noted in later VS–CEFR work surfaced in search snippets, not fully read). |

---

## Candidates (3–5)

Suitable for an app that already tracks **stability / difficulty / next_review**-style fields:

1. **FSRS-style DSR + desired-retention scheduling (primary scheduler)**  
   Map fields: `stability`←S, `difficulty`←D, `next_review`← time when predicted R equals target. Optional product “learned” UX: e.g., S ≥ N days *and* last k reviews pass—**product policy**, not part of FSRS core.

2. **SM-2 / Anki-like ease + learning graduation + mature threshold (legacy / interpretable)**  
   Map: ease↔E-Factor, graduate on completing learning steps, soft “learned” badge at interval ≥21d (Anki mature). Weaker probabilistic control than FSRS.

3. **Half-life regression (lexeme-aware, language-app native)**  
   Map: `stability`← half-life *h*, schedule when *p* near target; difficulty via feature weights / lexeme tags. Strong if you log exercise features beyond flashcard grades.

4. **Hybrid: SRS state + form–meaning strength gate (lexical-quality-lite)**  
   Keep FSRS/HLR for timing; declare “mastered for curriculum” only when multi-aspect checks pass (e.g., meaning recall + form recall / CATSS-style), addressing Albalawi/Perfetti gaps that pure R cannot close.

5. **Complementary frequency/CEFR band gates (not a scheduler)**  
   Use Nation coverage / Milton-style band targets to decide *what* enters the deck and when a *band* is curriculum-complete; do **not** confuse with per-word graduation—pair with candidate 1 or 3 for item timing.

**Practical shortlist for adult English self-study:** **(1) FSRS DSR** as core algorithm; **(4)** optional mastery badge; **(5)** for syllabus sizing; consider **(3)** if rich interaction logs beat pure grade history.

---

## Leads to chase

- Ye, Su, Cao (2022) KDD: *A Stochastic Shortest Path Algorithm for Optimizing Spaced Repetition Scheduling* — peer-reviewed FSRS/SSP origin (DOI surfaced: 10.1145/3534678.3539081); read for formal optimality claims vs Anki docs.
- FSRS-6 / ABC-of-FSRS wiki updates (2025–2026) for current parameter count and same-day review formulas.
- Wesche & Paribakht Vocabulary Knowledge Scale (VKS) primary paper — incremental self-report mastery stages (surfaced via secondary Reading Rockets summary; primary not read).
- Recent VS–CEFR EFL studies (e.g., IJAL 2025 DOI 10.1111/ijal.70313 snippets: receptive ~5.3k A1 → ~11.2k C2) — peer-reviewed, fresher than Milton; full text not read this run.
- Gyllstad et al. sampling-rate papers cited by Albalawi (2021) for operational “band mastered” test design.

---

## Looked for but not found

- A **consensus peer-reviewed definition** of “word mastered” that unifies FSRS/SM-2 states with CEFR descriptors (not found in the 8 sources).
- An **official FSRS “graduate/mastered” threshold** on Stability alone (docs schedule continuously via desired retention; no terminal mastered state).
- **SOTA ≤6 mo ML** paper comparing FSRS vs HLR specifically for *adult English vocabulary app* mastery UX (not retrieved within budget).
- Primary **Council of Europe CEFR** vocabulary size tables defining per-level word counts (Milton notes CEFR itself does not fully specify VS; empirical attachments vary).
