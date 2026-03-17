# pi_x_stack

Automated X/Twitter Arabic gaming content pipeline on Raspberry Pi 5. Generates provocative, debate-provoking Arabic gaming content — scrapes news, writes scripts, validates quality, generates voiceover, and publishes via Buffer's GraphQL API.

## Architecture

```mermaid
C4Context
    title System Context — pi_x_stack

    Person(user, "Content Creator", "Reviews & approves via Mattermost")
    System(x_stack, "pi_x_stack", "Automated X/Twitter pipeline on Raspberry Pi 5")
    System_Ext(gemini, "Google Gemini", "AI text/JSON generation & embeddings")
    System_Ext(elevenlabs, "ElevenLabs", "Arabic TTS with word-level timestamps")
    System_Ext(buffer, "Buffer GraphQL", "X/Twitter publishing via api.buffer.com/graphql")
    System_Ext(mattermost, "Mattermost", "5-gate HITL approval with interactive dialogs")
    System_Ext(news, "News Sources", "RSS feeds, Google News, Reddit")

    Rel(user, mattermost, "Approves/rejects, uploads video, picks schedule")
    Rel(x_stack, gemini, "Generates scripts & embeddings")
    Rel(x_stack, elevenlabs, "Generates Arabic voiceover")
    Rel(x_stack, buffer, "Publishes to X/Twitter")
    Rel(x_stack, mattermost, "Sends approval requests")
    Rel(x_stack, news, "Scrapes gaming news")
    Rel(mattermost, x_stack, "Webhook callbacks (approve/reject/dialog)")
```

## Pipeline Flow (5-Gate Human-in-the-Loop)

```mermaid
flowchart TD
    START([🕐 Daily 2PM / Manual]) --> PLAN[🧠 Planner — RAWG + Breaking News]

    PLAN --> GATE0{0️⃣ Gate 0 — Plan}
    GATE0 -- ✅ --> SCRAPE[📰 Scrape News]
    GATE0 -- ❌ --> R0[Reject]

    SCRAPE --> GATE1{1️⃣ Gate 1 — News}
    GATE1 -- ✅ --> SCRIPT[✍️ Writer — X Script]
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

    DIALOG --> BUFFER[📤 Buffer GraphQL → X]
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
2. Gate 4 message shows all SEO data in #x-publish
3. You reply with video + thumbnail attachments
4. Click "🚀 موافقة ونشر" → scheduling dialog opens
5. Pick date/time (YYYY-MM-DD HH:MM KSA) or "publish now"
6. Pipeline fetches your uploaded files, pushes to Buffer with schedule

### Approval Gates

| Gate | Channel | What You Review |
|------|---------|-----------------|
| 0️⃣ | #x-plan | Content plan (game, hot take angle) |
| 1️⃣ | #x-news | Scraped news articles |
| 2️⃣ | #x-script | Arabic script + validation scores |
| 3️⃣ | #x-voiceover | ElevenLabs voiceover audio |
| 4️⃣ | #x-publish | SEO caption + hashtags → upload video → schedule |

## Pipeline Steps

| Step | File | Description |
|------|------|-------------|
| 1 | `step1_scrape_news.py` | Scrape RSS/Google/Reddit |
| 2 | `step2_generate_script.py` | Generate Arabic X script |
| 3 | `step3_validate_script.py` | AI quality gate + auto-revision |
| 4 | `step4_generate_voiceover.py` | ElevenLabs TTS + timestamps |
| 5 | `step5_publish_x.py` | Generate SEO caption + hashtags |
| 5b | `step5b_buffer_draft.py` | Push to Buffer (text/video/scheduled) |
| 6 | `step6_update_rag.py` | Update RAG memory |

## Content Types

| Type | Description |
|------|-------------|
| `trending_news` | Breaking gaming/hardware news |
| `game_spotlight` | Deep-dive on a specific game |
| `controversial_take` | Provocative industry debate (X-specific) |
| `trailer_reaction` | New trailer analysis |

## Stack Coexistence

| Stack | PostgreSQL | Redis | n8n Webhook | Database |
|-------|-----------|-------|-------------|----------|
| pi_tiktok_stack | 5434 | 6380 | tiktok-manual | tiktok_rag |
| pi_instagram_stack | 5435 | 6381 | instagram-manual | instagram_rag |
| **pi_x_stack** | **5436** | **6382** | **x-manual** | **x_rag** |

All stacks share the single n8n instance on port 5678 (host network).

## Docker Services

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| `postgres_x` | `pgvector/pgvector:pg16` | 5436 | Database + vector embeddings |
| `redis_x` | `redis:7-alpine` | 6382 | Rate limiting + budget cache |

## Gemini Model Routing

| Task | Model |
|------|-------|
| Planner | gemini-2.5-flash |
| Scraper | gemini-2.5-flash |
| Validator | gemini-2.5-flash |
| Writer + SEO | gemini-3.1-pro-preview |

## Buffer Integration

Uses Buffer GraphQL API (`https://api.buffer.com/graphql`):
- Channel: `67ab8b48cc7f0c250ca6c853` (twitter, @TVV_Arabic)
- Supports: text drafts, video posts with thumbnail, custom scheduling
- X allows text-only posts (unlike TikTok/Instagram which require video)

## Quick Start

```bash
cd ~/pi_setup/pi_x_stack
docker compose up -d
# Trigger: POST http://192.168.0.11:5678/webhook/x-manual
```

## Schedule

- **Automatic**: Daily at 2:00 PM via n8n (workflow `CnwyI8DuWp33iveC`)
- **Manual**: `curl -X POST http://192.168.0.11:5678/webhook/x-manual`

## n8n Webhooks

| Path | Purpose |
|------|---------|
| `x-manual` | Manual pipeline trigger |
| `x-approve` | Gate approval callback |
| `x-reject` | Gate rejection callback |
| `x-comment` | Comment button → dialog |
| `x-publish-dialog` | Publish approve → scheduling dialog |
| `x-publish-submit` | Dialog submit → fetch files → Buffer |
| `x-dialog-submit` | Comment dialog submit |
| `x-retry-script` | Retry failed script generation |

## Project Structure

```
pi_x_stack/
├── config/
│   ├── settings.py
│   └── prompts/
├── database/
│   ├── init.sql
│   ├── connection.py
│   └── rag_manager.py
├── services/
│   ├── gemini_service.py
│   ├── news_scraper.py
│   ├── mattermost_service.py    # 5-gate HITL + publish dialog
│   └── buffer_service.py        # Buffer GraphQL API
├── processors/
│   ├── planner.py, writer.py, validator.py, clip.py, seo.py
├── pipeline/
│   ├── step1_scrape_news.py
│   ├── step2_generate_script.py
│   ├── step3_validate_script.py
│   ├── step4_generate_voiceover.py
│   ├── step5_publish_x.py          # SEO generation
│   ├── step5b_buffer_draft.py      # Buffer push
│   ├── step6_update_rag.py
│   ├── gate_helper.py
│   ├── open_publish_dialog.py      # Mattermost scheduling dialog
│   └── handle_publish_submit.py    # Dialog submit → Buffer
├── docker-compose.yml
├── n8n_workflow.json
└── .env
```

## License

Private — Adamo-97
