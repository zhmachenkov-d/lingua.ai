# Digest: review-r1-1

**Decision served:** Select an automatic review/reinforcement scheduling algorithm for lessons/topics (not only flashcards), for adult language self-study with learner-set rhythm and sequential lesson progression.

**Access date for all URLs:** 2026-10-20  
**Method:** Web search only; max 8 sources; no project/product context used as evidence.

---

## Findings (claim + source URL + publisher + pub_date + accessed:2026-10-20 + confidence + class)

1. **Spacing + retrieval practice improve long-term retention and transfer beyond lab flashcards; they apply in educational settings and to self-regulated learning, but learners underuse them.** Successive/relearning paradigms show repeated spaced retrieval of the *same content*, not only single-trial cards. There is no single “optimal” inter-session gap—any spacing beats massing; schedules can flex to learner calendars.
   - Source: https://www.nature.com/articles/s44159-022-00089-1  
   - Publisher: Nature Reviews Psychology (Springer Nature)  
   - Pub_date: 2022-08-02 (peer-reviewed review)  
   - Accessed: 2026-10-20  
   - Confidence: **high** | Class: **seminal survey (≤5y)**  
   - Implication for lessons/topics: treat a lesson/topic as a *retrieval unit* (questions, tasks, re-performance), schedule short effortful reviews over days/weeks, and allow learner rhythm without hunting a magic interval.

2. **Spaced retrieval strongly beats massed retrieval (meta g ≈ 0.74), but expanding intervals are *not* reliably superior to equal/uniform intervals overall (g ≈ 0.034 n.s.); expanding helps mainly when there are more retrieval exposures.**
   - Source: https://link.springer.com/article/10.1007/s10648-020-09572-8  
   - Publisher: Educational Psychology Review (Springer)  
   - Pub_date: 2020-10-07 (peer-reviewed meta-analysis; correction noted 2021-06-29)  
   - Accessed: 2026-10-20  
   - Confidence: **high** | Class: **seminal meta**  
   - Implication: calendar “1-3-7-14” topic review is a convenience heuristic, not a settled optimality claim; prefer *spaced, repeated retrieval* over rigid expanding formulas.

3. **In TBLT/task-repetition with adult L2 learners, repeating the same speaking task helps CAF overall; spacing *mediates which* gains appear—short/immediate gaps favor speed fluency; ~1-week gap favored structural complexity and repair fluency in this study.**
   - Source: https://doi.org/10.1016/j.system.2018.12.006 (author MS: https://eprints.whiterose.ac.uk/id/eprint/139941/2/System_FinalV.pdf)  
   - Publisher: *System* (Elsevier)  
   - Pub_date: 2019-04 (online 2018-12; peer-reviewed)  
   - Accessed: 2026-10-20  
   - Confidence: **medium-high** (single study, n≈71, power limits noted by authors) | Class: **seminal empirical (TBLT spacing)**  
   - Implication: lesson/topic “review” for language should often be *task re-performance / communicative reuse*, not only item recall; different goals (fluency vs complexity) may want different gaps.

4. **SOTA systematic review of oral task-repetition research (1996–2023) finds weak systematicity in how studies choose spacing intervals, repetition count, and reporting; calls for stronger theoretical rationales for interval choice.**
   - Source: https://doi.org/10.1177/13621688251323047  
   - Publisher: Language Teaching Research (Sage)  
   - Pub_date: 2025-03-25 (peer-reviewed systematic review; SOTA ≤12mo)  
   - Accessed: 2026-10-20  
   - Confidence: **high** (methods synthesis) | Class: **SOTA survey**  
   - Implication: do not overfit a product scheduler to any one TBLT spacing “recipe”; document assumptions and measure CAF-like outcomes.

5. **Interleaving (alternating categories/skills within practice) is theoretically distinct from spacing (rest gaps); interleaving aids discrimination between similar concepts. For adult/college Romance grammar, interleaved practice improved conjugation and (in some expts) tense/language identification vs blocked practice (1-week delayed tests).**
   - Source: https://doi.org/10.31234/osf.io/bnky8 (author PDF: https://sc-pan.github.io/pdf/PRKL_2024.pdf)  
   - Publisher: PsyArXiv / OSF  
   - Pub_date: 2024 (preprint — **not** treated here as peer-reviewed final)  
   - Accessed: 2026-10-20  
   - Confidence: **medium** (multi-expt adult samples; preprint status) | Class: **preprint empirical**  
   - Implication for topic review: when reviewing completed lessons that share confusable forms (tenses, patterns), *mix* topics in a session rather than pure blocked re-study of one lesson.

6. **Adaptive spacing that uses ongoing accuracy + response time (ARTS) outperforms fixed expanding/equal and random schedules; advantages hold when learning continues to mastery criteria and when mastered items drop out.**
   - Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC8324179/  
   - Publisher: *npj Science of Learning* (via PMC; Nature Portfolio)  
   - Pub_date: 2021 (peer-reviewed; PMCID PMC8324179)  
   - Accessed: 2026-10-20  
   - Confidence: **high** for item-level adaptive spacing + mastery | Class: **seminal empirical**  
   - Implication: mastery gates alone are insufficient; *how* you space during learning to criterion matters. Grain of “item” in these studies is still typically discrete learning items, not whole lessons—extrapolation needed.

7. **Production-scale item SRS can be cast as memory-model + cost-optimized scheduling (Markov/DHP-style memory; stochastic shortest path). Deployed for language vocabulary at large scale with reported review-cost gains vs prior SOTA.**
   - Source: https://doi.org/10.1145/3534678.3539081  
   - Publisher: ACM KDD 2022  
   - Pub_date: 2022-08-14 (peer-reviewed conference)  
   - Accessed: 2026-10-20  
   - Confidence: **high** for *item/vocab* scheduling; **low–medium** for whole-lesson units (not the paper’s unit of analysis) | Class: **seminal applied ML (FSRS/MaiMemo lineage)**  
   - Implication: FSRS-class algorithms are strong candidates for *atomic* language items (lemmas, cards, micro-skills) with graded reviews; they are a poor default sole scheduler if the product’s primary unit is a multi-skill lesson/topic unless you decompose lessons into schedulable items.

8. **In adaptive mastery systems, a higher mastery threshold reduces early forgetting, but the advantage shrinks over weeks; authors recommend combining mastery with distributed / retrieval practice rather than only raising the gate.**
   - Source: https://jedm.educationaldatamining.org/index.php/JEDM/article/view/900  
   - Publisher: Journal of Educational Data Mining  
   - Pub_date: (randomized follow-up to EDM mastery-threshold work; peer-reviewed JEDM article—exact issue date not fully visible in open abstract scrape; content aligns with 2020s ALEKS A/B follow-up)  
   - Accessed: 2026-10-20  
   - Confidence: **medium** (domain = math/chem adaptive tutors, not L2; open abstract confirms direction) | Class: **applied mastery evidence**  
   - Cross-check abstract claim also appears in related EDM 2022 short paper synthesis from search: higher mastery → better short-term retention, difference fades; distribute extra practice.  
   - Implication: sequential lesson unlock-by-mastery without post-mastery spaced retrieval is a retention risk for adult self-study.

---

## Candidates (3–5) with trade-offs

| # | Candidate | Fit to decision | Strengths | Weaknesses / trade-offs | Manual review of completed lessons |
|---|-----------|-----------------|-----------|-------------------------|-------------------------------------|
| A | **FSRS-/DSR-driven item review only** | Strong for vocab/micro-items; weak as sole lesson scheduler | Best-evidenced cost/retention optimization at *card* grain (KDD 2022 lineage); desired-retention dial; adapts to ratings | Does not schedule whole lessons/topics; ignores task-repetition CAF goals; needs dense graded feedback; sequential curriculum not modeled | Advanced/late reviews can feed the model if graded; unstructured rereads without grades add noise or no update |
| B | **Calendar / fixed–expanding spaced topic review** | Good UX for learner-set rhythm + lesson units | Matches practitioner “review last lesson / last week” spacing; flexible to adult calendars; no need for item logs (Carpenter 2022; Latimier: spacing > massing) | Expanding ≠ proven optimal vs equal (Latimier); no item difficulty adaptation; risk of passive re-reading unless retrieval tasks attached | Easy to allow voluntary open-lesson review; risk of *massing* if manual + calendar collide—cap or log sessions |
| C | **Mastery-based progression (gate then unlock next)** | Aligns with sequential lessons | Clear progression; remediation until criterion (tutor literature) | Mastery without later spaced retrieval → forgetting gap grows (JEDM/ALEKS-pattern evidence); threshold choice unstable over long delays | Manual re-open of “mastered” lessons can help if cast as retrieval/tasks; may undermine “done” psychology if overused |
| D | **Hybrid (recommended direction):** mastery/sequence gate for *forward* progress + spaced **topic/task** reviews + optional FSRS for atomic items | Best match to adult L2 self-study with lessons + rhythm | Combines progression (C), durable retention (spacing findings), TBLT task re-performance (Bui), and item efficiency (Ye) where cards exist; interleaving of confusable topics in review sessions (Pan preprint) | Highest product complexity; need policies for due-load vs learner rhythm; define lesson→item decomposition and success signals for topics | Treat manual review as *credited retrieval* (update schedule) or as *practice mode* (no interval reset)—must pick one to avoid schedule thrash |
| E | **Adaptive RT+accuracy sequencing (ARTS-like) at item/skill grain during learning** | Strong during acquisition to criterion | Beats fixed/random including under mastery+dropout (Mettler 2021) | Needs interactive trials with timing; less clear for offline lesson video/read units; still not TBLT-native | Manual browse doesn’t supply RT signals—keep ARTS for in-app drills only |

**Decision-leaning synthesis (evidence-bound):** Prefer **Candidate D (hybrid)**. Literature does not support FSRS-alone for lesson/topic units, nor mastery-alone for long-term retention, nor expanding calendars as uniquely optimal—but strongly supports (1) spaced effortful retrieval of content, (2) task repetition with intentional gaps for oral skill, (3) adaptive item spacing when discrete items exist, (4) interleaving when discrimination matters.

---

## Leads to chase

- Peer-reviewed final version + venue of Pan et al. interleaving Romance grammar (2024 preprint → journal?).
- Su et al. IEEE TKDE 2023 (“Optimizing Spaced Repetition Schedule by Capturing the Dynamics of Memory”) for FSRS/DHP formal link beyond KDD 2022.
- Full text of Rogers (2025) Language Teaching Research synthesis for recommended spacing reporting standards.
- DeKeyser skill-acquisition / automatization reviews on *distributed practice for procedural L2 skills* (cited in related SSLA spacing work; not retrieved as primary this run).
- Chen et al. Educ Psych Review systematic review: spacing vs interleaving distinct mechanisms (surfaced in search; not counted in the 8 if not fully read—chase for product design of “review mix”).
- Empirical studies scheduling **whole lessons/modules** (not items) with adaptive algorithms—likely thin.

---

## Looked for but not found

- A peer-reviewed head-to-head of **FSRS vs calendar topic review vs mastery gates** on *lesson-sized* L2 curriculum units.
- Clear SOTA (≤12mo) algorithm paper that schedules **multi-skill lessons** (vs flashcards/vocab) for adult self-study.
- Strong evidence that expanding calendars beat equal spacing specifically for **language lesson** review (meta argues against a general expanding advantage).
- Direct guidance in TBLT literature specifying an automatic scheduler for *sequential courseware* with learner-set daily rhythm (Rogers 2025 instead highlights methodological gaps).
- Settled policy for how **manual/voluntary review** should update automatic schedules (advance, delay, reset, or ignore)—not resolved in retrieved sources for lesson units (item SRS products often allow free timing; lesson products lack analogous evidence).
