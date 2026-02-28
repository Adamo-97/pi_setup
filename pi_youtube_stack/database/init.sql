-- ============================================================================
-- YouTube RAG Database — Schema Initialization
-- ============================================================================
-- This script runs automatically on first PostgreSQL container start via
-- docker-entrypoint-initdb.d. It creates all tables, indexes, and the
-- pgvector extension needed for the RAG system.
-- ============================================================================

-- Enable pgvector extension for embedding storage & similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable uuid generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. Games — master game data fetched from RAWG & enriched
-- ============================================================================
CREATE TABLE IF NOT EXISTS games (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rawg_id         INTEGER UNIQUE,              -- RAWG.io game ID
    title           TEXT NOT NULL,                -- English title
    title_ar        TEXT,                         -- Arabic title (if known)
    slug            TEXT,                         -- URL-friendly slug
    description     TEXT,                         -- Game description
    release_date    DATE,                         -- Release date
    platforms       JSONB DEFAULT '[]'::jsonb,    -- ["PS5","Xbox Series X","PC"]
    genres          JSONB DEFAULT '[]'::jsonb,    -- ["Action","RPG"]
    developers      JSONB DEFAULT '[]'::jsonb,    -- Developer names
    publishers      JSONB DEFAULT '[]'::jsonb,    -- Publisher names
    price           TEXT,                         -- Price string (region-specific)
    gamepass        BOOLEAN DEFAULT FALSE,        -- Available on Game Pass?
    arabic_support  JSONB DEFAULT '{}'::jsonb,    -- {"has_arabic": true, "type": "subtitles"}
    metacritic      INTEGER,                      -- Metacritic score
    rating          FLOAT,                        -- RAWG community rating
    background_image TEXT,                        -- Cover image URL
    rawg_data       JSONB DEFAULT '{}'::jsonb,    -- Full RAWG API response (backup)
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_games_release_date ON games(release_date);
CREATE INDEX IF NOT EXISTS idx_games_slug ON games(slug);
CREATE INDEX IF NOT EXISTS idx_games_rawg_id ON games(rawg_id);

-- ============================================================================
-- 2. Generated Scripts — every script draft produced by the Writer Agent
-- ============================================================================
CREATE TABLE IF NOT EXISTS generated_scripts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type    TEXT NOT NULL,                -- "monthly_releases" | "aaa_review" | "upcoming_games"
    title           TEXT NOT NULL,                -- Working title
    script_text     TEXT NOT NULL,                -- Full Arabic script
    word_count      INTEGER,                      -- Calculated word count
    target_duration FLOAT,                        -- Target video duration (minutes)
    game_ids        UUID[] DEFAULT '{}',          -- References to games table
    status          TEXT DEFAULT 'draft',         -- draft | validated | approved | rejected | produced
    version         INTEGER DEFAULT 1,            -- Script revision number
    parent_id       UUID REFERENCES generated_scripts(id), -- Previous version
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scripts_content_type ON generated_scripts(content_type);
CREATE INDEX IF NOT EXISTS idx_scripts_status ON generated_scripts(status);
CREATE INDEX IF NOT EXISTS idx_scripts_created ON generated_scripts(created_at DESC);

-- ============================================================================
-- 3. Validations — Validator Agent review results
-- ============================================================================
CREATE TABLE IF NOT EXISTS validations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    script_id       UUID NOT NULL REFERENCES generated_scripts(id) ON DELETE CASCADE,
    approved        BOOLEAN NOT NULL,
    overall_score   INTEGER NOT NULL,            -- 0-100
    scores          JSONB NOT NULL,              -- Detailed sub-scores
    critical_issues JSONB DEFAULT '[]'::jsonb,   -- List of critical problems
    suggestions     JSONB DEFAULT '[]'::jsonb,   -- Improvement suggestions
    revised_sections JSONB DEFAULT '{}'::jsonb,  -- Suggested rewrites
    summary         TEXT,                        -- Review summary
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validations_script ON validations(script_id);

-- ============================================================================
-- 4. Metadata — YouTube SEO metadata for each script
-- ============================================================================
CREATE TABLE IF NOT EXISTS metadata (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    script_id       UUID NOT NULL REFERENCES generated_scripts(id) ON DELETE CASCADE,
    titles          JSONB NOT NULL,              -- Array of title suggestions
    description     TEXT NOT NULL,               -- YouTube description
    tags            JSONB DEFAULT '[]'::jsonb,   -- Tag array
    hashtags        JSONB DEFAULT '[]'::jsonb,   -- Hashtag array
    game_info_cards JSONB DEFAULT '[]'::jsonb,   -- Game info cards
    thumbnail_suggestions JSONB DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metadata_script ON metadata(script_id);

-- ============================================================================
-- 5. Voiceovers — ElevenLabs generated audio files
-- ============================================================================
CREATE TABLE IF NOT EXISTS voiceovers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    script_id       UUID NOT NULL REFERENCES generated_scripts(id) ON DELETE CASCADE,
    file_path       TEXT NOT NULL,               -- Path to .wav file on disk
    file_size_bytes BIGINT,                      -- File size
    duration_seconds FLOAT,                      -- Audio duration
    elevenlabs_id   TEXT,                        -- ElevenLabs generation ID
    status          TEXT DEFAULT 'generated',    -- generated | approved | rejected
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_voiceovers_script ON voiceovers(script_id);

-- ============================================================================
-- 6. RAG Embeddings — vector embeddings for semantic search
-- ============================================================================
-- Stores embeddings of scripts, feedback, and game data for deduplication
-- and context retrieval. Dimension matches Gemini embedding output (768).
CREATE TABLE IF NOT EXISTS rag_embeddings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type     TEXT NOT NULL,               -- "script" | "feedback" | "game" | "validation"
    source_id       UUID,                        -- Reference to source record
    content_text    TEXT NOT NULL,                -- The text that was embedded
    content_summary TEXT,                        -- Short summary for display
    embedding       vector(768),                 -- pgvector embedding column
    metadata        JSONB DEFAULT '{}'::jsonb,   -- Extra context stored alongside
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX IF NOT EXISTS idx_rag_embedding_hnsw
    ON rag_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_rag_source_type ON rag_embeddings(source_type);

-- ============================================================================
-- 7. Feedback Log — human feedback for continuous learning
-- ============================================================================
CREATE TABLE IF NOT EXISTS feedback_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    script_id       UUID REFERENCES generated_scripts(id),
    feedback_type   TEXT NOT NULL,               -- "approval" | "rejection" | "edit" | "note"
    feedback_text   TEXT,                        -- Human feedback content
    source          TEXT DEFAULT 'slack',        -- Where feedback came from
    applied         BOOLEAN DEFAULT FALSE,       -- Has this been processed by RAG?
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_script ON feedback_log(script_id);
CREATE INDEX IF NOT EXISTS idx_feedback_applied ON feedback_log(applied);

-- ============================================================================
-- 8. Pipeline Runs — track each execution of the content pipeline
-- ============================================================================
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type    TEXT NOT NULL,
    trigger_source  TEXT NOT NULL,               -- "schedule" | "manual" | "n8n"
    status          TEXT DEFAULT 'started',      -- started | writing | validating | awaiting_approval | generating_audio | completed | failed
    script_id       UUID REFERENCES generated_scripts(id),
    error_message   TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pipeline_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_started ON pipeline_runs(started_at DESC);

-- ============================================================================
-- Helper function: auto-update updated_at timestamp
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables with updated_at
CREATE TRIGGER update_games_updated_at
    BEFORE UPDATE ON games
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_scripts_updated_at
    BEFORE UPDATE ON generated_scripts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
