"""Time formatting and parsing utilities."""
import re


def format_time(seconds, include_millis=True):
    seconds = max(0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)

    if include_millis:
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
        return f"{minutes:02d}:{secs:02d}.{millis:03d}"
    else:
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"


def parse_time(value):
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass

    parts = value.split(":")
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return (
            float(parts[0]) * 3600
            + float(parts[1]) * 60
            + float(parts[2])
        )
    raise ValueError(f"Invalid time: {value}")


def safe_filename(text):
    text = text.strip()
    if not text:
        text = "Untitled Story"
    text = re.sub(r'[<>:"/\\|?*]', "", text)
    text = re.sub(r"\s+", "_", text)
    text = text[:100]
    # A result that's nothing but dots (".", "..", "....") is a
    # current-dir/parent-dir path component when used as a single path
    # segment, not a real filename -- e.g. a project folder-name prompt or
    # a story title of ".." would otherwise resolve one level *above* the
    # intended export directory. This can come from direct user input or
    # from a loaded project file's own data, so guard it once here rather
    # than at each of this function's call sites.
    if not text.strip("."):
        text = "Untitled_Story"
    return text


def is_sentence_end(text):
    return bool(re.search(r"[.!?]+[\"'”’)\]]*$", text.strip()))
