"""Language Translation Plugin for Radio & TV Segmenter."""
from __future__ import annotations

try:
    from plugins.translation.plugin import Plugin
    __all__ = ["Plugin"]
except ImportError:
    Plugin = None
    __all__ = []
