-- ============================================================
-- pi_tiktok_stack — PostgreSQL Schema (pgvector)
-- ============================================================
-- Auto-executed on first docker-compose up via init.sql mount.
-- ============================================================

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------
-- 1. News articles (scraped from RSS, Google News, Reddit)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_articles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50)  NOT NULL,               -- rss | google_news | reddit
    source_url      TEXT         NOT NULL UNIQUE,
    title           TEXT         NOT NULL,
    summary         TEXT,
    full_text       TEXT,
    category        VARCHAR(100),
    published_at    TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ  DEFAULT NOW(),
    used            BOOLEAN      DEFAULT FALSE,
    metadata        JSONB        DEFAULT '{}',
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_source ON news_articles(source);
CREATE INDEX IF NOT EXISTS idx_news_used ON news_articles(used);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles(published_at DESC);

-- -----------------------------------------------------------
-- 2. Generated scripts
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS generated_scripts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type    VARCHAR(50)  NOT NULL,
    title           VARCHAR(500),
    script_text     TEXT         NOT NULL,
    word_count      INTEGER,
    estimated_duration FLOAT,
    news_ids        UUID[]       DEFAULT '{}',           -- refs to news_articles used
    status          VARCHAR(30)  DEFAULT 'draft',        -- draft | validated | rejected | approved | published
    trigger_source  VARCHAR(30)  DEFAULT 'schedule',     -- schedule | manual | event
    version         INTEGER      DEFAULT 1,
    parent_id       UUID         REFERENCES generated_scripts(id),
    metadata        JSONB        DEFAULT '{}',
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scripts_status ON generated_scripts(status);
CREATE INDEX IF NOT EXISTS idx_scripts_type ON generated_scripts(content_type);

-- -----------------------------------------------------------
-- 3. Validations
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS validations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    script_id       UUID         NOT NULL REFERENCES generated_scripts(id),
    approved        BOOLEAN      NOT NULL,
    overall_score   FLOAT        NOT NULL,
    scores          JSONB        NOT NULL,               -- per-criterion scores
    critical_issues JSONB        DEFAULT '[]',
    suggestions     JSONB        DEFAULT '[]',
    summary         TEXT,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- -----------------------------------------------------------
-- 4. Voiceovers
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS voiceovers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    script_id       UUID         NOT NULL REFERENCES generated_scripts(id),
    file_path       TEXT         NOT NULL,
    duration        FLOAT,
    word_timestamps JSONB        DEFAULT '[]',           -- [{word, start, end}, ...]
    sample_rate     INTEGER      DEFAULT 44100,
    format          VARCHAR(10)  DEFAULT 'wav',
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- -----------------------------------------------------------
-- 5. Video footage (downloaded clips / trailers)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS video_footage (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(30)  NOT NULL,               -- youtube | local
    source_url      TEXT,
    file_path       TEXT         NOT NULL,
    title           TEXT,
    duration        FLOAT,
    width           INTEGER,
    height          INTEGER,
    game_title      VARCHAR(300),
    clip_type       VARCHAR(30)  DEFAULT 'gameplay',     -- gameplay | trailer | cinematic
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- -----------------------------------------------------------
-- 6. Rendered videos (final TikTok output)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS rendered_videos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    script_id       UUID         NOT NULL REFERENCES generated_scripts(id),
    voiceover_id    UUID         REFERENCES voiceovers(id),
    footage_id      UUID         REFERENCES video_footage(id),
    file_path       TEXT         NOT NULL,
    duration        FLOAT,
    width           INTEGER      DEFAULT 1080,
    height          INTEGER      DEFAULT 1920,
    status          VARCHAR(30)  DEFAULT 'rendered',     -- rendered | approved | published
    buffer_update_id TEXT,                                -- Buffer API update ID
    published_at    TIMESTAMPTZ,
    metadata        JSONB        DEFAULT '{}',
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- -----------------------------------------------------------
-- 7. RAG embeddings (vector search)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_embeddings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type     VARCHAR(50)  NOT NULL,               -- script | feedback | news
    source_id       UUID,
    content_text    TEXT         NOT NULL,
    content_summary VARCHAR(500),
    embedding       vector(768)  NOT NULL,
    metadata        JSONB        DEFAULT '{}',
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_source ON rag_embeddings(source_type);
CREATE INDEX IF NOT EXISTS idx_rag_embedding ON rag_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- -----------------------------------------------------------
-- 8. Feedback log
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    script_id       UUID         REFERENCES generated_scripts(id),
    video_id        UUID         REFERENCES rendered_videos(id),
    feedback_type   VARCHAR(30)  NOT NULL,               -- approval | rejection | edit | note
    feedback_text   TEXT,
    source          VARCHAR(30)  DEFAULT 'slack',        -- slack | manual
    applied         BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- -----------------------------------------------------------
-- 9. Pipeline runs (execution tracking)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type    VARCHAR(50)  NOT NULL,
    trigger_source  VARCHAR(30)  DEFAULT 'schedule',
    status          VARCHAR(30)  DEFAULT 'started',      -- started | completed | failed
    step            VARCHAR(50),
    script_id       UUID         REFERENCES generated_scripts(id),
    video_id        UUID         REFERENCES rendered_videos(id),
    error_message   TEXT,
    started_at      TIMESTAMPTZ  DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    metadata        JSONB        DEFAULT '{}'
);

-- -----------------------------------------------------------
-- Auto-update updated_at trigger
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY[
            'news_articles', 'generated_scripts', 'rendered_videos'
        ])
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_updated_%I ON %I; '
            'CREATE TRIGGER trg_updated_%I BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION update_updated_at();',
            t, t, t, t
        );
    END LOOP;
END;
$$;
