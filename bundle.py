import os
from pathlib import Path

# Base output bundle file name prefix
BUNDLE_BASE_NAME = "project_bundle"
# Maximum size in bytes per part before rolling over to the next part (250 KB)
MAX_PART_SIZE = 250 * 1024

# Directories to skip
IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "release",
}

# Explicit file names to skip
IGNORE_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".DS_Store",
}

# Binary/asset extensions to exclude from source analysis
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".zip", ".tar", ".gz", ".7z",
    ".pyc", ".pyo", ".pyd",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".wav", ".ogg", ".mp4", ".mov"
}

def is_text_file(filepath: Path) -> bool:
    if filepath.suffix.lower() in BINARY_EXTENSIONS:
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            f.read(1024)
        return True
    except (UnicodeDecodeError, PermissionError):
        return False

class MultipartBundler:
    def __init__(self, root_dir: Path, max_bytes: int = MAX_PART_SIZE):
        self.root_dir = root_dir
        self.max_bytes = max_bytes
        self.part_number = 1
        self.current_handle = None
        self.current_bytes = 0
        self.created_files = []

    def _open_next_part(self):
        if self.current_handle:
            self.current_handle.close()

        filename = f"{BUNDLE_BASE_NAME}_part{self.part_number}.txt"
        out_path = self.root_dir / filename
        self.created_files.append(out_path)
        self.current_handle = open(out_path, "w", encoding="utf-8")
        header = f"# PROJECT REPOSITORY BUNDLE — PART {self.part_number}\n\n"
        self.current_handle.write(header)
        self.current_bytes = len(header.encode("utf-8"))
        print(f"\n--> Starting {filename}...")
        self.part_number += 1

    def append_file(self, rel_path: Path, content: str):
        ext = rel_path.suffix.lstrip(".") or "text"
        block = f"## File: {rel_path.as_posix()}\n```{ext}\n{content}\n```\n\n"
        block_bytes = len(block.encode("utf-8"))

        if self.current_handle is None or (self.current_bytes + block_bytes > self.max_bytes and self.current_bytes > 500):
            self._open_next_part()

        self.current_handle.write(block)
        self.current_bytes += block_bytes
        print(f"Bundled: {rel_path.as_posix()}")

    def close(self):
        if self.current_handle:
            self.current_handle.close()
            self.current_handle = None

def bundle_directory(root_dir: Path):
    # Remove older bundle part files
    for old_bundle in root_dir.glob(f"{BUNDLE_BASE_NAME}*.txt"):
        try:
            old_bundle.unlink()
        except Exception:
            pass

    bundler = MultipartBundler(root_dir)

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

        for file in sorted(filenames):
            if file in IGNORE_FILES or file.startswith(BUNDLE_BASE_NAME):
                continue

            full_path = Path(dirpath) / file
            rel_path = full_path.relative_to(root_dir)

            if is_text_file(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    bundler.append_file(rel_path, content)
                except Exception as e:
                    print(f"Skipped {rel_path.as_posix()}: {e}")

    bundler.close()
    print(f"\nFinished! Created {len(bundler.created_files)} parts:")
    for path in bundler.created_files:
        print(f" - {path.name} ({path.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    current_dir = Path.cwd()
    print(f"Bundling project from {current_dir} into segmented parts...")
    bundle_directory(current_dir)