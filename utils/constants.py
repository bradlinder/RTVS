"""Application constants and environment configuration."""
import os

try:
    from PySide6.QtCore import QSettings
except ImportError:
    QSettings = None

# Display branding shown to the user (title bar, About box, installers).
APP_DISPLAY_NAME = "Radio & TV Segmenter"
PROJECT_VERSION = "3.1.1-beta-2"
DEFAULT_GITHUB_REPO = "bradlinder/RTVS"

# Internal identifiers are intentionally left as "RadioTVStorySegmenter" (the
# original project name) rather than renamed to match APP_DISPLAY_NAME: this
# is the QSettings org/app name and the per-user app-data folder name, and
# changing it would orphan existing beta users' saved preferences and
# downloaded Whisper model cache on upgrade. Only user-facing text changes.
INTERNAL_APP_ID = "RadioTVStorySegmenter"

HELPER_PROTOCOL_VERSION = "1.0"
WAVEFORM_ANALYSIS_RATE = 8000
WAVEFORM_POINTS_PER_SECOND = 200
MIN_WORDS_PER_PARAGRAPH = 100
MAX_ACTIVITY_SNAPSHOTS = 50


def get_github_repo() -> str:
    """Return the configured GitHub repository owner/repo string."""
    env_repo = os.environ.get("GITHUB_REPO", "").strip()
    if env_repo:
        return env_repo
    try:
        settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        val = str(settings.value("github_repo", "") or "").strip()
        if val:
            return val
    except Exception:
        pass
    return DEFAULT_GITHUB_REPO
