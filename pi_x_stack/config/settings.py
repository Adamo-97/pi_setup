# -*- coding: utf-8 -*-
"""
Central Configuration
=====================
Loads all environment variables from .env and exposes them as frozen dataclasses.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Resolve project root and load .env
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str = ""
    model: str = "gemini-2.5-pro"
    embedding_model: str = "models/embedding-001"
    temperature: float = 0.8
    max_output_tokens: int = 4096


@dataclass(frozen=True)
class ElevenLabsConfig:
    api_key: str = ""
    voice_id: str = ""
    model: str = "eleven_multilingual_v2"
    output_format: str = "pcm_44100"
    sample_rate: int = 44100


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5436
    name: str = "x_rag"
    user: str = "x_user"
    password: str = "x_secure_pass_2025"
    min_connections: int = 1
    max_connections: int = 5


@dataclass(frozen=True)
class MattermostConfig:
    url: str = ""
    bot_token: str = ""
    channel_id: str = ""


@dataclass(frozen=True)
class BufferConfig:
    access_token: str = ""
    profile_id: str = ""
    api_base: str = "https://api.bufferapp.com/1"


@dataclass(frozen=True)
class RedisConfig:
    url: str = "redis://localhost:6382"
    max_memory: str = "64mb"
    ttl_seconds: int = 604800  # 7-day budget key TTL


@dataclass(frozen=True)
class BudgetConfig:
    nextcloud_url: str = "http://192.168.1.100:8080"
    nextcloud_user: str = ""
    nextcloud_password: str = ""
    nextcloud_path: str = "/remote.php/dav/files/admin/pi_config/budgets.json"
    local_fallback_path: str = "config/budgets.json"
    cache_ttl_seconds: int = 3600  # 1-hour Redis cache


@dataclass(frozen=True)
class SharedRAWGConfig:
    host: str = "192.168.1.100"
    port: int = 5433
    database: str = "youtube_rag"
    user: str = "yt_readonly"
    password: str = "readonly_pass_2025"


@dataclass(frozen=True)
class N8NConfig:
    webhook_base: str = "http://localhost:5681/webhook"


@dataclass(frozen=True)
class NewsConfig:
    # RSS feeds — gaming + controversy-generating sources
    rss_feeds: tuple = (
        "https://www.ign.com/articles.rss",
        "https://kotaku.com/rss",
        "https://www.pcgamer.com/rss/",
        "https://www.gamespot.com/feeds/mashup/",
        "https://www.eurogamer.net/feed",
        "https://www.theverge.com/games/rss/index.xml",
    )
    # SerpApi (Google News)
    serpapi_key: str = ""
    serpapi_engine: str = "google_news"
    # Reddit — gaming + controversy/debate subreddits
    reddit_subreddits: tuple = (
        "gaming",
        "Games",
        "pcgaming",
        "gamingcirclejerk",
        "truegaming",
        "PatientGamers",
    )
    reddit_user_agent: str = "pi_x_stack/1.0"
    # Scraping limits
    max_articles_per_source: int = 15
    max_age_hours: int = 48


@dataclass(frozen=True)
class VideoConfig:
    # yt-dlp
    yt_dlp_format: str = (
        "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"
    )
    max_download_duration: int = 600  # 10 min max trailer length
    # Local fallback
    local_footage_dir: str = "footage"
    # Assembly
    output_width: int = 1080
    output_height: int = 1920
    fps: int = 30
    target_duration_min: int = 30
    target_duration_max: int = 60
    # Subtitles
    subtitle_font: str = "Arial"
    subtitle_font_size: int = 64
    subtitle_highlight_color: str = "#FFD700"  # Gold
    subtitle_normal_color: str = "#FFFFFF"  # White
    subtitle_bg_color: str = "#00000099"  # Semi-transparent black
    subtitle_position: str = "center"  # center of screen


@dataclass(frozen=True)
class PathsConfig:
    output_audio: str = "output/audio"
    output_video: str = "output/video"
    output_clips: str = "output/clips"
    output_thumbnails: str = "output/thumbnails"
    logs: str = "logs"


@dataclass(frozen=True)
class ContentTypeConfig:
    name: str = ""
    schedule_type: str = "daily"  # daily | event | manual
    description: str = ""
    target_duration: int = 45  # seconds


# ---------------------------------------------------------------------------
# Content type registry
# ---------------------------------------------------------------------------
CONTENT_TYPES: Dict[str, ContentTypeConfig] = {
    "trending_news": ContentTypeConfig(
        name="trending_news",
        schedule_type="daily",
        description="Fast-paced trending gaming news roundup with hot takes",
        target_duration=45,
    ),
    "game_spotlight": ContentTypeConfig(
        name="game_spotlight",
        schedule_type="event",
        description="Deep spotlight on a single hot game",
        target_duration=60,
    ),
    "controversial_take": ContentTypeConfig(
        name="controversial_take",
        schedule_type="event",
        description="Provocative industry debate or unpopular gaming opinion",
        target_duration=50,
    ),
    "trailer_reaction": ContentTypeConfig(
        name="trailer_reaction",
        schedule_type="event",
        description="AI commentary over a game trailer with clips",
        target_duration=55,
    ),
}


def get_content_type(name: str) -> Optional[ContentTypeConfig]:
    """Look up a content type by name."""
    return CONTENT_TYPES.get(name)


# ---------------------------------------------------------------------------
# Lazy-loaded global settings
# ---------------------------------------------------------------------------
class _Settings:
    """Lazy singleton — reads env vars on first access."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def _load(self):
        if self._loaded:
            return
        e = os.environ.get

        self.gemini = GeminiConfig(
            api_key=e("GEMINI_API_KEY", ""),
            model=e("GEMINI_MODEL", "gemini-2.5-pro"),
            embedding_model=e("GEMINI_EMBEDDING_MODEL", "models/embedding-001"),
            temperature=float(e("GEMINI_TEMPERATURE", "0.8")),
            max_output_tokens=int(e("GEMINI_MAX_TOKENS", "4096")),
        )
        self.elevenlabs = ElevenLabsConfig(
            api_key=e("ELEVENLABS_API_KEY", ""),
            voice_id=e("ELEVENLABS_VOICE_ID", ""),
            model=e("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        )
        self.database = DatabaseConfig(
            host=e("DB_HOST", "localhost"),
            port=int(e("DB_PORT", "5436")),
            name=e("DB_NAME", "x_rag"),
            user=e("DB_USER", "x_user"),
            password=e("DB_PASSWORD", "x_secure_pass_2025"),
        )
        self.mattermost = MattermostConfig(
            url=e("MATTERMOST_URL", ""),
            bot_token=e("MATTERMOST_BOT_TOKEN", ""),
            channel_id=e("MATTERMOST_CHANNEL_ID", ""),
        )
        self.buffer = BufferConfig(
            access_token=e("BUFFER_ACCESS_TOKEN", ""),
            profile_id=e("BUFFER_PROFILE_ID", ""),
        )
        self.n8n = N8NConfig(
            webhook_base=e("N8N_WEBHOOK_BASE", "http://localhost:5681/webhook"),
        )
        self.news = NewsConfig(
            serpapi_key=e("SERPAPI_KEY", ""),
        )
        self.video = VideoConfig()
        self.paths = PathsConfig()
        self.redis = RedisConfig(
            url=e("REDIS_URL", "redis://localhost:6382"),
            max_memory=e("REDIS_MAX_MEMORY", "64mb"),
            ttl_seconds=int(e("REDIS_BUDGET_TTL", "604800")),
        )
        self.budget = BudgetConfig(
            nextcloud_url=e("NEXTCLOUD_URL", "http://192.168.1.100:8080"),
            nextcloud_user=e("NEXTCLOUD_USER", ""),
            nextcloud_password=e("NEXTCLOUD_PASSWORD", ""),
            nextcloud_path=e(
                "NEXTCLOUD_BUDGETS_PATH",
                "/remote.php/dav/files/admin/pi_config/budgets.json",
            ),
            local_fallback_path=e("BUDGETS_LOCAL_PATH", "config/budgets.json"),
            cache_ttl_seconds=int(e("BUDGET_CACHE_TTL", "3600")),
        )
        self.shared_rawg = SharedRAWGConfig(
            host=e("SHARED_RAWG_HOST", "192.168.1.100"),
            port=int(e("SHARED_RAWG_PORT", "5433")),
            database=e("SHARED_RAWG_DB", "youtube_rag"),
            user=e("SHARED_RAWG_USER", "yt_readonly"),
            password=e("SHARED_RAWG_PASSWORD", "readonly_pass_2025"),
        )

        self._loaded = True

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        self._load()
        return self.__dict__[name]


settings = _Settings()


def get_settings() -> _Settings:
    """Return the global settings singleton."""
    return settings
