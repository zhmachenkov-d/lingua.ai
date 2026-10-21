---
title: Phase A research package (D1–D3)
status: final
created: 2026-10-20
updated: 2026-10-21
---

# PRD: Phase A research package (D1–D3)

_Coaching path: Vision + Features. Stakes: personal/solo. Companions: deep-recon Runs 1–3 (§6.3–6.5); tech/competitive detail in `addendum.md`._

## 0. Document Purpose

This PRD captures the learner-facing product vision that Phase A must make concrete enough for a personal go/no-go and handoff into design (Phase B). It builds on `initiative-research.md` and `brief-research.md`; it does not replace them. Exemplar textbooks live under `textbooks/` (English File Beginner PDFs, including scan-like files). Algorithm, stack, and competitive choices are owner-approved in §6.3–6.5.

## 1. Vision

As a learner, I can load my textbook into the app, follow a study schedule the teacher agent builds from that book (with review and reinforcement built in), and always know where I stand: which topics I’ve finished, where I make mistakes, and which words I’ve learned. When I err often, the teacher tells me what to review. The app reminds me about upcoming and missed lessons. I can start the next lesson in sequence (even if I skipped one), reopen a finished lesson for review, run a vocabulary practice session any time, and work words through translation, matching, writing, cloze, and listen-and-spell. I can practice listening (audition) and play back text as speech when I need to hear it. A word is **Learned** per FSRS scheduling plus a product badge rule (§6.3) — not a raw correct-count alone.

Phase A succeeds when this vision is concrete enough that I can decide whether to build: practices (D1), competitive landscape (D2), and stack including PDF/OCR of scans (D3) are written and marked «Фаза A — на ревью».

## 2. Target User

### 2.1 Jobs To Be Done

- Functional: study English from _my_ textbook with a clear next lesson and spaced word practice.
- Functional: see progress (topics done, error themes, learned words) without guessing.
- Emotional: feel guided (plan + reminders + teacher feedback) rather than lost after a miss.
- Contextual: personal solo use; Russian UI explanations, English as the target language (from initiative).

### 2.2 Non-Users (v1)

- Classroom teachers managing many students.
- Learners who want only free chat with no textbook spine. [ASSUMPTION: textbook-led path is the spine of v1.]

### 2.3 Key User Journeys

_Lighter (hobby/solo) — to expand if needed._

- **UJ-1. Learner uploads textbook and gets a plan.** I upload a PDF (including a scan from `textbooks/`), the system digests it, and the teacher agent proposes a schedule with review slots.
- **UJ-2. Learner does the next lesson.** I open the app, start only the next sequential lesson (even if I missed an earlier one), complete it, and see topic progress update.
- **UJ-3. Learner reviews after mistakes.** After frequent errors, I get teacher feedback (“need to review”), see which topics/errors, and can open a finished lesson for reinforcement.
- **UJ-4. Learner drills words anytime.** Outside a lesson I start a vocab session (EN→RU, RU→EN, match, write, cloze, listen-and-spell) and the learned-words list updates per the mastery rule.
- **UJ-5. Learner listens and hears text.** During study I do listening (audition) tasks and can play back lesson or word text as speech.

## 3. Glossary

- **Textbook** — A learner-uploaded PDF used as the spine of study; may be born-digital or scanned.
- **Lesson** — A scheduled study unit derived from the Textbook plan; has sequential order.
- **Next Lesson** — The earliest not-yet-completed Lesson in sequence; the only Lesson that may be _started as new study_ (missed prior lessons do not unlock later ones out of order).
- **Review Lesson** — A already-completed Lesson reopened for reinforcement.
- **Teacher Agent** — The agent role that plans study, gives review feedback on frequent errors, and drives lesson flow.
- **Topic** — A content unit inside the Textbook (e.g. unit/grammar theme) tracked as progressed or error-prone.
- **Learned Word** — A vocabulary item that meets the product **Learned** badge rule on top of FSRS DSR scheduling (§6.3; exact S/k thresholds named in D1/build).
- **Vocab Session** — An on-demand practice session of word drills, independent of Lesson schedule.
- **Audition** — Listening practice: the learner hears audio and responds (comprehension / discrimination), distinct from mere playback.
- **Text Playback** — On-demand speech (TTS or sourced audio) of written text (lesson lines, words, prompts) so the learner can hear it.
- **Material** — A learner-uploaded study asset: a Textbook PDF or an Audio file set, tracked with a status.
- **Ready** — Material status meaning ingest/processing finished and the Material may be used for planning and study.
- **Poor quality** — Material status meaning ingest refused because the scan/PDF is unusable (e.g. skewed, too dark); learner must re-upload.
- **Phase A Package** — Research document sections D1–D3 marked «Фаза A — на ревью».

## 4. Features

_All nine feature blocks drafted._

### 4.1 Textbook ingest

**Description:** The learner uploads each Textbook as its own Material (Student's book, Workbook, etc. are separate uploads). They can also upload Audio files for the course. Right after upload, the app warns that processing is long-running and may take a lot of time. When processing finishes, the Material status becomes **Ready** and the learner gets an in-app notification; a Telegram message is Stage 2. Unusable scans are refused with status **Poor quality** (no partial Ready). Realizes UJ-1. [ASSUMPTION: Audio uploads are course audio paired by the learner to a Textbook/course, not free-floating music.]

**Functional Requirements:**

#### FR-1: Upload textbooks separately

Learner can upload one Textbook PDF per Material; each Textbook is a separate Material (not a multi-file bundle in one upload). Realizes UJ-1.

**Consequences (testable):**

- Uploading Student's book and Workbook yields two Materials, each with its own status.
- A Material in non-Ready status cannot be used as the spine for a new study plan.

#### FR-2: Upload audio files

Learner can upload Audio files as Material(s) associated with their study content. Realizes UJ-1, UJ-5.

**Consequences (testable):**

- Audio Material appears in the library with status tracking like Textbook Materials.
- When Ready, audio is available as a source for Audition and Text Playback (alongside TTS).

#### FR-3: Long-running ingest warning

Immediately after a successful upload starts processing, the learner sees an explicit warning that the operation is long and may take a lot of time. Realizes UJ-1.

**Consequences (testable):**

- Warning is shown before or as processing begins, not only after failure.
- Warning copy states duration may be long (exact minutes TBD).

#### FR-4: Ingest completion signals (MVP)

When processing completes successfully, Material status becomes **Ready**, and the learner receives an in-app notification. Realizes UJ-1.

**Consequences (testable):**

- Status transitions to Ready only when processing succeeded.
- In-app notification fires on success.

#### FR-5: Telegram ingest completion (Stage 2)

When processing completes successfully, the learner also receives a Telegram message. Deferred from MVP.

**Consequences (testable):**

- On Stage 2, Telegram message fires in addition to FR-4.

#### FR-6: Refuse poor-quality scans

If the uploaded Textbook is a bad scan (e.g. skewed, too dark) and cannot be processed reliably, the system refuses the Material and sets status to **Poor quality**. Realizes UJ-1.

**Consequences (testable):**

- Status is **Poor quality**, not Ready; Material cannot be used for planning or study.
- Learner is informed they must re-upload a better file (in-app; same channel rules as FR-4/FR-5 for notify).

**Out of Scope for this feature:**

- Automatic purchase/download of publishers’ audio from the web.
- Legal licensing of uploaded PDFs/audio.
- Auto-enhancement / deskew of bad scans to force Ready.

### 4.2 Study plan & schedule

**Description:** After at least one Textbook Material is **Ready**, the Teacher Agent builds a study plan from that Textbook. The learner sets the study rhythm (when/how often). The learner can manually pick a completed Lesson as a **Review Lesson**. Automatic review/reinforcement uses the **hybrid** pattern in §6.3. Realizes UJ-1, UJ-2, UJ-3.

**Functional Requirements:**

#### FR-7: Plan only after Ready

Learner can create or regenerate a study plan only when the chosen Textbook Material status is **Ready**. Realizes UJ-1.

**Consequences (testable):**

- Plan actions are blocked for Materials in non-Ready statuses (including Poor quality).
- A plan references a Ready Textbook Material.

#### FR-8: Learner sets rhythm

Learner chooses the study rhythm (e.g. days/times or frequency); the plan respects that rhythm. Realizes UJ-1.

**Consequences (testable):**

- Changing rhythm updates upcoming scheduled Lessons without requiring a new Textbook upload.
- The system does not silently override the learner’s chosen rhythm. [ASSUMPTION: exact UI for rhythm — calendar slots vs frequency — to be designed in UX; both express FR-8.]

#### FR-9: Manual review of completed lessons

Learner can select an already completed Lesson and start it as a **Review Lesson**. Realizes UJ-3.

**Consequences (testable):**

- Only completed Lessons appear as Review Lesson candidates.
- Starting a Review Lesson does not change which Lesson is the **Next Lesson**.

#### FR-10: Automatic review/reinforcement (hybrid)

The system schedules automatic review/reinforcement using the hybrid pattern (§6.3): sequential **Next Lesson** gate + spaced topic/task retrieval + FSRS for atomic items. Realizes UJ-3.

**Consequences (testable):**

- Auto-review does not skip the Next Lesson sequential gate.
- Atomic vocab/micro-items use FSRS schedules; topic/task reviews are spaced retrieval, not FSRS-alone on whole Lessons.
- D1 names a verification metric (e.g. delayed topic re-performance).

**Out of Scope for this feature:**

- Teacher/admin assigning rhythm for multiple students.

### 4.3 Lesson playback

**Description:** The learner may start new study only on the **Next Lesson** (earliest incomplete Lesson in sequence), including when that Lesson was missed on the schedule. They may also open a completed Lesson as a **Review Lesson**. A Lesson is **completed** only when all planned material for it is done, all assignments are finished, and error remediation planned for that Lesson (if any) is done. Realizes UJ-2, UJ-3. Decision: a missed scheduled Lesson stays Next Lesson until completion criteria are met — does not skip ahead.

**Functional Requirements:**

#### FR-11: Start only Next Lesson for new study

Learner can start a Lesson as new study only if it is the **Next Lesson**. Realizes UJ-2.

**Consequences (testable):**

- Later incomplete Lessons are not startable as new study while an earlier one is incomplete.
- Missing a scheduled time does not unlock a later Lesson out of order.

#### FR-12: Start Review Lesson from completed

Learner can start a **Review Lesson** only from Lessons that already meet completion criteria. Realizes UJ-3.

**Consequences (testable):**

- Incomplete Lessons do not appear as Review Lesson targets.
- Review Lesson start does not advance or replace **Next Lesson**.

#### FR-13: Lesson completion criteria

A Lesson becomes completed only when: (1) all planned material for that Lesson is done, (2) all assignments for that Lesson are finished, and (3) error remediation for that Lesson is finished if it was planned. Realizes UJ-2.

**Consequences (testable):**

- Status does not become completed if any of (1)–(3) is incomplete when remediation was planned.
- If no error remediation was planned for the Lesson, (3) does not block completion.
- Completing the Next Lesson advances Next Lesson to the following incomplete Lesson in sequence.

**Out of Scope for this feature:**

- Skipping ahead by manually marking complete without meeting FR-13.

### 4.4 Progress & errors

**Description:** The learner sees Topics with completion status and, where relevant, whether errors exist and which **error types** they are. v1 does not require listing every mistaken utterance or raw error samples on this view. Realizes UJ-3.

**Functional Requirements:**

#### FR-14: Topic progress list

Learner can see Topics and whether each is progressed/completed. Realizes UJ-2, UJ-3.

**Consequences (testable):**

- Each Topic shows a clear progressed vs not (or equivalent) state.
- Completing a Lesson updates Topic progress for Topics covered in that Lesson.

#### FR-15: Errors by topic and type

Learner can see, per Topic, whether there are errors and which error types apply. Realizes UJ-3.

**Consequences (testable):**

- Topics with no errors show no error-type list (or an empty/none state).
- Topics with errors list type labels (not full transcript samples) on this view.

**Out of Scope for this feature:**

- Full error journal with every instance and timestamps on the progress screen (may live elsewhere later).

### 4.5 Vocabulary & mastery

**Description:** The learner sees a list of **Learned Words**, can start a **Vocab Session** at any time, and practices with drills: translate EN→RU, RU→EN, match translation to word, write the word, **cloze**, and **listen-and-spell**. Whether a word counts as Learned follows §6.3 (FSRS + product badge). Realizes UJ-4.

**Functional Requirements:**

#### FR-16: Learned words list

Learner can view the list of **Learned Words**. Realizes UJ-4.

**Consequences (testable):**

- Words that meet the mastery algorithm appear on the list.
- Words that do not meet it do not appear as Learned Words.

#### FR-17: Vocab Session anytime

Learner can start a **Vocab Session** independently of Lesson schedule. Realizes UJ-4.

**Consequences (testable):**

- Vocab Session is available even when no Lesson is in progress.
- Completing drills in a Vocab Session can update mastery toward Learned Word status per the algorithm.

#### FR-18: Core vocab drills

In a Vocab Session, learner can do: EN→RU translation, RU→EN translation, match translation to word, write the word, cloze (fill gap in a sentence), and listen-and-spell (hear audio, spell the word). Realizes UJ-4.

**Consequences (testable):**

- Each of the six drill types is available in v1.
- Listen-and-spell uses the same audio preference as Text Playback / Audition (course audio or TTS).

#### FR-19: Mastery algorithm (FSRS + Learned badge)

**Learned Word** status uses FSRS DSR for scheduling and a product **Learned** badge policy on top (§6.3). Library for build: `pip install fsrs` (§6.4). Realizes UJ-4.

**Consequences (testable):**

- Scheduling fields map to difficulty / stability / next_review (and retrievability as needed).
- Badge thresholds (e.g. stability floor + last _k_ successful retrievals) are named in D1 before product treats mastery as settled.
- Verification metric is named in D1 (e.g. retention at desired R; % words meeting badge).

### 4.6 Reminders

**Description:** The learner gets reminders for an upcoming Lesson and for a missed Lesson. MVP channel is in-app only; Telegram reminders are Stage 2 (same policy as ingest completion). Realizes UJ-2.

**Functional Requirements:**

#### FR-20: Upcoming lesson reminder (MVP in-app)

Learner receives an in-app reminder before a scheduled Lesson. Realizes UJ-2.

**Consequences (testable):**

- An upcoming scheduled Lesson produces an in-app reminder.
- Reminder identifies which Lesson is upcoming.

#### FR-21: Missed lesson reminder (MVP in-app)

Learner receives an in-app reminder when a scheduled Lesson was missed (not completed by schedule time) while it remains Next Lesson. Realizes UJ-2.

**Consequences (testable):**

- Missing the schedule without meeting FR-13 triggers a missed-lesson in-app reminder.
- Reminder does not unlock a later Lesson out of order.

#### FR-22: Telegram lesson reminders (Stage 2)

Learner also receives Telegram reminders for upcoming and missed Lessons. Deferred from MVP.

**Consequences (testable):**

- On Stage 2, Telegram reminders fire in addition to FR-20/FR-21.

### 4.7 Teacher feedback

**Description:** When the learner makes frequent errors, the **Teacher Agent** tells them they need to review and surfaces the relevant Topics / error types. Remediation follows the **mix** pattern in §6.3: short Review Lesson (grammar/system) or Vocab Session (lexical), plus spaced inject into later Lessons. Realizes UJ-3.

**Functional Requirements:**

#### FR-23: Frequent-error review signal

When error frequency crosses the (to-be-defined) threshold, Teacher Agent notifies the learner that review is needed and points to Topic + error types. Realizes UJ-3.

**Consequences (testable):**

- Notification references Topic and error types consistent with FR-15.
- Threshold and wording are named in D1 before build treats them as settled. [ASSUMPTION: exact frequency threshold is research output, not fixed in this PRD.]

#### FR-24: Remediation pattern (mix)

Remediation is delivered as a **mix** (§6.3): offer a short **Review Lesson** (grammar/system) or **Vocab Session** (lexical) by error type, and **spaced-inject** remediation into later Lessons. Realizes UJ-3.

**Consequences (testable):**

- Frequent-error flows can propose Review Lesson and/or Vocab Session; later Lessons may include injected remediation items.
- Massed-only blocked review without later spaced reappearance is not the default.
- Exact frequency threshold remains named in D1 (FR-23).

### 4.8 Audition

**Description:** The learner does listening practice: hears audio and responds (comprehension / discrimination). Distinct from Text Playback. Uses uploaded course audio when available, otherwise TTS. Primarily inside a Lesson. Realizes UJ-5. [ASSUMPTION: a separate anytime Audition session like Vocab Session is not required for v1.]

**Functional Requirements:**

#### FR-25: Audition exercises in Lesson

Learner can complete Audition tasks during a Lesson (hear → respond). Realizes UJ-5.

**Consequences (testable):**

- Lesson plan can include Audition tasks that block FR-13 completion until finished when planned.
- Audition is not satisfied by Text Playback alone.

#### FR-26: Audition audio source preference

Audition prefers uploaded course Audio Material when Ready and matched; otherwise uses TTS. Realizes UJ-5.

**Consequences (testable):**

- When course audio exists for the item, it is used before TTS.
- When it does not, TTS is used and the exercise still runs.

### 4.9 Text Playback

**Description:** The learner can play written text (lesson lines, words, prompts) as speech on demand. Prefers uploaded/Oxford course audio when available; otherwise TTS. Realizes UJ-5.

**Functional Requirements:**

#### FR-27: Tap-to-hear text

Learner can trigger playback of written study text (words or lesson lines). Realizes UJ-5.

**Consequences (testable):**

- Playback starts from the selected text without requiring an Audition response.
- Playback works in Lesson and Vocab Session contexts where text is shown.

#### FR-28: Playback audio source preference

Text Playback prefers uploaded course or Oxford audio when available; otherwise TTS. Realizes UJ-5.

**Consequences (testable):**

- Same preference order as FR-26 for consistency.
- Absence of course audio does not block playback (TTS fallback).

## 5. Non-Goals (Explicit)

- Production-code delivery and polished visual UI redesign (logic/scenarios only in this research track).
- Multi-student classroom / teacher admin.
- Telegram as an MVP client or MVP notification channel (Stage 2 for notify).
- Auto-enhancement of bad scans to force Ready.
- Legal opinion on textbook or Oxford licensing.
- Leaving mastery / auto-review / remediation algorithms undecided after Phase A.

## 6. MVP Scope

### 6.1 In Scope

- Textbook and audio Material ingest with long-running warning; Ready / Poor quality; in-app completion notify.
- Study plan only after Ready; learner-set rhythm; Next Lesson / Review Lesson; FR-13 completion rules.
- Progress: Topic status + error types; Vocab Session anytime + six drills (incl. cloze, listen-and-spell); Audition in Lesson; Text Playback with course audio or TTS.
- Teacher frequent-error review signal (Topic + types).
- Angular web + Python 3.13 + Docker Compose baseline (initiative); PDF/OCR including scans via Marker + Poor-quality gate (R18 / §6.4).
- Hybrid auto-review, FSRS+Learned badge, mix remediation (§6.3); D2 differentiation per §6.5.

### 6.2 Out of Scope for MVP (product build)

- Telegram notifications (Stage 2).
- Anytime Audition session (v1 Audition is in-Lesson).
- ELSA-class pronunciation scoring as a trust-critical gate (prefer dialogue + course/TTS audio unless scoring validated — §6.5).

### 6.3 Phase A algorithm decisions (owner approved 2026-10-20)

- **Learned Word** (FR-19): FSRS DSR for scheduling; Learned badge = product policy on top of FSRS (exact S/k thresholds TBD in D1/build).
- **Auto review** (FR-10): hybrid — sequential Next Lesson + spaced topic/task retrieval + FSRS for atomic items.
- **Remediation** (FR-24): mix — short Review Lesson (grammar/system) or Vocab Session (lexical) + spaced inject into later Lessons.

Source: `_bmad-output/initiative-research/research-phase-a-learning-algorithms-mastery-revi/`. Implementation follows roadmap after Phase A docs land.

### 6.4 Phase A tech decisions (owner approved 2026-10-21)

- **PDF/OCR (R18):** Marker (`marker-pdf`) + product-owned Poor-quality gate; ingest adapter with OCRmyPDF / Google Document AI as runner-ups.
- **FSRS library (R5 SRS):** `pip install fsrs` (OSR py-fsrs); runner-up `fsrs-rs-python` for Anki parity / torch-free optimize.
- **Remaining D3 rows:** criteria weights (ops 0.30, cost 0.25, RU 0.20, lock-in 0.15, maturity 0.10) + shortlists; lean bundle after Phase A RU scorecard spike (Q11 policy C) names LLM primary/runner-up · custom/thin LangGraph · pgvector · **Free Dictionary primary** (Oxford runner-up until owner reads display/redistribution T&Cs after signup) · defer ASR/TTS · Postgres+JSONB — owner may re-weight before D3 table lock.

Source: `_bmad-output/initiative-research/research-phase-a-d3-tech-pdf-ocr-fsrs-libs-stack/`. Implementation follows roadmap after Phase A docs land.

### 6.5 Phase A competitive decisions (owner approved 2026-10-21)

- **White space:** textbook spine (OCR) + dictionary-in-context + transparent FSRS + Teacher Agent — not owned as primary story by peers studied.
- **Primary borrow:** LingQ (input→tap-save); Anki/RemNote (FSRS + ownership); Quizlet (explicit SR); Busuu (CEFR/review tiers); Speak.com (Learn→Practice→Apply); ChatGPT Study Mode (upload-bound tutor); ELSA (dictionary pronunciation).
- **Primary avoid:** Duo energy/path locks; LingQ free vocab walls; ELSA scoring/billing distrust; ChatGPT as sole beginner grammar authority.
- **Applicable yes / strongest peers:** Busuu (mass), LingQ (workflow), Anki (SRS core), Speak.com (speak-ai), ChatGPT (teacher substrate).

Source: `_bmad-output/initiative-research/research-phase-a-d2-competitive-duolingo-anki-lin/`. ≥10 products carded (R4 ≥8). Implementation follows roadmap after Phase A docs land.

## 7. Success Metrics

**Primary**

- **SM-1**: Owner can run the personal loop — upload from `textbooks/` → Ready plan → Next Lesson → Vocab Session — without a dead end. Validates FR-1–FR-4, FR-7–FR-9, FR-11–FR-13, FR-16–FR-18.
- **SM-2**: Phase A package names algorithm (§6.3), tech (§6.4), and competitive (§6.5) choices with trade-offs and is marked «Фаза A — на ревью». Validates FR-10, FR-19, FR-24 and R3–R5/R18.

**Counter-metrics**

- **SM-C1**: Do not optimize for number of product features shipped before Phase A D1–D3 package is marked for review.

## 8. Open Questions

1. ~~Learned Word algorithm~~ — settled (recon Run1 / §6.3): FSRS DSR + product Learned badge (exact S/k thresholds → D1/build).
2. ~~Auto review/reinforcement~~ — settled (§6.3): hybrid sequential gate + spaced topic/task + FSRS items.
3. ~~Remediation pattern~~ — settled (§6.3): mix Review Lesson / Vocab Session + spaced inject.
4. ~~Extra vocab drills~~ — settled: cloze + listen-and-spell (six drills in v1).
5. ~~Reminder channels~~ — settled: upcoming + missed; MVP in-app; Telegram = Stage 2.
6. ~~Audition vs Text Playback~~ — settled: keep separate.
7. ~~Audio source~~ — settled: TTS and textbook/Oxford audio when available.
8. ~~Telegram ingest notify~~ — settled: MVP in-app only; Telegram = Stage 2.
9. ~~PDF/OCR + FSRS lib + D3 criteria~~ — settled (§6.4).
10. ~~Oxford display/redistribution license~~ — settled (2026-10-21): **policy A** — Free Dictionary primary for Phase A/MVP lexicon recommend; Oxford runner-up until owner reads T&Cs after signup (not a legal opinion; C3).
11. ~~RU LLM quality scorecard~~ — settled (2026-10-21): **policy C** — Phase A spike before D3 runs mini scorecard (RU UI + EN pedagogy) across OpenAI mini/nano, Anthropic Haiku/Sonnet, Gemini Flash-Lite; owner picks primary + runner-up for D3.
12. ~~D2 competitive positioning~~ — settled (§6.5).
13. Exact FSRS Learned badge thresholds (S floor, _k_ streak, modalities) — **deferred** to Phase A spike (before D1 cites them; before product mastery UI ships).
14. Exact frequent-error frequency threshold (FR-23) — **deferred** to Phase A spike (with Q13; before Teacher Agent notify ships).

## 9. Assumptions Index

- [ASSUMPTION] Textbook-led path is the spine of v1.
- [ASSUMPTION] Exemplar corpus is `textbooks/*.pdf` (English File Beginner).
- [ASSUMPTION] Anytime Audition session not required for v1.
- [ASSUMPTION] Exact UI for study rhythm (calendar vs frequency) is UX work; both satisfy FR-8.
- [ASSUMPTION] Audio uploads are course audio paired to a Textbook/course, not free-floating music.
- Decision: Audition ≠ Text Playback; audio = TTS + textbook/Oxford when available.
- Decision: mastery / auto-review / remediation — §6.3.
- Decision: PDF/OCR + FSRS lib + D3 criteria — §6.4.
- Decision: competitive white space / borrow / avoid — §6.5.
