# 🎬 pi_tiktok_stack

Automated TikTok Arabic gaming content pipeline on Raspberry Pi 5. Scrapes trending gaming news, generates Arabic scripts with AI, produces voiceover with word-level timestamps, and publishes to TikTok via Buffer's GraphQL API — orchestrated by n8n with 5-gate human-in-the-loop approval.

---

## Architecture

```mermaid
C4Context
    title TikTok Gaming Pipeline — System Context

    Person(creator, "Content Creator", "Approves via Mattermost, uploads video, picks schedule")
    System(tiktok_stack, "pi_tiktok_stack", "Automated TikTok pipeline on Raspberry Pi 5")
    System_Ext(gemini, "Google Gemini", "LLM for scripts, validation, embeddings")
    System_Ext(elevenlabs, "ElevenLabs", "Arabic TTS with word-level timestamps")
    System_Ext(buffer, "Buffer GraphQL", "TikTok publishing via api.buffer.com/graphql")
    System_Ext(mattermost, "Mattermost", "5-gate HITL approval with interactive dialogs")
    System_Ext(news, "News Sources", "RSS, Google News, Reddit")

    Rel(creator, mattermost, "Approves/rejects, uploads video, picks schedule")
    Rel(tiktok_stack, gemini, "Scripts, validation, embeddings")
    Rel(tiktok_stack, elevenlabs, "Arabic voiceover + timestamps")
    Rel(tiktok_stack, buffer, "Publishes to TikTok")
    Rel(tiktok_stack, mattermost, "Sends approval requests")
    Rel(tiktok_stack, news, "Scrapes gaming news")
    Rel(mattermost, tiktok_stack, "Webhook callbacks")
```

---

## Pipeline Flow (5-Gate Human-in-the-Loop)

```mermaid
flowchart TD
    START([🕐 Daily 10AM / Manual]) --> PLAN[🧠 Planner — RAWG + Trending News]

    PLAN --> GATE0{0️⃣ Gate 0 — Plan}
    GATE0 -- ✅ --> SCRAPE[📰 Scrape News]
    GATE0 -- ❌ --> R0[Reject]

    SCRAPE --> GATE1{1️⃣ Gate 1 — News}
    GATE1 -- ✅ --> SCRIPT[✍️ Writer — TikTok Script]
    GATE1 -- ❌ --> R1[Reject]

    SCRIPT --> VALIDATE[🔍 Validator + Auto-Revise]
    VALIDATE --> GATE2{2️⃣ Gate 2 — Script}
    GATE2 -- ✅ --> VOICE[🎙️ ElevenLabs TTS]
    GATE2 -- ❌ --> R2[Reject]
    GATE2 -- 💬 Comment --> REWRITE[Rewrite Loop]

    VOICE --> GATE3{3️⃣ Gate 3 — Voiceover}
    GATE3 -- ✅ --> SEO[📊 SEO — Caption + Hashtags]
    GATE3 -- ❌ --> R3[Reject]

    SEO --> GATE4{4️⃣ Gate 4 — Publish}
    GATE4 -- 🚀 Approve --> DIALOG[📅 Schedule Dialog]
    GATE4 -- ❌ --> R4[Reject]

    DIALOG --> BUFFER[📤 Buffer GraphQL → TikTok]
    BUFFER --> RAG[🧠 Update RAG]

    style GATE0 fill:#2196F3,color:#fff
    style GATE1 fill:#2196F3,color:#fff
    style GATE2 fill:#2196F3,color:#fff
    style GATE3 fill:#2196F3,color:#fff
    style GATE4 fill:#FF9800,color:#fff
    style DIALOG fill:#4CAF50,color:#fff
```

### Gate 4 — Publish Flow

1. Pipeline generates SEO caption (Arabic + English), hashtags, and best post time
2. Gate 4 message shows all SEO data in #tiktok-publish
3. You reply with video + thumbnail attachments
4. Click "🚀 موافقة ونشر" → scheduling dialog opens
5. Pick date/time (YYYY-MM-DD HH:MM KSA) or "publish now"
6. Pipeline fetches your uploaded files, pushes to Buffer with schedule

### Approval Gates

| Gate | Channel | What You Review |
|------|---------|-----------------|
| 0️⃣ | #tiktok-plan | Content plan (game, angle, hook) |
| 1️⃣ | #tiktok-news | Scraped news articles |
| 2️⃣ | #tiktok-script | Arabic script + validation scores |
| 3️⃣ | #tiktok-voiceover | ElevenLabs voiceover audio |
| 4️⃣ | #tiktok-publish | SEO caption + hashtags → upload video → schedule |

---

## Pipeline Steps

| Step | File | Description |
|------|------|-------------|
| 1 | `step1_scrape_news.py` | Scrape RSS/Google/Reddit |
| 2 | `step2_generate_script.py` | Generate Arabic TikTok script |
| 3 | `step3_validate_script.py` | AI quality gate + auto-revision |
| 4 | `step4_generate_voiceover.py` | ElevenLabs TTS + timestamps |
| 5 | `step5_publish_tiktok.py` | Generate SEO caption + hashtags |
| 5b | `step5b_buffer_draft.py` | Push to Buffer (text/video/scheduled) |
| 6 | `step6_update_rag.py` | Update RAG memory |

## Content Types

| Type | Description |
|------|-------------|
| `trending_news` | Top 2-3 gaming news stories |
| `game_spotlight` | Deep dive on a single game |
| `trailer_reaction` | Commentary over new trailers |

## Stack Coexistence

| Stack | PostgreSQL | Redis | Trigger | Database |
|-------|-----------|-------|---------|----------|
| **pi_tiktok_stack** | **5434** | **6380** | **10AM** | **tiktok_rag** |
| pi_instagram_stack | 5435 | 6381 | — | instagram_rag |
| pi_x_stack | 5436 | 6382 | 2PM | x_rag |

All stacks share the single n8n instance on port 5678 (host network).

## Docker Services

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| `postgres_tiktok` | `pgvector/pgvector:pg16` | 5434 | Database + vector embeddings |
| `redis_tiktok` | `redis:7-alpine` | 6380 | Rate limiting + budget cache |

## Gemini Model Routing

| Task | Model |
|------|-------|
| Planner | gemini-2.5-flash |
| Scraper | gemini-2.5-flash |
| Validator | gemini-2.5-flash |
| Writer + SEO | gemini-3.1-pro-preview |

## Buffer Integration

Uses Buffer GraphQL API (`https://api.buffer.com/graphql`):
- Channel: `69a9d6033f3b94a1211ca539` (tiktok, @tvv_arabic)
- TikTok requires video attachment (text-only drafts need video added in Buffer UI)

## Quick Start

```bash
cd ~/pi_setup/pi_tiktok_stack
docker compose up -d
# Trigger: POST http://192.168.0.11:5678/webhook/tiktok-manual
```

## n8n Webhooks

| Path | Purpose |
|------|---------|
| `tiktok-manual` | Manual pipeline trigger |
| `tiktok-approve` | Gate approval callback |
| `tiktok-reject` | Gate rejection callback |
| `tiktok-comment` | Comment button → dialog |
| `tiktok-publish-dialog` | Publish approve → scheduling dialog |
| `tiktok-publish-submit` | Dialog submit → fetch files → Buffer |
| `tiktok-dialog-submit` | Comment dialog submit |
| `tiktok-retry-script` | Retry failed script generation |

## Schedule

- **Automatic**: Daily at 10:00 AM via n8n (workflow `6DF7xGPRVtHh0knr`)
- **Manual**: `curl -X POST http://192.168.0.11:5678/webhook/tiktok-manual`

## Project Structure

```
pi_tiktok_stack/
├── config/
│   ├── settings.py
│   └── prompts/
├── database/
│   ├── init.sql, connection.py, rag_manager.py
├── services/
│   ├── gemini_service.py, news_scraper.py
│   ├── mattermost_service.py    # 5-gate HITL + publish dialog
│   └── buffer_service.py        # Buffer GraphQL API
├── processors/
│   ├── planner.py, writer.py, validator.py, clip.py, seo.py
├── pipeline/
│   ├── step1–step6, gate_helper.py
│   ├── open_publish_dialog.py
│   └── handle_publish_submit.py
├── docker-compose.yml
├── n8n_workflow.json
└── .env
```

## License

Private — Adamo-97
