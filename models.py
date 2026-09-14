"""Radio & TV Story Segmenter — Public Data Models and Interface Definitions.

Provides lightweight, strongly typed dataclasses and TypedDicts for domain entities,
allowing modules and plugins to interact with contracts without importing large UI
or processing files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict


@dataclass
class SegmentWord:
    """Represents a single word token within an ASR segment with timing and formatting."""
    word: str
    start: float = 0.0
    end: float = 0.0
    seg_idx: int = 0
    speaker_name: str = ""
    raw_speaker: str = ""
    deleted: bool = False
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    highlight: bool = False
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "word": self.word,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
        }
        if self.deleted:
            d["deleted"] = True
        if self.bold:
            d["bold"] = True
        if self.italic:
            d["italic"] = True
        if self.underline:
            d["underline"] = True
        if self.strike:
            d["strike"] = True
        if self.highlight:
            d["highlight"] = True
        if self.confidence < 0.999:
            d["confidence"] = round(self.confidence, 3)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any], seg_idx: int = 0, speaker: str = "") -> SegmentWord:
        return cls(
            word=str(data.get("word", "")),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            seg_idx=seg_idx,
            speaker_name=speaker,
            raw_speaker=speaker,
            deleted=bool(data.get("deleted", False)),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            underline=bool(data.get("underline", False)),
            strike=bool(data.get("strike", False)),
            highlight=bool(data.get("highlight", False)),
            confidence=float(data.get("confidence", 1.0)),
        )


@dataclass
class Story:
    """Represents a segmented story with time boundaries and metadata."""
    start: float = 0.0
    end: float = 0.0
    title: str = "Untitled Story"
    suggestion: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "start": self.start,
            "end": self.end,
            "title": self.title,
            "suggestion": self.suggestion,
        }
        if self.metadata:
            d["metadata"] = dict(self.metadata)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Story:
        known = {"start", "end", "title", "suggestion", "metadata"}
        meta = dict(data.get("metadata", {})) if isinstance(data.get("metadata"), dict) else {}
        for k, v in data.items():
            if k not in known:
                meta[k] = v
        return cls(
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            title=str(data.get("title", "Untitled Story")),
            suggestion=bool(data.get("suggestion", False)),
            metadata=meta,
        )


@dataclass
class StoryComment:
    """Represents a segment-anchored or timestamp-anchored user comment."""
    id: str
    text: str
    start_time: float = 0.0
    end_time: float = 0.0
    quote: str = ""
    author: str = ""
    created_at: str = ""
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "quote": self.quote,
            "author": self.author,
            "created_at": self.created_at,
            "resolved": self.resolved,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StoryComment:
        return cls(
            id=str(data.get("id", "")),
            text=str(data.get("text", "")),
            start_time=float(data.get("start_time", 0.0)),
            end_time=float(data.get("end_time", 0.0)),
            quote=str(data.get("quote", "")),
            author=str(data.get("author", "")),
            created_at=str(data.get("created_at", "")),
            resolved=bool(data.get("resolved", False)),
        )


class ExportFormatFlags(TypedDict, total=False):
    """Boolean flags indicating which export formats are active."""
    txt: bool
    docx: bool
    pdf: bool
    srt: bool
    vtt: bool
    json: bool
    csv: bool
    audio: bool
    video: bool


@dataclass
class ExportOptions:
    """Unified configuration parameters for story and episode exports."""
    include_speakers: bool = True
    include_timestamps: bool = True
    include_comments: bool = True
    export_audio: bool = False
    export_video: bool = False
    formats: ExportFormatFlags = field(default_factory=dict)
    destination: str = "local"  # "local", "wordpress", "youtube", or custom plugin id
    output_dir: Optional[str] = None
    custom_options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExportDestinationDescriptor:
    """Metadata descriptor for an export destination provided by a plugin or core."""
    id: str
    title: str
    description: str = ""
    icon: Optional[str] = None
    supports_batch: bool = True
    requires_media: bool = False
