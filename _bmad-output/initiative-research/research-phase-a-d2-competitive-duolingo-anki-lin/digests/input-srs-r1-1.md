# Digest: input-srs round 1

**Decision served:** D2 competitive analysis — adult English self-study (textbook-led + dictionary vocab + spaced repetition + teacher-agent feedback). Dimension: **input-srs**.  
**Products covered:** Anki; LingQ; specialized SRS peer = **RemNote** (strongest evidenced modern FSRS peer this run). Lead only: SuperMemo (not carded).  
**Accessed:** 2026-10-21  
**Method note:** WebSearch + WebFetch. Some WebSearch approval prompts failed mid-run; primary claims re-fetched from official docs, pricing pages, App Store / Play listings. Trustpilot LingQ fetch returned 500.

---

## Findings (claims)

| # | Claim | Source | Publisher | Pub date | Accessed | Confidence | Class |
|---|--------|--------|-----------|----------|----------|------------|-------|
| F1 | Anki offers two schedulers: legacy SM-2-based algorithm and **FSRS** (Free Spaced Repetition Scheduler); FSRS uses Retrievability / Stability / Difficulty memory state and ML-fit parameters from review history; desired retention (default 90%) is the main user lever | [Anki FAQ – algorithm](https://docs.ankiweb.net/faqs/what-spaced-repetition-algorithm); [Deck Options – FSRS](https://docs.ankiweb.net/deck-options.html?highlight=FSRS) | Anki Docs | Live docs (FSRS section current) | 2026-10-21 | high | algorithm (two-source) |
| F2 | FSRS enablement is global across presets; learning/relearning steps should be &lt;1 day; Optimize parameters; Hard ≠ fail (misuse inflates intervals); scheduling add-ons discouraged with FSRS | Same Deck Options FSRS section | Anki Docs | Live | 2026-10-21 | high | algorithm / UX |
| F3 | AnkiMobile (iOS) lists SM2 + FSRS, free AnkiWeb sync, large decks, offline media; companion to desktop (note-type edits / add-ons on computer); **$24.99** one-time US App Store; rating **4.0** / 2.4K | [App Store – AnkiMobile](https://apps.apple.com/us/app/ankimobile-flashcards/id373493387) | Apple / Anki Software | Listing live; builds through 25.09 (2025-09-08) | 2026-10-21 | high | offer / pricing |
| F4 | AnkiWeb sync documented as free cloud sync; unused AnkiWeb accounts may be deleted after ~6 months inactivity | [AnkiMobile sync docs](https://docs.ankiweb.net/ankimobile/syncing); [Tenderapp KB – account removal](https://anki.tenderapp.com/kb/anki-ecosystem/ankiweb-account-removal) | Anki | Live | 2026-10-21 | high | pricing / data |
| F5 | Anki export: plain-text notes; `.apkg` deck packages; `.colpkg` full collection (import replaces collection); optional scheduling/media/presets | [Anki Manual – Exporting](https://docs.ankiweb.net/exporting.html) | Anki Docs | Live | 2026-10-21 | high | import/export |
| F6 | Trajectory: AnkiMobile 25.07 matched desktop with **FSRS6**; 25.09 matched desktop 25.09 (2025) | App Store version history on AnkiMobile listing | Apple / Anki | 2025-07 to 2025-09 | 2026-10-21 | high | trajectory |
| F7 | LingQ: import content (URL/text/file/scan); tap-to-dictionary → save “LingQs”; blue→yellow→known status; proprietary **SRS** due queue; review activities; multi-dictionary lookups | [LingQ iOS support](https://www.lingq.com/en/ios-app-support/); [LingQ iOS product page](https://www.lingq.com/en/ios-app/) | LingQ | Live | 2026-10-21 | high | offer / reading workflow |
| F8 | LingQ Free: 20 saved words, 5 imports, 1 playlist; Premium unlocks unlimited saves/imports, flashcard quizzes, offline, stats, full-sentence translations, auto audio for imports | [LingQ Free vs Premium blog](https://www.lingq.com/blog/lingq-free-vs-premium/) (2026-08-04); [signup/pricing](https://www.lingq.com/en/signup/) | LingQ | Blog 2026-08-04; pricing live | 2026-10-21 | high | pricing / offer |
| F9 | LingQ Premium USD (blog, Aug 2026): **$14.99/mo**, **$10/mo** (12-mo / $119.99), **$8.99/mo** (24-mo / $215.76); Premium Plus ~**$29.99/mo** or **$22.50/mo** annual (+ AI voices, Advanced Lynx Chat, AI Simplified Lessons, 6× audio transcription). Live signup page also showed **GBP** geo prices (£12.99/mo etc.) | Blog + signup fetch | LingQ | ≤3 mo | 2026-10-21 | high USD via blog; high that geo-pricing exists | pricing |
| F10 | LingQ App Store: **4.7** / ~9.4–10K ratings; recent praise for authentic reading/listening & intermediate+ progress; friction: clunky UI, bugs, wish for stronger auto vocab SRS / curriculum after Mini Stories; free-tier 20-LingQ wall | [App Store – Learn Languages \| LingQ](https://apps.apple.com/us/app/learn-languages-lingq/id379385811); reviews synthesis in search | Apple / users | Reviews dated Jan–Jun (year omitted on some) + 2024-11; appslupa aggregates last-12-mo themes | 2026-10-21 | high rating; medium on exact review years when App Store omits year | voice / traction |
| F11 | RemNote: notes + flashcards in one app; schedulers include Anki SM-2, FSRS (**v6**, opt-in beta), legacy Exponential (not recommended); claimed ~20–30% fewer reviews vs SM-2 for same retention; Anki deck import preserves review history for FSRS | [RemNote FSRS help](https://help.remnote.com/en/articles/9124137-the-fsrs-spaced-repetition-algorithm) (updated 2026-08-21); [Custom Schedulers](https://help.remnote.com/en/articles/6958056-custom-schedulers); [remnote.com/feature/fsrs](https://www.remnote.com/feature/fsrs) | RemNote | Help 2026-08-21 | 2026-10-21 | high algorithm; medium on % gain (vendor claim) | algorithm (two-source help + feature page) |
| F12 | RemNote pricing (live): Free $0 (unlimited notes/cards/devices; capped PDF/IO/handwriting); Pro **$8/mo** billed yearly ($96/yr); Pro+AI **$18/mo** yearly; also monthly & Life-Long Learner referenced in help FAQ | [remnote.com/pricing](https://www.remnote.com/pricing); [Pro FAQ](https://help.remnote.com/en/articles/6084981-remnote-pro-frequently-asked-questions) (2026-08-21) | RemNote | Live / Aug 2026 | 2026-10-21 | high | pricing |
| F13 | RemNote voice: App Store / Play praise notes+cards unification vs Anki; low-star / recent complaints concentrate on **mobile lag, crashes, sync/save failures, crowded UI** (e.g. iOS review 2025-08-25; Android 1★ themes Oct 2025–Feb 2026 via ProdApps aggregation) | [App Store RemNote](https://apps.apple.com/us/app/remnote-notes-flashcards/id1545429784); [ProdApps RemNote advisor](https://productivity-apps.com/apps/remnote/advisor); Play snippets in search | Users / third-party aggregator | 2025-08 to 2026-03 | 2026-10-21 | medium–high (aggregator is secondary) | voice |
| F14 | LingQ does **not** publicly name SM-2/FSRS on support pages retrieved; describes proprietary “SRS algorithm” + status progression (correct twice in session → status up) and prioritizes re-encounter in reading over clearing all due cards | LingQ iOS support Vocabulary section | LingQ | Live | 2026-10-21 | high (absence of named algo on retrieved pages) | algorithm / product philosophy |

**Unverified beliefs (omitted from decision lenses unless marked):** SuperMemo current pricing/feature matrix (not fetched); Mnemosyne current status; exact Anki desktop/Android dollar costs beyond “free” (desktop/Android free is consistent across AnkiMobile listing + sync docs, not separately price-page verified); LingQ Trustpilot scores (fetch failed); whether RemNote FSRS beta bugs affect language decks specifically.

---

## Product cards

### Anki

**Offer & features:** User-owned flashcard SRS. Desktop + AnkiDroid + AnkiWeb + paid AnkiMobile. Dual algorithm: SM-2 lineage **or** FSRS (optimize parameters; target retention). Shared/community decks; add-ons on desktop; media on cards; graphs/stats; powerful search. **Not** a reading app or curated language course — content is user/community-authored. Dictionary = DIY (fields, templates, external links; AnkiMobile changelog mentions dictionary-link fixes, not a built-in language dictionary product).

**Pricing & packaging:** Desktop/open-source + AnkiWeb sync = free (docs/listing). AnkiMobile US **$24.99** one-time (funds ecosystem per listing). No recurring Anki subscription evidenced this run.

**Positioning:** Serious, flexible SRS tool for learners who accept a learning curve; AnkiMobile listing warns against subscription knockoffs and positions app as companion to computer Anki.

**Trajectory blip:** 2025 mobile releases aligned with desktop **FSRS6** (25.07) and continued desktop parity (25.09). Algorithm modernization is the clearest recent product motion.

**Customer voice (≤12 mo where dated):**
- **Praise:** One-time purchase vs Quizlet-style subs; powerful once learned; “original” SRS trust (listing reviews; older praise still surface but Jul “Not for dummies!!” and feature praise coexist).
- **1–3★ / friction:** Steep learning curve; SRS daily limits confuse Quizlet-expecting users (Jul review on listing); sync/reliability worries historically; small-team bug risk (older reviews on listing — use as supporting, not sole, signal).

| Lens | Assessment | Why |
|------|------------|-----|
| **Strengths** | Best-in-class open SRS (SM-2 + FSRS), user-owned content, strong import/export (`.apkg`/`.colpkg`/text), near-free economics | Manual F1–F5; App Store pricing |
| **Weaknesses** | UX cliff; no textbook/reader workflow; no first-party dictionary/vocab-from-input loop; FSRS footguns (Hard misuse, add-on conflicts) | Listing reviews; Deck Options warnings; absence of reading product |
| **Borrow** | FSRS + desired-retention control; portable deck formats; local-first ownership; optional paid mobile funding free sync | Differentiation-critical vs subscription flashcard apps |
| **Avoid** | Shipping raw Anki complexity to non-power users; assuming community decks = pedagogy; treating Hard/Again incorrectly in copy | Voice + FSRS docs |
| **Applicable?** | **Yes for SRS core; No as full product shell** | Maps to spaced repetition + user vocab ownership; does not cover textbook-led reading or teacher-agent. Use as algorithm/export benchmark, not UX template. |

---

### LingQ

**Offer & features:** Comprehensible-input platform: library + **import any content** → reader with color-coded known/unknown; tap word → dictionary/popular translations → save LingQ; phrase LingQs; sentence mode; playlist/audio; stats/streaks; **SRS review activities** for due terms. Philosophy: create many LingQs; don’t stress clearing all reviews — re-reading is primary. Premium Plus adds AI voices, Advanced Lynx Chat, AI Simplified Lessons.

**Pricing & packaging:** Freemium with hard caps (20 LingQs / 5 imports). Premium subscription (USD per Aug 2026 blog: $14.99 / $10 / $8.99 effective monthly by term). Premium Plus AI tier. Geo-localized currency on signup page (GBP observed this run).

**Positioning:** Content-first language learning for serious learners (esp. intermediate+); cofounder polyglot narrative on pricing page; “no set order — you are in charge.”

**Trajectory blip:** Aug 2026 Free vs Premium blog; Premium Plus AI packaging on live pricing; App Store builds through Oct 2026 per third-party tracker (appslupa) — treat build dates as secondary.

**Customer voice:**
- **Praise:** Best for advanced proficiency via authentic input; engaging real audio; import-from-web workflow (App Store reviews May/Jun; signup page 4.7 / 21,520 reviews claim).
- **1–3★ / friction:** Clunky UI; bugs/glitches every session (Jan review); free 20-word wall; membership cancel/downgrade pain (2023 review — older); desire for stronger automatic interval vocab trainer after Mini Stories (May “clunky” review); billing mentioned in ~7% of recent reviews per appslupa aggregate.

| Lens | Assessment | Why |
|------|------------|-----|
| **Strengths** | Textbook/reading-adjacent **import + dictionary-in-context + vocab status**; SRS as companion not sole engine; multi-device sync | iOS support + pricing/feature matrix |
| **Weaknesses** | Proprietary opaque SRS (not FSRS/SM-2 named); freemium hostile to serious trial; UI/bug debt; weak guided path for absolute beginners | F14; Free caps; App Store cons |
| **Borrow** | Tap-to-save from reading; status colors; import URL/file; “re-encounter in content &gt; clear all due” messaging; dictionary multi-source | Closest peer to textbook-led + dictionary vocab |
| **Avoid** | 20-item free vocab cap as conversion hammer; opaque SRS without retention targets; AI upsell before core reader polish | Pricing + voice |
| **Applicable?** | **Yes (strongest workflow analog)** | Directly maps input → dictionary → SRS; gaps: algorithm transparency, teacher-agent depth (Lynx Chat is AI, not human teacher), English-textbook structure not required. |

---

### RemNote (specialized SRS peer)

**Why this peer:** Among SuperMemo / RemNote / Mnemosyne / FSRS-first apps, RemNote had the strongest **current primary-doc evidence** this run for modern **FSRS v6**, dual SM-2/FSRS, Anki import with history, and live pricing — positioning it as the specialized notes+SRS competitor rather than language input.

**Offer & features:** Outliner notes with flashcards in context; PDF annotation / image occlusion (plan-gated); Exam Scheduler; AI card generation on Pro+AI. Schedulers: Anki SM-2 (default customizable), FSRS v6 (beta, opt-in, auto-train weights after ≥~1000 reviews), Exponential (legacy). Marketing: cards keep note context vs isolated Anki facts.

**Pricing & packaging:** Generous Free (unlimited notes/cards/sync); Pro ~$8/mo annual; Pro+AI ~$18/mo annual; Life-Long Learner one-time (FAQ, price not on fetched pricing table detail).

**Positioning:** “Notes + flashcards” for students (esp. med school testimonials on pricing page); Anki alternative with less app-switching.

**Trajectory blip:** FSRS incorporated (was plugin → built-in); help updated 2026-08-21 still labels FSRS **beta**; AI tier expansion on pricing.

**Customer voice:**
- **Praise:** Easier than Anki; notes+cards unified; Anki import smooth (pricing-page quotes; Play Apr 2026 praise).
- **1–3★:** Mobile overloaded/flimsy UI (2025-08-25); Android crashes, lag, failed saves, subscription not reflecting (ProdApps 1★ samples Oct 2025–Feb 2026).

| Lens | Assessment | Why |
|------|------------|-----|
| **Strengths** | FSRS v6 + SM-2 choice; card-in-notes context; Anki interoperability; free unlimited cards | Help F11–F12 |
| **Weaknesses** | Not language-input/dictionary-native; FSRS still beta; mobile reliability risk for daily review habit | Voice F13; no LingQ-like reader |
| **Borrow** | Cards born from study notes/textbook excerpts; scheduler presets; Anki import bridge; retention-oriented FSRS copy | Fits textbook-led → card pipeline |
| **Avoid** | Feature sprawl before mobile reliability; shipping “beta” scheduler as default without guardrails; AI credit complexity as core | Pricing complexity + mobile complaints |
| **Applicable?** | **Partial** | Excellent for SRS + user-owned study material; **not** a reading/dictionary input product. Borrow note→card, not the whole RemNote meta. |

---

## Cross-product patterns

1. **Algorithm split:** Transparent ML SRS (Anki FSRS, RemNote FSRS v6) vs **opaque proprietary SRS** (LingQ) attached to reading. For D2, adults who care about retention science will expect Anki-class explainability; input-first learners may tolerate LingQ’s “status + due” model.
2. **Content ownership axis:** Anki/RemNote = user-authored cards (exportable). LingQ = user-imported **texts** with platform-held LingQ vocab (export not evidenced this run).
3. **Dictionary integration:** Only LingQ ships first-party multi-dictionary-in-reader. Anki/RemNote leave dictionary to card fields or external tools.
4. **Monetization:** Anki = mostly free + one-time iOS. RemNote = freemium with real free SRS. LingQ = freemium with **vocab/import caps** that block the core loop.
5. **Textbook/reading workflows:** LingQ wins on import→read→save. RemNote wins on annotate/PDF→card. Anki wins on pure review after cards exist.
6. **Reliability tax:** Power-user SRS apps (Anki, RemNote) draw low-star complaints on sync/bugs/complexity; language input apps (LingQ) on UI/bugs/billing — habit products are judged harshly when review day fails.

---

## Leads

| Lead | Why follow | Priority |
|------|------------|----------|
| **SuperMemo** (desktop/web pricing, SM-17/18 claims, language packs) | Original SRS lineage; not carded this round | Medium — second specialized peer |
| LingQ **vocab export / Anki sync** existence | Critical for “user-owned content” comparison; not found on pages fetched | High |
| RemNote **Life-Long Learner** exact price + FSRS default timeline | Pricing/FAQ mentions; table incomplete | Low |
| Mnemosyne / standalone **FSRS** apps (e.g. FSRS-native mobile) | Confirm no stronger narrow peer than RemNote | Low |
| Two-source **traction** (downloads, MAU) for Anki/LingQ/RemNote | Only store ratings + LingQ first-party review counts this run | Medium |

---

## Looked for but not found

- LingQ public documentation naming **SM-2 / FSRS / SuperMemo** as the vocab scheduler (only “our SRS algorithm”).
- LingQ **Trustpilot** page content (HTTP 500 this run).
- Anki official single **pricing page** (model inferred from App Store + sync docs + listing copy).
- RemNote / LingQ **App Store URLs** with wrong IDs (404 until corrected via search).
- Evidence that any of the three ships a **human teacher-agent** feedback loop comparable to tutoring (LingQ Premium Plus AI chat is AI-only on retrieved pages).
- Fresh SuperMemo feature/pricing primary fetch (deferred as lead).
