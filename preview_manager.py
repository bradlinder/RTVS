#!/usr/bin/env python3
"""AI Studio Web Preview Manager for Radio & TV Story Segmenter.

This script manages, verifies, and restores the AI Studio web preview scaffolding
(interactive changelog and release history viewer).

Because the web preview files are ignored by git (to keep the GitHub repository
focused strictly on the native Python/PySide6 desktop application), this script
allows instant zero-token restoration and version synchronization whenever needed
(e.g., after fresh git clones, repository updates, or branch switches).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

PACKAGE_JSON_TEMPLATE = """{
  "name": "radio-tv-segmenter",
  "private": true,
  "version": "__VERSION__",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 3000",
    "build": "tsc && vite build",
    "lint": "eslint .",
    "preview": "vite preview"
  },
  "dependencies": {
    "lucide-react": "^1.16.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@eslint/js": "^10.0.1",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "eslint": "^10.10.0",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.3",
    "typescript": "^5.4.5",
    "typescript-eslint": "^8.70.0",
    "vite": "^5.2.11"
  }
}
"""

TSCONFIG_JSON_TEMPLATE = """{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
"""

VITE_CONFIG_TEMPLATE = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
  },
});
"""

TAILWIND_CONFIG_TEMPLATE = """/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
"""

POSTCSS_CONFIG_TEMPLATE = """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
"""

ESLINT_CONFIG_TEMPLATE = """import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'node_modules', '.vite'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-unused-vars': 'warn',
    },
  },
);
"""

METADATA_JSON_TEMPLATE = """{
  "name": "Radio & TV Segmenter",
  "description": "Radio & TV Segmenter v__VERSION__ - AI-powered audio/video transcription, diarization, translation, and story segmentation suite.",
  "requestFramePermissions": [],
  "majorCapabilities": ["MAJOR_CAPABILITY_SERVER_SIDE_GEMINI_API"]
}
"""

INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/noun_electronicmedia_5929933.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Radio & TV Segmenter v__VERSION__</title>
    <meta name="description" content="Radio & TV Segmenter v__VERSION__ - AI-powered audio/video transcription, diarization, translation, and story segmentation suite." />
    <meta property="og:title" content="Radio & TV Segmenter v__VERSION__" />
    <meta property="og:description" content="Radio & TV Segmenter v__VERSION__ - AI-powered audio/video transcription, diarization, translation, and story segmentation suite." />

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  </head>
  <body class="bg-slate-950 text-slate-100 antialiased font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""

SRC_MAIN_TSX = """import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
"""

SRC_INDEX_CSS = """@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-slate-950 text-slate-100;
  }
}
"""

SRC_VITE_ENV_D_TS = """/// <reference types="vite/client" />

declare module '*.md?raw' {
  const content: string;
  export default content;
}
"""

SRC_APP_TSX = """import React, { useState, useMemo } from 'react';
import { 
  Radio, 
  Search, 
  Filter, 
  ChevronDown, 
  ChevronRight, 
  Copy, 
  Check, 
  Sparkles, 
  ExternalLink,
  ShieldCheck,
  Cpu
} from 'lucide-react';
import CHANGELOG_MARKDOWN from '../CHANGELOG.md?raw';

interface ReleaseSection {
  version: string;
  title: string;
  content: string[];
}

export function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedVersion, setSelectedVersion] = useState('all');
  const [copiedVersion, setCopiedVersion] = useState<string | null>(null);
  const [expandedVersions, setExpandedVersions] = useState<Record<string, boolean>>({ 'v3.0.0-beta': true, 'v2.9.6': true });

  const releases: ReleaseSection[] = useMemo(() => {
    const rawSections = CHANGELOG_MARKDOWN.split(/\\n(?=## )/);
    const parsed: ReleaseSection[] = [];

    for (const section of rawSections) {
      const lines = section.trim().split('\\n');
      if (lines.length === 0) continue;
      const headerLine = lines[0];
      if (!headerLine.startsWith('## ')) continue;

      const versionMatch = headerLine.match(/##\\s+(v[\\w.-]+)/);
      const version = versionMatch ? versionMatch[1] : headerLine.replace('## ', '').trim();
      const title = headerLine.replace('## ', '').trim();
      const content = lines.slice(1);

      parsed.push({ version, title, content });
    }
    return parsed;
  }, []);

  const filteredReleases = useMemo(() => {
    return releases.filter(r => {
      if (selectedVersion !== 'all' && r.version !== selectedVersion) {
        return false;
      }
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      if (r.title.toLowerCase().includes(q)) return true;
      return r.content.some(line => line.toLowerCase().includes(q));
    });
  }, [releases, selectedVersion, searchQuery]);

  const toggleExpand = (version: string) => {
    setExpandedVersions(prev => ({
      ...prev,
      [version]: !prev[version]
    }));
  };

  const copyChangelog = (version: string, content: string[]) => {
    const text = `## ${version}\\n${content.join('\\n')}`;
    navigator.clipboard.writeText(text);
    setCopiedVersion(version);
    setTimeout(() => setCopiedVersion(null), 2000);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-30 px-6 py-4">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-gradient-to-tr from-cyan-600 to-blue-600 rounded-xl shadow-lg shadow-cyan-500/20 text-white flex items-center justify-center">
              <Radio className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-1.5">
                  Radio & TV Story Segmenter
                </h1>
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/80">
                  v2.9.6
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Desktop Suite Release History & Interactive Changelog Inspector
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3 w-full md:w-auto">
            <a 
              href="https://github.com/bradlinder/RTVS" 
              target="_blank" 
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
            >
              <span>GitHub Repository</span>
              <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
            </a>
            <a 
              href="https://github.com/bradlinder/RTVS/releases" 
              target="_blank" 
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white shadow-sm shadow-cyan-600/30 transition"
            >
              <span>Releases & Binaries</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-6xl w-full mx-auto px-6 py-8 flex-1 flex flex-col gap-6">
        {/* Architecture & Environment Status Banner */}
        <section className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-sm">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-cyan-950/60 border border-cyan-800/60 px-2 py-0.5 rounded">
                  <Cpu className="w-3 h-3" /> Core Engine
                </span>
                <span className="text-xs text-slate-400">Native Python / PySide6 Desktop Application</span>
              </div>
              <p className="text-sm text-slate-300">
                AI-driven audio/video story segmentation, faster-whisper transcription, WeSpeaker voice embedding diarization, and multi-platform broadcast publishing.
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-800/60 border border-slate-700/60 px-3 py-2 rounded-xl">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>WeSpeaker ONNX & MarianMT isolated architecture</span>
            </div>
          </div>
        </section>

        {/* Filter and Search Bar */}
        <section className="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input 
              type="text"
              placeholder="Search features, fixes, or modules..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Filter className="w-3.5 h-3.5" />
              <span>Filter:</span>
            </div>
            <select
              value={selectedVersion}
              onChange={e => setSelectedVersion(e.target.value)}
              className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 transition cursor-pointer"
            >
              <option value="all">All Releases ({releases.length})</option>
              {releases.map(r => (
                <option key={r.version} value={r.version}>{r.version}</option>
              ))}
            </select>
          </div>
        </section>

        {/* Changelog Accordion List */}
        <section className="space-y-4">
          {filteredReleases.length === 0 ? (
            <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl bg-slate-900/20">
              <p className="text-slate-400 text-sm">No release notes matched your search query.</p>
              <button 
                onClick={() => { setSearchQuery(''); setSelectedVersion('all'); }}
                className="mt-3 text-xs text-cyan-400 hover:text-cyan-300 underline"
              >
                Reset search filters
              </button>
            </div>
          ) : (
            filteredReleases.map(release => {
              const isExpanded = expandedVersions[release.version] ?? (release.version === 'v2.9.6' || release.version === 'v2.9.5');
              const isLatest = release.version === 'v2.9.6';

              return (
                <article 
                  key={release.version}
                  className={`border rounded-2xl transition-all duration-200 ${
                    isLatest 
                      ? 'border-cyan-800/80 bg-slate-900/70 shadow-lg shadow-cyan-950/20' 
                      : 'border-slate-800 bg-slate-900/30 hover:border-slate-700'
                  }`}
                >
                  <header 
                    onClick={() => toggleExpand(release.version)}
                    className="p-5 flex items-center justify-between cursor-pointer select-none gap-4"
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-1 rounded-lg bg-slate-800 text-slate-300">
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4 text-cyan-400" />
                        ) : (
                          <ChevronRight className="w-4 h-4" />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="text-base font-bold text-white tracking-tight">
                            {release.title}
                          </h2>
                          {isLatest && (
                            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 flex items-center gap-1">
                              <Sparkles className="w-3 h-3" /> Latest Release
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {release.content.filter(l => l.trim().startsWith('- **')).length} major milestone updates
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                      <button
                        onClick={() => copyChangelog(release.version, release.content)}
                        className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition text-xs flex items-center gap-1.5"
                        title="Copy release notes markdown"
                      >
                        {copiedVersion === release.version ? (
                          <>
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                            <span className="text-[11px] text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5" />
                            <span className="text-[11px]">Copy Markdown</span>
                          </>
                        )}
                      </button>
                    </div>
                  </header>

                  {isExpanded && (
                    <div className="px-6 pb-6 pt-2 border-t border-slate-800/80 text-sm text-slate-300 space-y-3 font-sans leading-relaxed">
                      {release.content.map((line, idx) => {
                        const trimmed = line.trim();
                        if (!trimmed) return null;

                        if (trimmed.startsWith('- **')) {
                          const parts = trimmed.slice(2).split(':**');
                          const title = parts[0]?.replace(/^\\*\\*/, '');
                          const rest = parts.slice(1).join(':**');

                          return (
                            <div key={idx} className="mt-3 first:mt-1">
                              <h3 className="text-slate-100 font-semibold text-sm flex items-center gap-2 text-cyan-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 inline-block" />
                                {title}
                              </h3>
                              {rest && <p className="text-slate-300 text-xs mt-1 ml-3.5">{rest}</p>}
                            </div>
                          );
                        }

                        if (trimmed.startsWith('- ')) {
                          return (
                            <li key={idx} className="ml-6 text-xs text-slate-300 list-disc marker:text-slate-500">
                              {trimmed.slice(2)}
                            </li>
                          );
                        }

                        if (trimmed.startsWith('  - ')) {
                          return (
                            <li key={idx} className="ml-10 text-xs text-slate-400 list-circle marker:text-slate-600">
                              {trimmed.slice(4)}
                            </li>
                          );
                        }

                        return (
                          <p key={idx} className="text-xs text-slate-300">
                            {trimmed}
                          </p>
                        );
                      })}
                    </div>
                  )}
                </article>
              );
            })
          )}
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-6 px-6 text-center text-xs text-slate-500">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <p>Radio & TV Story Segmenter desktop suite - Built for broadcast journalism.</p>
          <p className="text-slate-600">Live preview dynamically synchronized with repository documentation</p>
        </div>
      </footer>
    </div>
  );
}
"""


def get_project_version() -> str:
    """Read PROJECT_VERSION from prs_shared.py."""
    prs_path = ROOT_DIR / "prs_shared.py"
    if prs_path.is_file():
        content = prs_path.read_text(encoding="utf-8")
        match = re.search(r'PROJECT_VERSION\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            v = match.group(1).strip()
            # Collapse any duplicate dots
            return re.sub(r"\.+", ".", v)
    return "2.9.6"


def restore_preview(force: bool = False) -> int:
    """Ensure all preview scaffolding files exist with up-to-date version strings."""
    version = get_project_version()
    print(f"[PREVIEW] Synchronizing web preview scaffolding for v{version}...")

    files = {
        ROOT_DIR / "package.json": PACKAGE_JSON_TEMPLATE.replace("__VERSION__", version),
        ROOT_DIR / "tsconfig.json": TSCONFIG_JSON_TEMPLATE,
        ROOT_DIR / "vite.config.ts": VITE_CONFIG_TEMPLATE,
        ROOT_DIR / "tailwind.config.js": TAILWIND_CONFIG_TEMPLATE,
        ROOT_DIR / "postcss.config.js": POSTCSS_CONFIG_TEMPLATE,
        ROOT_DIR / "eslint.config.js": ESLINT_CONFIG_TEMPLATE,
        ROOT_DIR / "metadata.json": METADATA_JSON_TEMPLATE.replace("__VERSION__", version),
        ROOT_DIR / "index.html": INDEX_HTML_TEMPLATE.replace("__VERSION__", version),
        ROOT_DIR / "src" / "main.tsx": SRC_MAIN_TSX,
        ROOT_DIR / "src" / "index.css": SRC_INDEX_CSS,
        ROOT_DIR / "src" / "vite-env.d.ts": SRC_VITE_ENV_D_TS,
        ROOT_DIR / "src" / "App.tsx": SRC_APP_TSX,
    }

    created = 0
    updated = 0

    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            print(f"  + Created: {path.relative_to(ROOT_DIR)}")
            created += 1
        elif force:
            path.write_text(content, encoding="utf-8")
            print(f"  * Overwritten: {path.relative_to(ROOT_DIR)}")
            updated += 1

    print(f"[PREVIEW] Preview restoration complete ({created} created, {updated} updated).")
    return 0


def sync_version(version: str | None = None) -> int:
    """Synchronize the application version into package.json, metadata.json, and index.html."""
    if not version:
        version = get_project_version()
    clean_version = re.sub(r"\.+", ".", str(version).strip().lstrip("v"))
    print(f"[PREVIEW] Synchronizing version v{clean_version} across preview files...")

    # 1. package.json
    pkg_path = ROOT_DIR / "package.json"
    if pkg_path.is_file():
        try:
            data = json.loads(pkg_path.read_text(encoding="utf-8"))
            if data.get("version") != clean_version:
                data["version"] = clean_version
                pkg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                print(f"  * Synchronized package.json -> v{clean_version}")
        except Exception as e:
            print(f"  ! Error updating package.json: {e}")

    # 2. metadata.json
    meta_path = ROOT_DIR / "metadata.json"
    if meta_path.is_file():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            data["description"] = f"Radio & TV Segmenter v{clean_version} - AI-powered audio/video transcription, diarization, translation, and story segmentation suite."
            meta_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"  * Synchronized metadata.json -> v{clean_version}")
        except Exception as e:
            print(f"  ! Error updating metadata.json: {e}")

    # 3. index.html
    html_path = ROOT_DIR / "index.html"
    if html_path.is_file():
        try:
            content = html_path.read_text(encoding="utf-8")
            content = re.sub(r"<title>Radio & TV Segmenter v[^<]+</title>", f"<title>Radio & TV Segmenter v{clean_version}</title>", content)
            content = re.sub(r'content="Radio & TV Segmenter v[^"-]+ -', f'content="Radio & TV Segmenter v{clean_version} -', content)
            content = re.sub(r'content="Radio & TV Segmenter v[^"]+"', f'content="Radio & TV Segmenter v{clean_version}"', content)
            html_path.write_text(content, encoding="utf-8")
            print(f"  * Synchronized index.html -> v{clean_version}")
        except Exception as e:
            print(f"  ! Error updating index.html: {e}")

    print("[PREVIEW] Version synchronization complete.")
    return 0


def verify_preview() -> int:
    """Verify that all preview files exist and are valid."""
    required_files = [
        ROOT_DIR / "package.json",
        ROOT_DIR / "tsconfig.json",
        ROOT_DIR / "vite.config.ts",
        ROOT_DIR / "metadata.json",
        ROOT_DIR / "index.html",
        ROOT_DIR / "src" / "main.tsx",
        ROOT_DIR / "src" / "App.tsx",
        ROOT_DIR / "src" / "index.css",
        ROOT_DIR / "src" / "vite-env.d.ts",
    ]

    missing = [f.relative_to(ROOT_DIR) for f in required_files if not f.exists()]
    if missing:
        print(f"[PREVIEW] Missing preview files: {', '.join(str(m) for m in missing)}")
        print("[PREVIEW] Run `python preview_manager.py --restore` to restore.")
        return 1

    print("[PREVIEW] All web preview scaffolding files are present and verified.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Studio Web Preview Scaffolding Manager")
    parser.add_argument("--restore", action="store_true", help="Restore any missing preview files")
    parser.add_argument("--force", action="store_true", help="Force overwrite all preview files with fresh defaults")
    parser.add_argument("--sync", action="store_true", help="Synchronize versions across preview files from prs_shared.py")
    parser.add_argument("--version-str", help="Specify an explicit version string for sync")
    parser.add_argument("--verify", action="store_true", help="Check integrity of preview files")

    args = parser.parse_args()

    if args.force:
        return restore_preview(force=True)
    if args.restore:
        return restore_preview(force=False)
    if args.sync or args.version_str:
        return sync_version(version=args.version_str)
    if args.verify:
        return verify_preview()

    # Default action: verify, restore if missing, and sync version
    if verify_preview() != 0:
        restore_preview(force=False)
    return sync_version()


if __name__ == "__main__":
    sys.exit(main())
