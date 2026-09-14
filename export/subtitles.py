"""Subtitle and timeline formatters for Radio & TV Story Segmenter.

Provides formatting and file generation for:
- SubRip (.srt)
- WebVTT (.vtt)
- Red Book CUE sheets (.cue)
- YouTube Chapter markers
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def format_subtitle_timestamp(seconds: float, vtt: bool = False) -> str:
    """Format seconds into SRT (HH:MM:SS,mmm) or VTT (HH:MM:SS.mmm) timestamp."""
    secs = max(0.0, float(seconds or 0.0))
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = secs % 60
    ms = int(round((s - int(s)) * 1000))
    sec = int(s)
    if ms >= 1000:
        sec += 1
        ms = 0
    delimiter = "." if vtt else ","
    return f"{h:02d}:{m:02d}:{sec:02d}{delimiter}{ms:03d}"


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into SRT (HH:MM:SS,mmm) timestamp."""
    return format_subtitle_timestamp(seconds, vtt=False)


def format_vtt_timestamp(seconds: float) -> str:
    """Format seconds into WebVTT (HH:MM:SS.mmm) timestamp."""
    return format_subtitle_timestamp(seconds, vtt=True)


def format_cue_timestamp(seconds: float) -> str:
    """Format seconds into standard CUE sheet MM:SS:FF (75 frames per second)."""
    return seconds_to_cue_time(seconds)


def format_youtube_timestamp(seconds: float) -> str:
    """Format seconds into YouTube chapter timestamp (e.g. 03:45 or 01:23:45)."""
    t = max(0.0, float(seconds or 0.0))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def seconds_to_cue_time(seconds: float) -> str:
    """Format seconds into standard CUE sheet MM:SS:FF (75 frames per second)."""
    total_secs = max(0.0, float(seconds or 0.0))
    minutes = int(total_secs // 60)
    secs = int(total_secs % 60)
    frames = int(round((total_secs - int(total_secs)) * 75))
    if frames >= 75:
        frames = 0
        secs += 1
        if secs >= 60:
            secs = 0
            minutes += 1
    return f"{minutes:02d}:{secs:02d}:{frames:02d}"


def generate_cue_sheet(stories: list, media_filename: str = "", album_title: str = "Album") -> str:
    """Generate a standard red-book compatible .cue sheet from story segments."""
    lines = []
    clean_title = album_title.replace('"', "'")
    lines.append(f'TITLE "{clean_title}"')
    if media_filename:
        ext = Path(media_filename).suffix.lower()
        file_type = "MP3" if ext == ".mp3" else ("AIFF" if ext in (".aif", ".aiff") else "WAVE")
        lines.append(f'FILE "{Path(media_filename).name}" {file_type}')
    else:
        lines.append('FILE "audio.wav" WAVE')

    sorted_stories = sorted(stories, key=lambda s: getattr(s, "start", 0.0))
    for i, story in enumerate(sorted_stories, 1):
        title = (getattr(story, "title", "") or f"Track {i}").strip().replace('"', "'")
        cue_time = seconds_to_cue_time(getattr(story, "start", 0.0))
        lines.append(f'  TRACK {i:02d} AUDIO')
        lines.append(f'    TITLE "{title}"')
        lines.append(f'    INDEX 01 {cue_time}')
    return "\n".join(lines) + "\n"


def generate_cue_content(stories: list, media_filename: str = "", album_title: str = "Album") -> str:
    """Generate CUE sheet content from story segments (alias for generate_cue_sheet)."""
    return generate_cue_sheet(stories, media_filename=media_filename, album_title=album_title)


def generate_youtube_chapters(stories: list, ensure_zero_start: bool = True) -> str:
    """Generate YouTube chapter markers / tracklist (e.g. 00:00 - Intro, 03:45 - Track 1)."""
    lines = []
    if not stories:
        return ""
    sorted_stories = sorted(stories, key=lambda s: getattr(s, "start", 0.0))
    first_start = getattr(sorted_stories[0], "start", 0.0)
    if ensure_zero_start and first_start > 0.5:
        lines.append("00:00 - Intro")
    for story in sorted_stories:
        t = max(0.0, float(getattr(story, "start", 0.0)))
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        if h > 0:
            ts_str = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            ts_str = f"{m:02d}:{s:02d}"
        title = (getattr(story, "title", "") or "Untitled Segment").strip()
        lines.append(f"{ts_str} - {title}")
    return "\n".join(lines) + "\n"


def format_subtitles(
    blocks: List[Dict[str, Any]],
    fmt: str = "srt",
    include_speakers: bool = True,
    clean_text_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Format a list of story/transcript blocks into an SRT or WebVTT formatted string."""
    lines: List[str] = []
    is_vtt = (fmt.lower() == "vtt")
    if is_vtt:
        lines.append("WEBVTT\n")

    counter = 1
    for block in blocks:
        start = block.get("start", 0.0)
        end = block.get("end", start + 1.0)
        raw_text = block.get("text", "")
        spk = block.get("speaker", "")

        if clean_text_fn:
            text = clean_text_fn(raw_text, spk)
        else:
            text = raw_text.strip()

        if include_speakers and spk:
            text = f"{spk}: {text}"

        if not text:
            continue

        start_ts = format_subtitle_timestamp(start, vtt=is_vtt)
        end_ts = format_subtitle_timestamp(end, vtt=is_vtt)

        if not is_vtt:
            lines.extend([str(counter), f"{start_ts} --> {end_ts}", text, ""])
        else:
            lines.extend([f"{start_ts} --> {end_ts}", text, ""])
        counter += 1

    return "\n".join(lines)


def write_subtitles_file(
    blocks: List[Dict[str, Any]],
    path: Path | str,
    fmt: str = "srt",
    include_speakers: bool = True,
    clean_text_fn: Optional[Callable[[str, str], str]] = None,
) -> None:
    """Writes formatted subtitles (SRT or VTT) to a destination path."""
    content = format_subtitles(blocks, fmt=fmt, include_speakers=include_speakers, clean_text_fn=clean_text_fn)
    Path(path).write_text(content, encoding="utf-8")


def generate_srt_content(
    blocks: List[Dict[str, Any]],
    include_speakers: bool = True,
    clean_text_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Generate SubRip (.srt) subtitle content from blocks."""
    return format_subtitles(blocks, fmt="srt", include_speakers=include_speakers, clean_text_fn=clean_text_fn)


def generate_vtt_content(
    blocks: List[Dict[str, Any]],
    include_speakers: bool = True,
    clean_text_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Generate WebVTT (.vtt) subtitle content from blocks."""
    return format_subtitles(blocks, fmt="vtt", include_speakers=include_speakers, clean_text_fn=clean_text_fn)

