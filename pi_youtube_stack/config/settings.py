# -*- coding: utf-8 -*-
"""
Central Configuration Module
=============================
Loads all environment variables and provides typed, validated settings
for every service in the YouTube content generation stack.

All secrets and configuration values are read from the .env file
at the project root. Sensible defaults are provided where possible.
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Resolve project root (two levels up from config/settings.py)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# Load .env file — override=False keeps existing environment values
load_dotenv(dotenv_path=ENV_PATH, override=False)


def _require_env(key: str) -> str:
    """Return an env var or raise a clear error at startup."""
    value = os.getenv(key)
    if not value:
        print(
            f"[CONFIG ERROR] Required environment variable '{key}' is not set. "
            f"Check your .env file at: {ENV_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


# ---------------------------------------------------------------------------
# Data classes — grouped, typed, immutable-ish configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeminiConfig:
    """Google Gemini API configuration."""

    api_key: str
    model: str
    temperature: float
    max_output_tokens: int
    top_p: float
    top_k: int


@dataclass(frozen=True)
class ElevenLabsConfig:
    """ElevenLabs TTS API configuration."""

    api_key: str
    voice_id: str
    model_id: str
    output_format: str
    stability: float
    similarity_boost: float
    style: float


@dataclass(frozen=True)
class RAWGConfig:
    """RAWG.io game database API configuration."""

    api_key: str
    base_url: str
    page_size: int


@dataclass(frozen=True)
class DatabaseConfig:
    """PostgreSQL (pgvector) database configuration."""

    host: str
    port: int
    name: str
    user: str
    password: str
    embedding_dimension: int

    @property
    def connection_string(self) -> str:
        """Build a psycopg2-compatible DSN."""
        return (
            f"host={self.host} port={self.port} dbname={self.name} "
            f"user={self.user} password={self.password}"
        )

    @property
    def async_url(self) -> str:
        """Build an asyncpg-compatible URL."""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


@dataclass(frozen=True)
class SlackConfig:
    """Slack webhook configuration for human-in-the-loop approval."""

    webhook_url: str
    approval_channel: str
    bot_token: str


@dataclass(frozen=True)
class N8NConfig:
    """n8n connection details (for callback webhooks)."""

    base_url: str
    webhook_path_approve_script: str
    webhook_path_approve_audio: str


@dataclass(frozen=True)
class PathsConfig:
    """All filesystem paths used by the stack."""

    project_root: Path
    output_scripts: Path
    output_voiceovers: Path
    output_metadata: Path
    logs: Path


@dataclass(frozen=True)
class ContentTypeConfig:
    """Definition of a single content type (extensible registry)."""

    type_id: str  # e.g. "monthly_releases"
    display_name: str  # e.g. "Monthly Game Releases"
    description: str  # Used in prompts for context
    schedule_day: int  # Day of month (0 = manual/event-based)
    schedule_type: str  # "monthly" | "event" | "manual"


# ---------------------------------------------------------------------------
# Build configuration instances from environment
# ---------------------------------------------------------------------------


def _build_gemini() -> GeminiConfig:
    return GeminiConfig(
        api_key=_require_env("GEMINI_API_KEY"),
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-pro"),
        temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.8")),
        max_output_tokens=int(os.getenv("GEMINI_MAX_TOKENS", "8192")),
        top_p=float(os.getenv("GEMINI_TOP_P", "0.95")),
        top_k=int(os.getenv("GEMINI_TOP_K", "40")),
    )


def _build_elevenlabs() -> ElevenLabsConfig:
    return ElevenLabsConfig(
        api_key=_require_env("ELEVENLABS_API_KEY"),
        voice_id=_require_env("ELEVENLABS_VOICE_ID"),
        model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
        output_format=os.getenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_44100"),
        stability=float(os.getenv("ELEVENLABS_STABILITY", "0.5")),
        similarity_boost=float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.75")),
        style=float(os.getenv("ELEVENLABS_STYLE", "0.4")),
    )


def _build_rawg() -> RAWGConfig:
    return RAWGConfig(
        api_key=_require_env("RAWG_API_KEY"),
        base_url=os.getenv("RAWG_BASE_URL", "https://api.rawg.io/api"),
        page_size=int(os.getenv("RAWG_PAGE_SIZE", "20")),
    )


def _build_database() -> DatabaseConfig:
    return DatabaseConfig(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        name=os.getenv("POSTGRES_DB", "youtube_rag"),
        user=os.getenv("POSTGRES_USER", "yt_user"),
        password=_require_env("POSTGRES_PASSWORD"),
        embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION", "768")),
    )


def _build_slack() -> SlackConfig:
    return SlackConfig(
        webhook_url=_require_env("SLACK_WEBHOOK_URL"),
        approval_channel=os.getenv("SLACK_APPROVAL_CHANNEL", "#youtube-approvals"),
        bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
    )


def _build_n8n() -> N8NConfig:
    return N8NConfig(
        base_url=os.getenv("N8N_BASE_URL", "http://localhost:5678"),
        webhook_path_approve_script=os.getenv(
            "N8N_WEBHOOK_APPROVE_SCRIPT", "/webhook/approve-script"
        ),
        webhook_path_approve_audio=os.getenv(
            "N8N_WEBHOOK_APPROVE_AUDIO", "/webhook/approve-audio"
        ),
    )


def _build_paths() -> PathsConfig:
    root = PROJECT_ROOT
    paths = PathsConfig(
        project_root=root,
        output_scripts=root / "output" / "scripts",
        output_voiceovers=root / "output" / "voiceovers",
        output_metadata=root / "output" / "metadata",
        logs=root / "logs",
    )
    # Ensure all output directories exist
    for p in [
        paths.output_scripts,
        paths.output_voiceovers,
        paths.output_metadata,
        paths.logs,
    ]:
        p.mkdir(parents=True, exist_ok=True)
    return paths


# ---------------------------------------------------------------------------
# Content type registry — add new types here to extend the system
# ---------------------------------------------------------------------------
CONTENT_TYPES: list[ContentTypeConfig] = [
    ContentTypeConfig(
        type_id="monthly_releases",
        display_name="إصدارات الشهر",
        description=(
            "A comprehensive roundup of all major game releases for the current month. "
            "Covers release dates, platforms, pricing, Game Pass availability, "
            "and Arabic language support."
        ),
        schedule_day=25,
        schedule_type="monthly",
    ),
    ContentTypeConfig(
        type_id="aaa_review",
        display_name="مراجعة لعبة AAA",
        description=(
            "An in-depth review of a major AAA game title. Covers gameplay, "
            "story, graphics, performance, value for money, and Arabic support. "
            "Triggered mid-month or when a major title launches."
        ),
        schedule_day=0,
        schedule_type="event",
    ),
    ContentTypeConfig(
        type_id="upcoming_games",
        display_name="ألعاب قادمة",
        description=(
            "A preview of exciting upcoming game releases. Covers trailers, "
            "expected features, developer track record, and hype analysis. "
            "Triggered when major announcements or showcases occur."
        ),
        schedule_day=0,
        schedule_type="event",
    ),
]


def get_content_type(type_id: str) -> ContentTypeConfig:
    """Look up a content type by its ID. Raises ValueError if not found."""
    for ct in CONTENT_TYPES:
        if ct.type_id == type_id:
            return ct
    valid_ids = [ct.type_id for ct in CONTENT_TYPES]
    raise ValueError(f"Unknown content type '{type_id}'. Valid types: {valid_ids}")


# ---------------------------------------------------------------------------
# Lazy-loaded singleton settings — import and use directly
# ---------------------------------------------------------------------------


class _Settings:
    """Lazy-loading settings container. Configs are built on first access."""

    def __init__(self):
        self._gemini = None
        self._elevenlabs = None
        self._rawg = None
        self._database = None
        self._slack = None
        self._n8n = None
        self._paths = None

    @property
    def gemini(self) -> GeminiConfig:
        if self._gemini is None:
            self._gemini = _build_gemini()
        return self._gemini

    @property
    def elevenlabs(self) -> ElevenLabsConfig:
        if self._elevenlabs is None:
            self._elevenlabs = _build_elevenlabs()
        return self._elevenlabs

    @property
    def rawg(self) -> RAWGConfig:
        if self._rawg is None:
            self._rawg = _build_rawg()
        return self._rawg

    @property
    def database(self) -> DatabaseConfig:
        if self._database is None:
            self._database = _build_database()
        return self._database

    @property
    def slack(self) -> SlackConfig:
        if self._slack is None:
            self._slack = _build_slack()
        return self._slack

    @property
    def n8n(self) -> N8NConfig:
        if self._n8n is None:
            self._n8n = _build_n8n()
        return self._n8n

    @property
    def paths(self) -> PathsConfig:
        if self._paths is None:
            self._paths = _build_paths()
        return self._paths


# Global settings instance — usage: `from config.settings import settings`
settings = _Settings()
