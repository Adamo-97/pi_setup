# -*- coding: utf-8 -*-
"""
Subtitle Service
================
Instagram Reels word-by-word highlighted Arabic captions.
Generates ASS subtitle files with karaoke-style highlighting
and FFmpeg drawtext filters for overlay rendering.
"""

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("instagram.subtitles")


@dataclass
class SubtitleWord:
    """A single word with timing info."""

    word: str
    start: float
    end: float
    index: int


@dataclass
class SubtitleGroup:
    """A group of words displayed together (one subtitle frame)."""

    words: List[SubtitleWord]
    start: float
    end: float

    @property
    def text(self) -> str:
        return " ".join(w.word for w in self.words)


class SubtitleService:
    """Generates Instagram Reels word-by-word highlighted Arabic subtitles."""

    def __init__(
        self,
        font_size: int = 64,
        highlight_color: str = "#FFD700",
        normal_color: str = "#FFFFFF",
        bg_color: str = "#00000099",
        words_per_group: int = 4,
        padding: int = 20,
    ):
        self.font_size = font_size
        self.highlight_color = highlight_color
        self.normal_color = normal_color
        self.bg_color = bg_color
        self.words_per_group = words_per_group
        self.padding = padding

    # ================================================================
    # Group words into subtitle chunks
    # ================================================================

    def group_words(
        self,
        word_timestamps: List[Dict[str, Any]],
    ) -> List[SubtitleGroup]:
        """
        Group word timestamps into display groups of N words each.

        Args:
            word_timestamps: [{word, start, end}, ...]

        Returns:
            List of SubtitleGroup objects
        """
        words = [
            SubtitleWord(
                word=wt["word"],
                start=wt["start"],
                end=wt["end"],
                index=i,
            )
            for i, wt in enumerate(word_timestamps)
        ]

        groups = []
        for i in range(0, len(words), self.words_per_group):
            chunk = words[i : i + self.words_per_group]
            groups.append(
                SubtitleGroup(
                    words=chunk,
                    start=chunk[0].start,
                    end=chunk[-1].end,
                )
            )

        logger.info(
            "Created %d subtitle groups from %d words",
            len(groups),
            len(words),
        )
        return groups

    # ================================================================
    # Generate FFmpeg subtitle filter
    # ================================================================

    def generate_ffmpeg_drawtext_filter(
        self,
        word_timestamps: List[Dict[str, Any]],
        video_width: int = 1080,
        video_height: int = 1920,
        font_path: Optional[str] = None,
    ) -> str:
        """
        Generate a complex FFmpeg drawtext filter string for word-by-word
        highlighting.

        Each word group is shown as a block. The currently-spoken word
        is rendered in highlight_color, others in normal_color.

        Returns:
            FFmpeg filter_complex string segment for drawtext.
        """
        groups = self.group_words(word_timestamps)
        if not groups:
            return ""

        y_pos = int(video_height * 0.70)  # 70% down the screen
        font = font_path or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        filters = []

        for group in groups:
            enable = f"between(t,{group.start:.3f},{group.end:.3f})"

            for word in group.words:
                # Highlighted word: gold color while being spoken
                word_enable = f"between(t,{word.start:.3f},{word.end:.3f})"
                not_word_enable = (
                    f"between(t,{group.start:.3f},{word.start:.3f})"
                    f"+between(t,{word.end:.3f},{group.end:.3f})"
                )

                # Calculate x position (center-aligned, RTL-aware)
                group_text = group.text
                word_offset = self._calc_word_offset(
                    group.words, word.index - group.words[0].index
                )

                # Highlight filter for current spoken word
                filters.append(
                    f"drawtext=text='{self._escape_ffmpeg(word.word)}':"
                    f"fontfile='{font}':"
                    f"fontsize={self.font_size}:"
                    f"fontcolor={self.highlight_color}:"
                    f"x=(w-text_w)/2+{word_offset}:"
                    f"y={y_pos}:"
                    f"enable='{word_enable}':"
                    f"shadowcolor=black:shadowx=2:shadowy=2"
                )

            # Background box for the whole group
            filters.insert(
                len(filters) - len(group.words),
                f"drawtext=text='{self._escape_ffmpeg(group.text)}':"
                f"fontfile='{font}':"
                f"fontsize={self.font_size}:"
                f"fontcolor={self.normal_color}:"
                f"x=(w-text_w)/2:"
                f"y={y_pos}:"
                f"enable='{enable}':"
                f"box=1:boxcolor={self.bg_color}:"
                f"boxborderw={self.padding}:"
                f"shadowcolor=black:shadowx=2:shadowy=2",
            )

        return ",".join(filters)

    # ================================================================
    # Generate ASS subtitle file (alternative approach)
    # ================================================================

    def generate_ass_file(
        self,
        word_timestamps: List[Dict[str, Any]],
        output_path: str,
        video_width: int = 1080,
        video_height: int = 1920,
    ) -> str:
        """
        Generate an ASS subtitle file with word-by-word karaoke-style
        highlighting. More reliable than drawtext for complex Arabic text.

        Returns:
            Path to the generated .ass file
        """
        groups = self.group_words(word_timestamps)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        header = f"""[Script Info]
Title: Instagram Reels Subtitles
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{self.font_size},&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,3,3,2,2,30,30,{int(video_height * 0.25)},0
Style: Highlight,Arial,{self.font_size},&H0000D7FF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,3,3,2,5,30,30,{int(video_height * 0.25)},0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        events = []
        for group in groups:
            start_ts = self._seconds_to_ass_time(group.start)
            end_ts = self._seconds_to_ass_time(group.end)

            # Build karaoke text with highlighting
            karaoke_text = ""
            for word in group.words:
                dur_cs = int((word.end - word.start) * 100)  # centiseconds
                karaoke_text += f"{{\\kf{dur_cs}}}{word.word} "

            events.append(
                f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{karaoke_text.strip()}"
            )

        ass_content = header + "\n".join(events) + "\n"
        output.write_text(ass_content, encoding="utf-8")

        logger.info("Generated ASS subtitle: %s (%d events)", output.name, len(events))
        return str(output)

    # ================================================================
    # Utilities
    # ================================================================

    @staticmethod
    def _escape_ffmpeg(text: str) -> str:
        """Escape special characters for FFmpeg drawtext."""
        return (
            text.replace("\\", "\\\\")
            .replace("'", "'\\''")
            .replace(":", "\\:")
            .replace("%", "%%")
        )

    @staticmethod
    def _calc_word_offset(words: List[SubtitleWord], word_index: int) -> int:
        """Rough pixel offset for a word within its group (estimation)."""
        avg_char_width = 20
        offset = 0
        for i in range(word_index):
            offset += len(words[i].word) * avg_char_width + avg_char_width
        return offset

    @staticmethod
    def _seconds_to_ass_time(seconds: float) -> str:
        """Convert seconds to ASS timestamp H:MM:SS.CC"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
