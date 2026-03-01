# -*- coding: utf-8 -*-
"""
Pydantic Models
===============
Data models for every entity in the Instagram Reels pipeline.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NewsArticle(BaseModel):
    id: Optional[UUID] = None
    source: str
    source_url: str
    title: str
    summary: Optional[str] = None
    full_text: Optional[str] = None
    category: Optional[str] = None
    published_at: Optional[datetime] = None
    used: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class GeneratedScript(BaseModel):
    id: Optional[UUID] = None
    content_type: str
    title: Optional[str] = None
    script_text: str
    word_count: Optional[int] = None
    estimated_duration: Optional[float] = None
    news_ids: List[UUID] = Field(default_factory=list)
    status: str = "draft"
    trigger_source: str = "schedule"
    version: int = 1
    parent_id: Optional[UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ValidationScores(BaseModel):
    hook_strength: float = 0
    accuracy: float = 0
    pacing: float = 0
    engagement: float = 0
    language_quality: float = 0
    cta_effectiveness: float = 0
    instagram_fit: float = 0


class ValidationResult(BaseModel):
    id: Optional[UUID] = None
    script_id: Optional[UUID] = None
    approved: bool = False
    overall_score: float = 0
    scores: ValidationScores = Field(default_factory=ValidationScores)
    critical_issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    summary: Optional[str] = None

    class Config:
        from_attributes = True


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float


class Voiceover(BaseModel):
    id: Optional[UUID] = None
    script_id: Optional[UUID] = None
    file_path: str = ""
    duration: Optional[float] = None
    word_timestamps: List[WordTimestamp] = Field(default_factory=list)
    sample_rate: int = 44100
    format: str = "wav"

    class Config:
        from_attributes = True


class VideoFootage(BaseModel):
    id: Optional[UUID] = None
    source: str = "youtube"
    source_url: Optional[str] = None
    file_path: str = ""
    title: Optional[str] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    game_title: Optional[str] = None
    clip_type: str = "gameplay"

    class Config:
        from_attributes = True


class RenderedVideo(BaseModel):
    id: Optional[UUID] = None
    script_id: Optional[UUID] = None
    voiceover_id: Optional[UUID] = None
    footage_id: Optional[UUID] = None
    file_path: str = ""
    duration: Optional[float] = None
    width: int = 1080
    height: int = 1920
    status: str = "rendered"
    buffer_update_id: Optional[str] = None
    published_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class Feedback(BaseModel):
    id: Optional[UUID] = None
    script_id: Optional[UUID] = None
    video_id: Optional[UUID] = None
    feedback_type: str
    feedback_text: Optional[str] = None
    source: str = "mattermost"
    applied: bool = False

    class Config:
        from_attributes = True


class PipelineRun(BaseModel):
    id: Optional[UUID] = None
    content_type: str
    trigger_source: str = "schedule"
    status: str = "started"
    step: Optional[str] = None
    script_id: Optional[UUID] = None
    video_id: Optional[UUID] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class RAGEmbedding(BaseModel):
    id: Optional[UUID] = None
    source_type: str
    source_id: Optional[UUID] = None
    content_text: str
    content_summary: Optional[str] = None
    embedding: List[float] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
