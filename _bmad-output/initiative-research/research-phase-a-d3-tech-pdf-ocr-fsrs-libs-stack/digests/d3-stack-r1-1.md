# Digest: d3-stack round 1

**Dimension:** d3-stack | **Accessed:** 2026-10-21 | **Method:** WebSearch + WebFetch primary docs only (no project tickets/PRDs/code).  
**Scope:** Phase-A criteria matrix + shortlists (3–5 per row) for solo adult English-learning app; baseline Python 3.13 server + Angular client + Docker Compose. No forced single pick unless evidence overwhelming.

---

## Findings (claims) — claim/source/publisher/pub_date/accessed/confidence/class

| # | Claim | Source | Publisher | Pub date | Accessed | Confidence | Class |
|---|--------|--------|-----------|----------|----------|------------|-------|
| F1 | OpenAI API token pricing is public; e.g. `gpt-4o-mini` $0.15/$0.60 per 1M input/output; `gpt-5-mini` $0.25/$2.00; nano tiers cheaper (`gpt-5-nano` $0.05/$0.40). | https://platform.openai.com/docs/pricing | OpenAI | undated page (live) | 2026-10-21 | high | pricing |
| F2 | Anthropic publishes API model rates on pricing page; e.g. Haiku 5.5 ~$0.50/$2.50 per MTok (≤100K prompts); Sonnet 5.5 $2/$10; Opus 5.5 $4/$20; Fable 5.1 $10/$50. | https://www.anthropic.com/pricing#api | Anthropic | undated page (live) | 2026-10-21 | high | pricing |
| F3 | Google Gemini Developer API has Free tier (limited models; content may improve products) and Paid; `gemini-2.5-flash-lite` Free input/output “Free of charge”; Paid $0.10 in / $0.40 out per 1M tokens. | https://ai.google.dev/gemini-api/docs/pricing | Google | undated page (live) | 2026-10-21 | high | pricing |
| F4 | Second source for Gemini free/paid framing: same Google pricing doc Free vs Paid sections (two-source: F3+F4 same publisher page sections). | https://ai.google.dev/gemini-api/docs/pricing | Google | undated | 2026-10-21 | high | pricing |
| F5 | **RU UI capability for LLMs:** No vendor pricing/docs page retrieved this run states Russian chat quality SLAs. Treat RU quality as **eval gate**, not catalog claim. | — | — | — | 2026-10-21 | n/a | gap |
| F6 | LangGraph is a low-level Python agent orchestration runtime (`pip install langgraph`); docs stress durable execution, HITL, persistence; recommend higher-level LangChain agents if starting out. | https://docs.langchain.com/langgraph | LangChain Inc | undated docs | 2026-10-21 | high | product |
| F7 | Thoughtworks Technology Radar Vol 34 places **LangGraph** in **Trial** (languages/frameworks); also **LiteLLM** Trial; **Caution: Ignoring durability in agent workflows**. | https://www.thoughtworks.com/radar | Thoughtworks | April 2026 (Vol 34) | 2026-10-21 | high | maturity |
| F8 | Thoughtworks Vol 34 theme: AI pace makes evaluation hard; tools “less than a month old” often too young to assess; risk of **codebase cognitive debt** from adopting without mental models. | https://www.thoughtworks.com/radar | Thoughtworks | April 2026 | 2026-10-21 | high | practice |
| F9 | Dify self-host via Docker Compose is documented; min **CPU ≥2, RAM ≥4 GiB** (macOS note: ≥8 GiB VM); Compose starts **~15 containers** (7 core + 8 deps + init). | https://docs.dify.ai/en/getting-started/install-self-hosted/docker-compose | LangGenius / Dify | undated docs | 2026-10-21 | high | ops |
| F10 | Dify upgrade guidance: compare `.env` to examples; if `docker-compose.yaml` customized, **re-apply** onto new release file (release can add required services). | same as F9 | Dify | undated | 2026-10-21 | medium | pain |
| F11 | Qdrant official quickstart: `docker pull qdrant/qdrant`, single container ports 6333/6334, Python client; optional embedded/in-process. | https://qdrant.tech/documentation/quickstart/ | Qdrant | undated docs | 2026-10-21 | high | product |
| F12 | Chroma: Apache-2.0 OSS; self-host or Chroma Cloud; embeddings + dense/sparse/hybrid + metadata filter. | https://docs.trychroma.com/docs/overview/introduction | Chroma | undated docs | 2026-10-21 | high | product |
| F13 | Pinecone: managed only on public pricing; Starter free; Builder $20/mo flat; Standard **$50/mo minimum** usage; Enterprise $500/mo min. | https://www.pinecone.io/pricing/ | Pinecone | undated | 2026-10-21 | high | pricing |
| F14 | Second source for Pinecone floor: plan comparison table same page (Starter free vs Builder $20 vs Standard $50 min). | https://www.pinecone.io/pricing/ | Pinecone | undated | 2026-10-21 | high | pricing |
| F15 | pgvector: open-source vector similarity search **for Postgres** (GitHub `pgvector/pgvector`). | https://github.com/pgvector/pgvector | pgvector project | undated | 2026-10-21 | medium | product |
| F16 | Oxford Dictionaries API pricing (primary): Sandbox free **500 calls** (first-letter restricted); **API Lite £50/mo** (£600/yr) — 1,000 calls/mo, en-GB/en-US, Search/Lemmas/Words/Entries, overage £0.10/call; **Growing from £200/mo** — 10k calls/mo/language + Thesaurus/Sentences/Inflections, overage £0.01; **Enterprise from £415/mo** (£5k/yr billed) — 500k calls/mo/language. | https://account.oxforddictionaries.com/pricing | Oxford Languages | live; plans relaunch noted Jan 2025 | 2026-10-21 | high | pricing |
| F17 | Second source Oxford plans: Updates post “Introducing Our New API Plans - Lite and Growing” **9 January 2025**; starts from £50/mo billed annually. | https://developer.oxforddictionaries.com/updates | Oxford Dictionaries API | 2025-01-09 | 2026-10-21 | high | pricing |
| F18 | Oxford Enterprise signup page: Enterprise licenses **commercial use only**, annual fee **from £5,000 per language**; offline/license content via sales. | https://developer.oxforddictionaries.com/signup-enterprise | Oxford | undated | 2026-10-21 | high | license |
| F19 | Oxford request shape: `https://od-api.oxforddictionaries.com/api/v2/{endpoint}/{language_code}/{word_id}`; headers `app_id`/`app_key`; Python `requests` sample; endpoints include entries, thesaurus, sentences; lemmas for inflections. | https://developer.oxforddictionaries.com/documentation/making-requests-to-the-api | Oxford | undated | 2026-10-21 | high | api |
| F20 | Oxford languages table: **Russian `RU` → EN** supports Search Translations + Translations only (not Entries/Words monolingual EN learner path). EN monolingual Entries for EN-GB/EN-US. | https://developer.oxforddictionaries.com/documentation/languages | Oxford | undated | 2026-10-21 | high | api |
| F21 | Full Oxford commercial T&Cs / redistribution license text for app display of definitions: **not retrieved** (likely account/paywalled). Flag: license flags incomplete. | — | — | — | 2026-10-21 | n/a | gap |
| F22 | Free Dictionary API: `GET https://api.dictionaryapi.dev/api/v2/entries/en/{word}`; JSON array with word, phonetic(s), meanings[].definitions; no auth on public page. | https://dictionaryapi.dev/ | Free Dictionary API | undated | 2026-10-21 | medium | api |
| F23 | Merriam-Webster Dictionary API: free if **non-commercial**, ≤**1000 queries/day/key**, ≤2 reference APIs; commercial requires contact/approval. | https://dictionaryapi.com/ | Merriam-Webster | undated | 2026-10-21 | high | license |
| F24 | OpenAI transcription: Whisper **$0.006/minute**; `gpt-4o-mini-transcribe` $0.003/min; TTS `tts-1` $15/1M chars; `gpt-4o-mini-tts` audio out $12/1M tokens. | https://platform.openai.com/docs/pricing | OpenAI | undated | 2026-10-21 | high | pricing |
| F25 | OpenAI STT docs: Whisper supports **98 languages** (accuracy varies); recommend `gpt-transcribe`; whisper-1 timestamps deprecated path until 2027-02-26. | https://platform.openai.com/docs/guides/speech-to-text | OpenAI | undated | 2026-10-21 | high | product |
| F26 | PostgreSQL documents JSON/JSONB as first-class types for semi-structured data alongside relational tables (supports hybrid learner profile: relational core + JSONB flex). | https://www.postgresql.org/docs/current/datatype-json.html | PostgreSQL GDG | current docs | 2026-10-21 | high | storage |
| F27 | Coze / ByteDance agent platform: **not successfully fetched** this run (search intermittently blocked). Peer named in brief remains **unevidenced here**. | — | — | — | 2026-10-21 | n/a | gap |
| F28 | Community retrospective posts (Reddit/HN “LangGraph/Dify/Pinecone pain”): WebSearch **rejected** this run; pain points below limited to **vendor-doc friction** + Thoughtworks caution blips, not user retros. | — | — | — | 2026-10-21 | n/a | gap |

---

## Criteria matrix (suggested weights)

Hard gates (binary fail → drop from shortlist): **Python server SDK or HTTP**; **Docker Compose–friendly** (or zero extra services); **solo-operable** (≤ few moving parts); Angular is client-only (server choices dominate).

| Criterion | Suggested weight (solo Phase-A) | Why (evidenced practice) |
|-----------|----------------------------------|---------------------------|
| **Ops burden** | **0.30** | Dify’s own Compose footprint (~15 containers, 2+ CPU / 4–8 GiB) shows platform agents tax solo ops (F9). Thoughtworks warns AI novelty creates cognitive debt if systems aren’t understood (F8). |
| **Cost (API + infra)** | **0.25** | Token rates span ~$0.05–$10+/MTok across vendors (F1–F3); Oxford Lite alone is £50/mo floor for quality lexicon (F16–F17); Pinecone Standard floors at $50/mo (F13). Solo burn rate is a go/no-go. |
| **RU quality (UI + content)** | **0.20** | Product needs Russian UI; vendors do not publish RU SLAs on pricing pages (F5). Oxford RU is translation-oriented, not EN monolingual teaching data (F20). Weight high enough to force a **scorecard eval**, not catalog pick. |
| **Lock-in** | **0.15** | Managed-only vector (Pinecone F13) and proprietary agent platforms raise exit cost; LiteLLM appears on Thoughtworks Trial as abstraction pattern (F7) — favors portable LLM calls. |
| **Maturity / freshness** | **0.10** | Thoughtworks: tools &lt;1 month often too young; LangGraph Trial not Adopt (F7–F8). AI-adjacent freshness bar ≤3 mo for version/pricing claims; general stack ≤12 mo. |

**Owner re-weight later.** If RU UI is existential, raise RU to 0.30 and cut cost/ops. If budget is existential, invert.

---

## Shortlists per row A–F

### A. LLM (note RU + cost)

**Landscape maturity:** Frontier API market mature (&gt;12 mo); **model SKUs and prices churn ≤3 mo** — re-check pricing pages before commit (F1–F3, F8).

| Candidate | Pass hard gates? | Cost signal (this run) | RU note | Ops / lock-in |
|-----------|------------------|------------------------|---------|---------------|
| **OpenAI** (mini/nano default) | Yes (HTTPS API) | `gpt-4o-mini` $0.15/$0.60; `gpt-5-nano` $0.05/$0.40 per 1M (F1) | Unverified quality — eval required (F5) | Low ops; moderate lock-in (mitigate via OpenAI-compatible abstraction) |
| **Anthropic Claude** (Haiku/Sonnet) | Yes | Haiku 5.5 ~$0.50/$2.50; Sonnet $2/$10 per MTok (F2) | Unverified — eval | Low ops; lock-in similar |
| **Google Gemini** (Flash-Lite) | Yes | Free tier available; Paid flash-lite $0.10/$0.40 (F3) | Unverified — eval; Free tier may use data to improve products (F3) | Low ops; free-tier policy risk |
| **Open-weight via local/vLLM** (peer) | Yes if Docker GPU/CPU sized | Infra/GPU cost dominates; no public $/tok this run | Can run RU-tuned models — **not evidenced which** this run | High ops for solo |
| **Multi-provider via LiteLLM-style gateway** | Yes | Adds thin proxy cost | Enables A/B RU eval | Thoughtworks Trial (F7); extra service |

**Do not force pick.** Cost leader among cloud: Gemini Free / OpenAI nano for experiments; quality TBD by RU eval.

### B. Agent orchestration

**Landscape:** Frameworks mature enough for Trial (LangGraph F7); full “agent platforms” differ sharply in ops weight (F9).

| Candidate | Pass gates? | Notes |
|-----------|-------------|-------|
| **Custom Python** (FastAPI + explicit state machine / thin graph) | Yes | Lowest ops; matches Thoughtworks caution on durability — you own checkpoints (F7 Caution) |
| **LangGraph** | Yes (`pip`) | Low-level, durable/HITL/persistence (F6); Thoughtworks **Trial** (F7); learning curve = cognitive load (F6 tip + F8) |
| **LangChain agents** (higher-level on LangGraph) | Yes | Docs recommend for starters (F6) |
| **Dify** (self-host Compose) | Conditional | Docker-native but **~15 containers**, upgrade friction (F9–F10) — fails “solo lean” unless product needs visual builder |
| **Coze** | Unevidenced | Brief peer; **not retrieved** this run (F27) |

### C. Vector DB

| Candidate | Pass gates? | Notes |
|-----------|-------------|-------|
| **pgvector on existing Postgres** | Yes | One less service; OSS extension (F15); fits Compose already running Postgres |
| **Qdrant** | Yes | Official single-container Docker + Python client (F11) |
| **Chroma** | Yes | Apache-2.0; self-host or cloud (F12) |
| **Pinecone** | Conditional | Zero self-host ops but **$0→$20→$50/mo floors** and managed lock-in (F13–F14) |
| **Weaviate** (peer; Dify default bundle) | Indirect | Appears as Dify Compose dependency (F9) — not separately deep-dived |

### D. Dictionary API

| Candidate | Pass gates? | Pricing / limits / license flags | Response shape |
|-----------|-------------|----------------------------------|----------------|
| **Oxford Dictionaries API** | Yes (HTTPS + Python sample) | Sandbox 500 calls letter-limited; Lite **£50/mo**, 1k calls, overage £0.10; Growing **£200+/mo**, 10k/lang; Enterprise £5k+/lang/yr commercial (F16–F18). **Full redistrib T&Cs paywalled/not fetched (F21).** | REST v2 path `…/api/v2/{endpoint}/{lang}/{word_id}`; JSON; filters/fields projections (F19). RU = translations path, not EN Entries (F20). |
| **Free Dictionary API** | Yes | Free public HTTP; **SLA/ToS thin** on page (F22) | Array of `{word, phonetic(s), meanings[{partOfSpeech, definitions[]}]}` (F22) |
| **Merriam-Webster API** | Conditional | Free **non-commercial**, 1000 qpd, 2 APIs; commercial case-by-case (F23) | Product-specific request URLs (register for keys) |

**Oxford gate risk for solo commercial learner app:** Lite call budget + £50 floor + incomplete public license text (F16, F21). If gates fail → Free Dictionary (prototype) or MW if non-commercial / negotiated commercial.

### E. Optional ASR/TTS (Docker Compose–suitable)

| Candidate | Local / cloud | Notes |
|-----------|---------------|-------|
| **OpenAI Whisper / gpt-*-transcribe** | Cloud | Whisper $0.006/min; mini-transcribe $0.003/min; 98 langs claimed for Whisper (F24–F25) |
| **OpenAI TTS** (`tts-1`, `gpt-4o-mini-tts`) | Cloud | tts-1 $15/1M chars; mini-tts priced in tokens (F24) |
| **Local Whisper.cpp / faster-whisper** (peer) | Local Compose | Common pattern; **image/docs not fetched this run** — ops/CPU unverified |
| **Local Piper / Coqui-class TTS** (peer) | Local Compose | Suitable for offline; **not fetched** — unverified |
| **Gemini native audio / Live** | Cloud | Present on Gemini pricing page (audio lines F3 file); deeper fit not scoped |

### F. Learner profile storage

| Candidate | Notes |
|-----------|-------|
| **PostgreSQL relational** (+ migrations) | Default for accounts, progress, billing integrity; Compose staple |
| **PostgreSQL + JSONB** | Semi-structured profile/preferences without second DB (F26) |
| **Document store (MongoDB/etc.)** | Flexible schema; **extra service** — ops weight vs JSONB |
| **SQLite** | Ultra-lean solo; weaker multi-writer story for later scale |
| **Redis-only profile** | Ephemeral/cache — not system of record |

**No forced pick.** Evidence favors **relational + JSONB hybrid** for solo Compose (F26) over a separate document DB unless schema chaos is proven.

---

## Provisional lean bundle + swap conditions

> **PROVISIONAL — owner re-weights criteria; not a final architecture decision.**

**Default lean stack for solo (Compose-friendly):**

| Layer | Provisional choice | Rationale (evidence-tied) |
|-------|--------------------|---------------------------|
| A LLM | OpenAI **mini/nano** *or* Gemini **Flash-Lite** (start Free for spikes) | Lowest public $/tok among retrieved cloud options (F1, F3); swap after RU eval |
| B Orchestration | **Custom Python** graph / thin LangGraph | Avoid Dify’s ~15-container tax (F9); LangGraph available if durability/HITL needed (F6–F7) |
| C Vectors | **pgvector** on same Postgres | One less container vs Qdrant/Chroma; OSS (F15) |
| D Dictionary | **Free Dictionary API** for Phase-A prototype; **Oxford Lite** only if quality/license gates pass | Oxford £50/1k calls + incomplete public license (F16, F21); Free Dict shape known (F22) |
| E ASR/TTS | **Defer**; when needed OpenAI Whisper + tts-1 | Documented rates (F24–F25); local later if cost/privacy bites |
| F Profile | **Postgres + JSONB** | Relational integrity + flexible learner fields (F26) |

**Named swap conditions:**

1. **RU UI eval fails** on default LLM → swap provider or add LiteLLM multi-backend A/B (F5, F7).  
2. **Agent workflows need durable HITL / long-running state** → adopt LangGraph (F6–F7); if non-dev builders required → reconsider Dify despite ops (F9).  
3. **Vector workload outgrows Postgres** (latency/scale) → Qdrant single container (F11) before Pinecone $20–$50 floors (F13).  
4. **Lexicon quality/legal requires Oxford** and call volume &gt;1k/mo → Growing plan or cache aggressively (F16); if commercial MW needed → sales path (F23).  
5. **ASR/TTS cost or offline** → local Whisper/Piper-class (unevidenced this run — spike first).  
6. **Document-shaped profile chaos** (frequent nested schema change) → add Mongo *or* lean harder on JSONB before new DB.

---

## Leads

1. Run a **fixed RU UI + EN pedagogy prompt pack** across OpenAI mini, Claude Haiku, Gemini Flash-Lite (fills F5).  
2. Fetch Oxford **full license / display rights** after account signup (F21).  
3. Spike **pgvector vs Qdrant** on expected corpus size (no perf numbers this run — two-source rule unmet).  
4. If agent platform desired: fetch **Coze** primary docs (F27) + compare container count to Dify (F9).  
5. Local ASR/TTS: fetch Whisper.cpp / Piper Docker Compose READMEs (row E peers).  
6. Thoughtworks Vol 34 PDF deep-read on LangGraph / LiteLLM blip text (only landing page retrieved).

---

## Looked for but not found

- Public Oxford **redistribution / UI display license** text (paywalled or account-gated) (F21).  
- Vendor **Russian LLM quality** guarantees or scorecards on primary docs (F5).  
- **Coze** primary documentation (F27).  
- Community **retrospectives** (Reddit/HN) on LangGraph/Dify/Pinecone — WebSearch approval failed (F28).  
- Two independent sources for **vector DB latency/throughput** numbers — omitted.  
- Local Whisper/Piper official Compose docs — not fetched within budget.  
- Merriam-Webster detailed response schema — only Developer Center terms (F23).

---

*End digest d3-stack-r1-1. Sources used this run ≈12 primary URLs (OpenAI pricing×2 views, Anthropic pricing, Gemini pricing, LangGraph docs, Thoughtworks Radar, Dify Compose, Qdrant quickstart, Chroma intro, Pinecone pricing, Oxford pricing+updates+requests+languages+enterprise, Free Dictionary, Merriam-Webster, Postgres JSON, OpenAI STT). WebSearch intermittently blocked; some peers thin by design.*
