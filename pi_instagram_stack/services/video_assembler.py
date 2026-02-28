# -*- coding: utf-8 -*-
"""
Video Assembler Service
=======================
Assembles vertical Instagram Reels (1080x1920) using FFmpeg:
  - Loads gameplay/trailer footage
  - Crops/resizes to 9:16 vertical
  - Trims to voiceover duration (30-60s)
  - Overlays voiceover audio
  - Burns word-by-word Arabic subtitles (ASS)
  - Exports final .mp4
"""

import json
import logging
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("instagram.assembler")


class VideoAssembler:
    """FFmpeg-based vertical video assembly pipeline."""

    def __init__(
        self,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        output_dir: str = "output",
        temp_dir: str = "output/temp",
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ================================================================
    # Main assembly pipeline
    # ================================================================

    def assemble(
        self,
        footage_path: str,
        voiceover_path: str,
        subtitle_ass_path: str,
        target_duration: Optional[float] = None,
        title: str = "instagram_reel",
    ) -> Dict[str, Any]:
        """
        Full assembly pipeline:
          1. Get voiceover duration → sets target
          2. Prepare footage (crop + resize to vertical)
          3. Trim footage to target duration
          4. Overlay voiceover audio
          5. Burn ASS subtitles
          6. Export final .mp4

        Returns:
            dict with output_path, duration, file_size, metadata
        """
        run_id = uuid.uuid4().hex[:8]
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info("[%s] Starting video assembly: %s", run_id, title)

        # Step 1: Get voiceover duration
        vo_duration = self._get_duration(voiceover_path)
        duration = target_duration or vo_duration
        duration = max(15.0, min(duration, 90.0))  # Clamp 15-90s
        logger.info(
            "[%s] Target duration: %.1fs (voiceover: %.1fs)",
            run_id,
            duration,
            vo_duration,
        )

        # Step 2: Prepare footage (crop to vertical)
        prepared_path = str(self.temp_dir / f"{run_id}_prepared.mp4")
        self._prepare_footage(footage_path, prepared_path)

        # Step 3: Trim to target duration
        trimmed_path = str(self.temp_dir / f"{run_id}_trimmed.mp4")
        self._trim_video(prepared_path, trimmed_path, duration)

        # Step 4: Overlay voiceover + burn subtitles in single pass
        output_filename = f"{safe_title}_{timestamp}.mp4"
        output_path = str(self.output_dir / output_filename)
        self._final_render(
            video_path=trimmed_path,
            voiceover_path=voiceover_path,
            subtitle_ass_path=subtitle_ass_path,
            output_path=output_path,
            duration=duration,
        )

        # Get final info
        final_info = self._get_media_info(output_path)
        file_size = Path(output_path).stat().st_size

        # Clean up temp files
        self._cleanup_temp(run_id)

        result = {
            "output_path": output_path,
            "duration": final_info.get("duration", duration),
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "resolution": f"{self.width}x{self.height}",
            "fps": self.fps,
            "run_id": run_id,
        }

        logger.info(
            "[%s] Assembly complete: %s (%.1fs, %.1fMB)",
            run_id,
            output_filename,
            result["duration"],
            result["file_size_mb"],
        )
        return result

    # ================================================================
    # Pipeline steps
    # ================================================================

    def _prepare_footage(self, input_path: str, output_path: str) -> None:
        """
        Crop and resize footage to 9:16 vertical format.
        Strategy: center-crop the widest dimension to 9:16 ratio,
        then scale to target resolution.
        """
        info = self._get_media_info(input_path)
        src_w = info.get("width", 1920)
        src_h = info.get("height", 1080)

        # Target aspect ratio = 9/16 = 0.5625
        target_ratio = self.width / self.height  # 0.5625

        src_ratio = src_w / src_h
        if src_ratio > target_ratio:
            # Source is wider than target → crop width
            crop_w = int(src_h * target_ratio)
            crop_h = src_h
        else:
            # Source is taller/equal → crop height
            crop_w = src_w
            crop_h = int(src_w / target_ratio)

        # Ensure even dimensions
        crop_w = crop_w - (crop_w % 2)
        crop_h = crop_h - (crop_h % 2)

        vf = (
            f"crop={crop_w}:{crop_h}:(iw-{crop_w})/2:(ih-{crop_h})/2,"
            f"scale={self.width}:{self.height}:flags=lanczos,"
            f"fps={self.fps},"
            f"setsar=1"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-an",  # Strip audio (we'll use voiceover)
            "-movflags",
            "+faststart",
            output_path,
        ]

        logger.info(
            "Preparing footage: %dx%d → %dx%d", src_w, src_h, self.width, self.height
        )
        self._run_ffmpeg(cmd, "prepare footage")

    def _trim_video(self, input_path: str, output_path: str, duration: float) -> None:
        """Trim video to target duration with fade out."""
        fade_duration = min(1.0, duration * 0.05)
        fade_start = duration - fade_duration

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-t",
            str(duration),
            "-vf",
            f"fade=t=out:st={fade_start:.2f}:d={fade_duration:.2f}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-an",
            output_path,
        ]

        logger.info("Trimming to %.1fs with %.1fs fade", duration, fade_duration)
        self._run_ffmpeg(cmd, "trim video")

    def _final_render(
        self,
        video_path: str,
        voiceover_path: str,
        subtitle_ass_path: str,
        output_path: str,
        duration: float,
    ) -> None:
        """
        Final render: overlay voiceover audio + burn ASS subtitles.
        Single FFmpeg pass for efficiency.
        """
        # Check if ASS file exists
        ass_exists = Path(subtitle_ass_path).is_file()

        # Build filter complex
        if ass_exists:
            # Escape path for ASS filter (FFmpeg requires forward slashes)
            ass_path_escaped = subtitle_ass_path.replace("\\", "/").replace(":", "\\:")
            vf = f"ass='{ass_path_escaped}'"
        else:
            vf = "null"
            logger.warning("ASS subtitle file not found: %s", subtitle_ass_path)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-i",
            voiceover_path,
            "-filter_complex",
            (f"[0:v]{vf}[v];" f"[1:a]apad=whole_dur={duration:.2f}[a]"),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",  # Higher quality for final output
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-t",
            str(duration),
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]

        logger.info(
            "Final render with subtitles + voiceover → %s", Path(output_path).name
        )
        self._run_ffmpeg(cmd, "final render")

    # ================================================================
    # Utility methods
    # ================================================================

    def _run_ffmpeg(
        self, cmd: List[str], step_name: str
    ) -> subprocess.CompletedProcess:
        """Run an FFmpeg command with error handling."""
        logger.debug("FFmpeg [%s]: %s", step_name, " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min timeout
            )
            if result.returncode != 0:
                logger.error(
                    "FFmpeg [%s] failed (code %d):\n%s",
                    step_name,
                    result.returncode,
                    result.stderr[-2000:],
                )
                raise RuntimeError(f"FFmpeg {step_name} failed: {result.stderr[-500:]}")
            return result

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg [%s] timed out after 600s", step_name)
            raise RuntimeError(f"FFmpeg {step_name} timed out")

    def _get_duration(self, file_path: str) -> float:
        """Get media file duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            file_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception as e:
            logger.warning("Could not get duration for %s: %s", file_path, e)
            return 45.0  # Default fallback

    def _get_media_info(self, file_path: str) -> Dict[str, Any]:
        """Get media info (duration, width, height) via ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)

            info: Dict[str, Any] = {}
            if "format" in data:
                info["duration"] = float(data["format"].get("duration", 0))

            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    info["width"] = stream.get("width", 0)
                    info["height"] = stream.get("height", 0)
                    info["codec"] = stream.get("codec_name", "unknown")
                    break

            return info
        except Exception as e:
            logger.warning("Could not get media info for %s: %s", file_path, e)
            return {}

    def _cleanup_temp(self, run_id: str) -> None:
        """Remove temp files for a specific run."""
        for f in self.temp_dir.glob(f"{run_id}_*"):
            try:
                f.unlink()
                logger.debug("Cleaned up: %s", f.name)
            except OSError:
                pass

    # ================================================================
    # Quick assembly (no subtitles, for previews)
    # ================================================================

    def quick_preview(
        self,
        footage_path: str,
        voiceover_path: str,
        title: str = "preview",
    ) -> str:
        """
        Quick preview assembly without subtitles.
        Useful for Slack preview before full render.
        """
        run_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(self.output_dir / f"preview_{title}_{timestamp}.mp4")

        vo_duration = self._get_duration(voiceover_path)

        # Single-pass: crop + resize + trim + audio overlay
        target_ratio = self.width / self.height
        vf = (
            f"crop=ih*{target_ratio:.4f}:ih:(iw-ih*{target_ratio:.4f})/2:0,"
            f"scale={self.width}:{self.height}:flags=fast_bilinear,"
            f"fps={self.fps}"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            footage_path,
            "-i",
            voiceover_path,
            "-vf",
            vf,
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",  # Lower quality for speed
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-t",
            str(vo_duration),
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]

        self._run_ffmpeg(cmd, "quick preview")
        logger.info("Preview: %s", output_path)
        return output_path
