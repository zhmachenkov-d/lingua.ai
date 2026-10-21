# Digest: fsrs-lib round 1

**Dimension:** fsrs-lib  
**Accessed:** 2026-10-21  
**Method note:** WebSearch tool approval failed this run; evidence retrieved via HTTP fetch of primary sources (PyPI JSON, GitHub raw/API, Anki docs, Anki `Cargo.toml`).

## Findings (claims)

### F1 — Official OSR pure-Python package is PyPI `fsrs` (repo `py-fsrs`), not `py-fsrs`
- **Claim:** The Open Spaced Repetition Python FSRS package installs as `pip install fsrs`; GitHub repo is `open-spaced-repetition/py-fsrs`. PyPI name `py-fsrs` returns Not Found.
- **Source:** https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/README.md ; https://pypi.org/pypi/fsrs/json ; https://pypi.org/pypi/py-fsrs/json (404)
- **Publisher:** Open Spaced Repetition / PyPI
- **Pub_date:** README current on `main` (repo `updated_at` 2026-10-20); `fsrs` 6.3.2 upload 2026-08-09
- **Accessed:** 2026-10-21
- **Confidence:** high
- **Class:** fact

### F2 — `fsrs` 6.3.2 hard gates: Python ≥3.10, MIT, maintained, CI includes 3.13
- **Claim:** Latest release `6.3.2` requires `requires-python >=3.10`, MIT license, pure `py3-none-any` wheel, default runtime dep only `typing-extensions`. GitHub Actions matrix tests `3.10`–`3.14` including **3.13** for basic and optimizer jobs. Repo not archived; latest GitHub release published 2026-08-09; stars ~514.
- **Source:** https://pypi.org/pypi/fsrs/json ; https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/pyproject.toml ; https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/.github/workflows/test.yml ; https://api.github.com/repos/open-spaced-repetition/py-fsrs ; https://github.com/open-spaced-repetition/py-fsrs/releases/tag/v6.3.2
- **Publisher:** Open Spaced Repetition / PyPI / GitHub
- **Pub_date:** release 2026-08-09; workflow on `main`
- **Accessed:** 2026-10-21
- **Confidence:** high
- **Class:** fact

### F3 — `fsrs` exposes D/S/R + scheduling API sufficient for `next_review`
- **Claim:** `Card` stores `stability`, `difficulty`, `due`; `Scheduler.review_card(card, rating)` returns updated card + `ReviewLog`; `Scheduler.get_card_retrievability(card)` returns R; JSON `to_json`/`from_json` for persistence. Optional `Optimizer` via `pip install "fsrs[optimizer]"` (torch/numpy/pandas/tqdm).
- **Source:** https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/fsrs/card.py ; https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/README.md ; https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/fsrs/scheduler.py (methods `get_card_retrievability`, `review_card`, `reschedule_card`); https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/fsrs/__init__.py
- **Publisher:** Open Spaced Repetition
- **Pub_date:** sources on `main` / release 6.3.2 era
- **Accessed:** 2026-10-21
- **Confidence:** high
- **Class:** fact

### F4 — `fsrs-rs-python` is OSR bindings to Anki-aligned Rust crate; ships cp313 wheels; thinner packaging metadata
- **Claim:** Package `fsrs-rs-python` 0.9.3 (`requires-python >=3.9`) provides PyO3 bindings to crate `fsrs` **6.6.2**. PyPI publishes **cp313** (and cp314) manylinux/musllinux/macos/windows wheels. GitHub: 37★, pushed 2026-10-19, homepage PyPI; README points to `examples/` for schedule/optimize. PyPI metadata lacks license/summary/project_urls; no LICENSE file in repo root (license field null on GitHub API). Parent `fsrs-rs` crate declares **BSD-3-Clause**.
- **Source:** https://pypi.org/pypi/fsrs-rs-python/json ; https://api.github.com/repos/open-spaced-repetition/fsrs-rs-python ; https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs-python/main/README.md ; https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs-python/main/Cargo.toml ; https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs/main/Cargo.toml (`license = "BSD-3-Clause"`)
- **Publisher:** Open Spaced Repetition / PyPI
- **Pub_date:** PyPI 0.9.3 upload 2026-08-31; repo push 2026-10-19
- **Accessed:** 2026-10-21
- **Confidence:** high (API/wheels); **medium** on binding package SPDX (undeclared — infer only from parent crate)
- **Class:** fact (wheels/deps); inference (binding SPDX)

### F5 — `fsrs-rs-python` API: D/S via `MemoryState`; scheduling via `next_states`; optimize without PyTorch
- **Claim:** Example/schedule API: `FSRS(parameters=...).next_states(memory_state, desired_retention, elapsed_days)` → again/hard/good/easy intervals + `MemoryState(stability, difficulty)`. `.pyi` stubs include `compute_parameters`, `memory_state`, `memory_state_from_sm2`, simulation types. README markets burn-rs instead of pytorch (“2GB → 1MB”). Caller must own Card/due bookkeeping (examples define a local `Card` class).
- **Source:** https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs-python/main/examples/schedule.py ; https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs-python/main/fsrs_rs_python.pyi ; https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs-python/main/examples/optimize.py ; https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs-python/main/README.md
- **Publisher:** Open Spaced Repetition
- **Pub_date:** examples/`main`; release 0.9.3 2026-08-31
- **Accessed:** 2026-10-21
- **Confidence:** high
- **Class:** fact

### F6 — Anki alignment favors `fsrs-rs` / bindings over pure `py-fsrs` for optimizer parity (two-source)
- **Claim:** Anki workspace depends on Rust crate `fsrs` version **6.6.2** (same version pinned by `fsrs-rs-python`). Official Anki manual documents built-in FSRS (Anki 23.10+). `py-fsrs` README states optimized parameters/retention “may be slightly different than the numbers computed by Anki” and points readers to `fsrs-rs` for the “official Rust-based Anki implementation.”
- **Source:** https://raw.githubusercontent.com/ankitects/anki/main/Cargo.toml (`[workspace.dependencies.fsrs] version = "6.6.2"`) ; https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs-python/main/Cargo.toml (`fsrs` = 6.6.2) ; https://docs.ankiweb.net/deck-options.html#fsrs ; https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/README.md (Optimizer note)
- **Publisher:** Anki / Open Spaced Repetition
- **Pub_date:** Anki docs live; Cargo.toml on `main` (accessed 2026-10-21); py-fsrs README on `main`
- **Accessed:** 2026-10-21
- **Confidence:** high
- **Class:** fact

### F7 — Community / download weight: `fsrs` ≫ `fsrs-rs-python`
- **Claim:** Recent PyPI downloads (pypistats): `fsrs` last_month **173355**, last_week **61981**; `fsrs-rs-python` last_month **5524**, last_week **2085**. GitHub stars: py-fsrs **514** vs fsrs-rs-python **37** (fsrs-rs itself **448**).
- **Source:** https://pypistats.org/api/packages/fsrs/recent ; https://pypistats.org/api/packages/fsrs-rs-python/recent ; GitHub API repos above
- **Publisher:** pypistats / GitHub
- **Pub_date:** stats snapshot 2026-10-21
- **Accessed:** 2026-10-21
- **Confidence:** high (as of access time)
- **Class:** fact

### F8 — Typing / docs: `fsrs` stronger developer UX for solo app
- **Claim:** `fsrs` ships `py.typed` (PEP 561), pdoc docs at https://open-spaced-repetition.github.io/py-fsrs , README quickstart + Optimizer section. `fsrs-rs-python` ships `.pyi` stubs; docs are mainly README + examples (no equivalent hosted API book found this run).
- **Source:** https://raw.githubusercontent.com/open-spaced-repetition/py-fsrs/main/pyproject.toml (`fsrs = ["py.typed"]`) ; https://open-spaced-repetition.github.io/py-fsrs/fsrs.html (HTTP 200) ; https://raw.githubusercontent.com/open-spaced-repetition/fsrs-rs-python/main/README.md ; presence of `fsrs_rs_python.pyi`
- **Publisher:** Open Spaced Repetition
- **Pub_date:** current `main` / docs site live
- **Accessed:** 2026-10-21
- **Confidence:** high
- **Class:** fact

### F9 — Cut: no separate “anki FSRS Python library”; `py-fsrs` PyPI name fails
- **Claim:** Anki integrates FSRS via Rust `fsrs` crate, not a first-party Python package for app embedding. Candidate name `py-fsrs` on PyPI is absent (404).
- **Source:** ankitects/anki `Cargo.toml` ; PyPI `py-fsrs` 404 ; Anki manual FSRS section
- **Publisher:** Anki / PyPI
- **Pub_date:** accessed 2026-10-21
- **Confidence:** high
- **Class:** fact

### F10 — SM-2 fallback context only (algorithm already not primary)
- **Claim:** OSR `sm-2` 0.3.0 on PyPI (MIT, `>=3.10`, upload 2024-12-07; GitHub pushed 2025-08-09). Third-party `supermemo2` 3.0.1 (MIT, upload 2024-06-23). `anki-sm-2` 0.2.0 is **AGPL-3.0** (hobby commercial risk). None are FSRS/D-S-R schedulers.
- **Source:** https://pypi.org/pypi/sm-2/json ; https://pypi.org/pypi/supermemo2/json ; https://pypi.org/pypi/anki-sm-2/json ; https://api.github.com/repos/open-spaced-repetition/sm-2 ; https://raw.githubusercontent.com/open-spaced-repetition/sm-2/main/README.md
- **Publisher:** OSR / alankan886 / joshdavham / PyPI
- **Pub_date:** see uploads above
- **Accessed:** 2026-10-21
- **Confidence:** high
- **Class:** fact

### F11 — Freshness vs budget (versions ≤1 mo)
- **Claim:** Neither finalist has a PyPI release in the last ~1 month as of 2026-10-21 (`fsrs` 6.3.2 = 2026-08-09; `fsrs-rs-python` 0.9.3 = 2026-08-31). Both remain inside ~6-month ecosystem activity (GitHub pushes Oct 2026; Anki still pins fsrs 6.6.2).
- **Source:** PyPI upload timestamps; GitHub `pushed_at`
- **Publisher:** PyPI / GitHub
- **Pub_date:** as cited
- **Accessed:** 2026-10-21
- **Confidence:** high
- **Class:** fact

### F12 — Cost & lock-in
- **Claim:** Both candidates are free OSS distributed on PyPI (no SaaS meter). Exit cost is low if the app persists its own review logs + D/S (+ due): both models use Difficulty/Stability; `fsrs-rs` also exposes `memory_state_from_sm2` for legacy migration. Switching libs means rewriting the thin adapter around `review_card` vs `next_states`, not re-deriving memory science. Optimizer path lock-in: `fsrs[optimizer]` → torch stack; `fsrs-rs-python` → native wheel/platform matrix (Docker need matching manylinux/musllinux arch).
- **Source:** licenses/deps from F2–F5; schedule/optimize examples; py-fsrs optional-dependencies
- **Publisher:** OSR
- **Pub_date:** accessed 2026-10-21
- **Accessed:** 2026-10-21
- **Confidence:** medium-high (adapter exit is engineering judgment grounded in APIs above)
- **Class:** inference

## Select matrix

Scoring: 1–5 (higher better) for solo Python 3.13 + Docker Compose hobby/commercial app. Deciding cells for top-two use **two sources** where noted.

| Criterion | `fsrs` (py-fsrs) | `fsrs-rs-python` | Notes / evidence |
|---|---|---|---|
| API ergonomics | **5** | 3 | Card+Scheduler+due vs DIY Card + `next_states` (README + schedule.py) |
| Parameter optimization | **4** | **5** | Both optimize; Rust path Anki-version-aligned (anki Cargo + binding Cargo); py-fsrs warns of slight Anki diff (README) |
| Docs quality | **5** | 2 | pdoc site + long README vs examples-only |
| Release freshness | 3 | 3 | Both last PyPI release Aug 2026; binding repo push newer (Oct 19) |
| Community / Anki alignment | 4 | **5** | Downloads/stars favor `fsrs` (pypistats/GitHub); **Anki binary uses fsrs-rs 6.6.2** (anki + binding Cargo) |
| Dependency weight (default schedule) | **5** | 3 | typing-extensions + pure wheel vs native multi-arch wheels / Rust toolchain if building from source |
| Typing | **5** | 4 | `py.typed` + typed API vs `.pyi` stubs |
| Py3.13 / Docker fitness | **5** | 4 | CI matrix includes 3.13; binding has cp313 wheels but platform wheel care |
| License clarity | **5** | 3 | MIT explicit; binding SPDX undeclared on PyPI (parent BSD-3) |
| **Solo default fit** | **Winner** | Runner-up | |

**Hard-gate screen**

| Candidate | Pass? | Cut reason if fail |
|---|---|---|
| `fsrs` / py-fsrs | **PASS** | — |
| `fsrs-rs-python` | **PASS** (with license-clarity caveat) | — |
| PyPI `py-fsrs` | FAIL | Package name 404; use `fsrs` |
| Anki-as-Python-lib | FAIL | FSRS via Rust dependency, not embeddable Python pkg |
| `sm-2` / `supermemo2` / `anki-sm-2` | N/A fallback | Not FSRS; `anki-sm-2` AGPL |

## Verdict draft

- **Pick:** **`fsrs` (GitHub: open-spaced-repetition/py-fsrs)** — install `pip install fsrs`; use `Scheduler.review_card` + persist `Card.difficulty` / `stability` / `due`; call `get_card_retrievability` for R; add `fsrs[optimizer]` only if/when personalizing parameters.
- **Runner-up:** **`fsrs-rs-python`** — same OSR ecosystem, Anki-crate-aligned (`fsrs` 6.6.2), optimize without torch, cp313 wheels ready.
- **When runner-up wins:** Need closest Anki/fsrs-rs numerical parity for optimize/schedule; refuse torch in images; want native optimizer disk footprint marketed by bindings README.
- **Against pick:** Willing to trade ergonomics/docs for Anki-identical Rust core; or need features only exposed in fsrs-rs (simulation / batch memory_state) sooner.
- **Reversibility hedge:** Persist **review logs + D + S + due** in your schema (not library-private blobs only). Keep a 1-file adapter interface (`schedule(card, rating) -> due, D, S, R`). Then swap `fsrs` ↔ `fsrs-rs-python` without migrating user-facing data model. Avoid AGPL SM-2 packages if commercial hobby distribution matters.

## Leads

1. Confirm `fsrs-rs-python` SPDX with maintainers / add LICENSE to repo (current gap).
2. Side-by-side interval smoke test: same seed reviews on `fsrs` 6.3.2 vs `fsrs-rs-python`/`fsrs` 6.6.2 for delta magnitude (not done this run).
3. Docker Compose: verify `fsrs-rs-python` wheel tag for chosen base image (`manylinux` vs `musllinux` Alpine).
4. Watch next `fsrs` PyPI release (last Aug 2026) for FSRS-6/7 parameter drift vs Anki’s 6.6.2 pin.
5. If SM-2 ever needed for import-only: prefer OSR `sm-2` (MIT) over `anki-sm-2` (AGPL).

## Looked for but not found

- WebSearch UI results (tool approval failed this run).
- Clear SPDX/license file on `fsrs-rs-python` repository/PyPI metadata.
- Hosted API documentation site for `fsrs-rs-python` comparable to py-fsrs pdoc.
- First-party Anki Python packaging of FSRS for third-party apps.
- PyPI project named `py-fsrs`.
- Performance benchmarks with two independent primary sources this run (omitted; no latency/throughput claims).
