# -*- coding: utf-8 -*-
"""
Data Models
============
Pydantic models representing database entities.
Used for validation, serialization, and clean data passing
between agents, services, and scripts.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Game Models
# ---------------------------------------------------------------------------


class ArabicSupport(BaseModel):
    """Arabic language support details for a game."""

    has_arabic: bool = False
    arabic_type: Optional[str] = None  # "subtitles" | "dubbing" | "interface"
    quality_note: Optional[str] = None


class Game(BaseModel):
    """Represents a game record from the database."""

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    rawg_id: Optional[int] = None
    title: str
    title_ar: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    release_date: Optional[date] = None
    platforms: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    developers: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)
    price: Optional[str] = None
    gamepass: bool = False
    arabic_support: ArabicSupport = Field(default_factory=ArabicSupport)
    metacritic: Optional[int] = None
    rating: Optional[float] = None
    background_image: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Script Models
# ---------------------------------------------------------------------------


class GeneratedScript(BaseModel):
    """Represents a generated YouTube script."""

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    content_type: str
    title: str
    script_text: str
    word_count: Optional[int] = None
    target_duration: Optional[float] = None
    game_ids: list[uuid.UUID] = Field(default_factory=list)
    status: str = "draft"
    version: int = 1
    parent_id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Validation Models
# ---------------------------------------------------------------------------


class ValidationScores(BaseModel):
    """Detailed validation scores from the Validator Agent."""

    accuracy: int = 0
    language_quality: int = 0
    hook_strength: int = 0
    retention_potential: int = 0
    tone_and_style: int = 0
    structure: int = 0
    length_appropriateness: int = 0
    cta_effectiveness: int = 0


class ValidationResult(BaseModel):
    """Complete validation result from the Validator Agent."""

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    script_id: uuid.UUID
    approved: bool
    overall_score: int
    scores: ValidationScores
    critical_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    revised_sections: dict[str, str] = Field(default_factory=dict)
    summary: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Metadata Models
# ---------------------------------------------------------------------------


class TitleSuggestion(BaseModel):
    """A suggested YouTube title with reasoning."""

    title: str
    reasoning: str


class GameInfoCard(BaseModel):
    """Game info card for the video description/metadata."""

    game_title: str
    game_title_ar: Optional[str] = None
    platforms: list[str] = Field(default_factory=list)
    price: Optional[str] = None
    gamepass: bool = False
    arabic_support: ArabicSupport = Field(default_factory=ArabicSupport)
    release_date: Optional[str] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None
    genre: Optional[str] = None


class VideoMetadata(BaseModel):
    """Complete YouTube metadata for a video."""

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    script_id: uuid.UUID
    titles: list[TitleSuggestion] = Field(default_factory=list)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    game_info_cards: list[GameInfoCard] = Field(default_factory=list)
    thumbnail_suggestions: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Voiceover Models
# ---------------------------------------------------------------------------


class Voiceover(BaseModel):
    """Represents a generated voiceover audio file."""

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    script_id: uuid.UUID
    file_path: str
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    elevenlabs_id: Optional[str] = None
    status: str = "generated"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Feedback Models
# ---------------------------------------------------------------------------


class Feedback(BaseModel):
    """Human feedback record."""

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    script_id: Optional[uuid.UUID] = None
    feedback_type: str  # "approval" | "rejection" | "edit" | "note"
    feedback_text: Optional[str] = None
    source: str = "slack"
    applied: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Pipeline Models
# ---------------------------------------------------------------------------


class PipelineRun(BaseModel):
    """Tracks a single execution of the content generation pipeline."""

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    content_type: str
    trigger_source: str  # "schedule" | "manual" | "n8n"
    status: str = "started"
    script_id: Optional[uuid.UUID] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# RAG Embedding Model
# ---------------------------------------------------------------------------


class RAGEmbedding(BaseModel):
    """A stored embedding for RAG retrieval."""

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)
    source_type: str  # "script" | "feedback" | "game" | "validation"
    source_id: Optional[uuid.UUID] = None
    content_text: str
    content_summary: Optional[str] = None
    embedding: Optional[list[float]] = None  # Vector stored separately
    metadata: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
