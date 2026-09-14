#!/usr/bin/env python3
"""
Snapshot Manager for Radio & TV Story Segmenter
------------------------------------------------
Provides automated snapshotting and zero-friction restoration for stable and beta
releases, with dual redundancy across local git tags and standalone filesystem archives.

Usage:
  python snapshot_manager.py --create <name> [--stable]
  python snapshot_manager.py --restore <name>
  python snapshot_manager.py --list
  python snapshot_manager.py --status
"""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import json
import re
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SNAPSHOTS_DIR = ROOT_DIR / ".snapshots"
SNAPSHOT_MANIFEST = SNAPSHOTS_DIR / "manifest.json"

EXCLUDE_DIRS = {
    ".git",
    ".snapshots",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "dist",
    "build",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".tar.gz",
    ".zip",
}


def load_manifest() -> dict:
    if SNAPSHOT_MANIFEST.exists():
        try:
            with open(SNAPSHOT_MANIFEST, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"snapshots": {}, "latest_stable": None}
    return {"snapshots": {}, "latest_stable": None}


def save_manifest(data: dict):
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_current_project_version() -> str:
    prs_file = ROOT_DIR / "prs_shared.py"
    if prs_file.exists():
        try:
            content = prs_file.read_text(encoding="utf-8")
            match = re.search(r'PROJECT_VERSION\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
    try:
        from prs_shared import PROJECT_VERSION
        return str(PROJECT_VERSION).strip()
    except Exception:
        return "unknown"


def ensure_git_repo():
    """Ensure git repo is initialized with standard identity."""
    git_dir = ROOT_DIR / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=ROOT_DIR, check=False)
        subprocess.run(["git", "config", "user.name", "Radio & TV Story Segmenter"], cwd=ROOT_DIR, check=False)
        subprocess.run(["git", "config", "user.email", "support@radiotvsegmenter.local"], cwd=ROOT_DIR, check=False)


def create_snapshot(name: str, is_stable: bool = False):
    ensure_git_repo()
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    version = get_current_project_version()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    archive_name = f"{name}.tar.gz"
    archive_path = SNAPSHOTS_DIR / archive_name

    print(f"[*] Creating snapshot '{name}' (App Version: v{version}, Stable={is_stable})...")

    # 1. Archive core project files
    def tar_filter(tarinfo):
        path_parts = Path(tarinfo.name).parts
        for part in path_parts:
            if part in EXCLUDE_DIRS:
                return None
        if any(tarinfo.name.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
            return None
        return tarinfo

    with tarfile.open(archive_path, "w:gz") as tar:
        for item in ROOT_DIR.iterdir():
            if item.name in EXCLUDE_DIRS:
                continue
            tar.add(item, arcname=item.name, filter=tar_filter)

    # 2. Git commit and tag for granular inspection
    try:
        subprocess.run(["git", "add", "-A"], cwd=ROOT_DIR, check=False)
        commit_msg = f"Release Snapshot: {name} (v{version})"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=ROOT_DIR, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Create or update git tag
        subprocess.run(["git", "tag", "-f", name], cwd=ROOT_DIR, check=False)
        if is_stable:
            subprocess.run(["git", "tag", "-f", "latest-stable"], cwd=ROOT_DIR, check=False)
            subprocess.run(["git", "branch", "-f", "stable"], cwd=ROOT_DIR, check=False)
    except Exception as e:
        print(f"[!] Warning: Git tag could not be updated: {e}")

    # 3. Update manifest
    manifest = load_manifest()
    manifest["snapshots"][name] = {
        "version": version,
        "timestamp": timestamp,
        "is_stable": is_stable,
        "archive": archive_name,
    }
    if is_stable:
        manifest["latest_stable"] = name
    save_manifest(manifest)

    print(f"[✓] Snapshot '{name}' successfully saved to {archive_path}")
    if is_stable:
        print(f"[✓] Marked '{name}' as the latest stable release.")


def list_snapshots():
    manifest = load_manifest()
    snapshots = manifest.get("snapshots", {})
    latest_stable = manifest.get("latest_stable")

    print("\n" + "=" * 60)
    print("Radio & TV Story Segmenter - Available Snapshots")
    print("=" * 60)

    if not snapshots:
        print("  No snapshots found.")
        return

    for name, info in sorted(snapshots.items()):
        marker = " [LATEST STABLE]" if name == latest_stable else ""
        if info.get("is_stable") and not marker:
            marker = " [STABLE]"
        print(f"  • {name:<22} v{info.get('version', '?'):<8} {info.get('timestamp', '')}{marker}")
    print("=" * 60 + "\n")


def restore_snapshot(name: str):
    manifest = load_manifest()
    snapshots = manifest.get("snapshots", {})

    if name in ("stable", "latest-stable", "latest"):
        name = manifest.get("latest_stable")
        if not name:
            print("[!] Error: No snapshot marked as latest stable found.")
            sys.exit(1)

    if name not in snapshots:
        print(f"[!] Error: Snapshot '{name}' not found in manifest.")
        list_snapshots()
        sys.exit(1)

    info = snapshots[name]
    archive_path = SNAPSHOTS_DIR / info.get("archive", f"{name}.tar.gz")
    if not archive_path.exists():
        print(f"[!] Error: Archive file {archive_path} does not exist.")
        sys.exit(1)

    print(f"[*] Restoring snapshot '{name}' (v{info.get('version')}, saved {info.get('timestamp')})...")

    # 1. Unpack archive directly over project files
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            normalized = Path(os.path.abspath(os.path.join(ROOT_DIR, member.name)))
            try:
                normalized.relative_to(ROOT_DIR)
            except ValueError:
                raise PermissionError(f"Attempted path traversal in backup member: {member.name}")
        tar.extractall(path=ROOT_DIR)

    # 2. Synchronize web preview
    preview_mgr = ROOT_DIR / "preview_manager.py"
    if preview_mgr.exists():
        try:
            subprocess.run([sys.executable, str(preview_mgr), "--restore"], cwd=ROOT_DIR, check=False)
            subprocess.run([sys.executable, str(preview_mgr), "--sync"], cwd=ROOT_DIR, check=False)
        except Exception as e:
            print(f"[!] Warning: Preview synchronization encountered an issue: {e}")

    # 3. Checkout git tag if available
    ensure_git_repo()
    try:
        subprocess.run(["git", "checkout", "-f", name], cwd=ROOT_DIR, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    print(f"[✓] Successfully restored project to snapshot '{name}' (v{info.get('version')})!")


def main():
    parser = argparse.ArgumentParser(description="Snapshot Manager for Radio & TV Story Segmenter")
    parser.add_argument("--create", type=str, help="Create a named snapshot")
    parser.add_argument("--stable", action="store_true", help="Mark snapshot as stable release")
    parser.add_argument("--restore", type=str, help="Restore named snapshot (or 'stable')")
    parser.add_argument("--list", action="store_true", help="List all available snapshots")
    parser.add_argument("--status", action="store_true", help="Show current project version and latest stable snapshot")

    args = parser.parse_args()

    if args.create:
        create_snapshot(args.create, is_stable=args.stable)
    elif args.restore:
        restore_snapshot(args.restore)
    elif args.list:
        list_snapshots()
    elif args.status:
        manifest = load_manifest()
        print(f"Current App Version: v{get_current_project_version()}")
        print(f"Latest Stable Snapshot: {manifest.get('latest_stable', 'None')}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
