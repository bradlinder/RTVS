import React, { useState, useMemo } from 'react';
import { 
  Sparkles, 
  Search, 
  ChevronDown, 
  ChevronRight, 
  Copy, 
  Check, 
  Tag, 
  GitBranch, 
  Terminal, 
  FileText, 
  Layers, 
  ExternalLink,
  ShieldCheck,
  Cpu
} from 'lucide-react';

// Complete changelog source of truth matching CHANGELOG.md
const CHANGELOG_MARKDOWN = `# Changelog

## v2.9.2
- **Documentation Alignment & Post-Plugin Architecture Audit**:
  - Reconciled STABILITY_NOTES.md and BUILD_INSTRUCTIONS.txt to remove stale references claiming Hugging Face Transformers is tested in the core frozen binary, documenting that it lives strictly within the isolated plugins/translation/ virtual environment.
  - Aligned core application runtime documentation with the modular post-plugin architecture.
- **WeSpeaker ONNX Embedding Engine Clarification**:
  - Confirmed and documented wespeakerruntime in requirements.txt and radio_tv_story_segmenter_worker.py as the dedicated, high-performance ONNX speaker voice embedding engine (wespeaker_rt.Speaker(lang="en")) for speaker diarization.
- **Repository Hygiene & Release Governance**:
  - Maintained .gitignore patterns preventing temporary build artifacts and virtual environments from being tracked.
  - Enforced release archive distribution governance via GitHub Releases.
- **Version Alignment**:
  - Bumped application version to v2.9.2 across prs_shared.py, updater.py, build_installer.py, RadioTVStorySegmenter.iss, package.json, plugin manifests (wordpress, youtube, translation), metadata, and documentation.

## v2.9.1
- **Seamless App Upgrade Plugin Synchronization**:
  - Automatically checks and upgrades installed plugins in the user directory when a newer bundled version is shipped with an application update.
  - Ensures existing users who upgrade the desktop application automatically receive all updated core plugin features without requiring manual reinstallation.
- **Independent Plugin Update Checker ("Check for Updates...")**:
  - Added a dedicated "Check for Updates..." action to the Plugin Manager (Tools > Manage Plugins & Add-ons), enabling users to check GitHub releases for newer versions of installed plugins and update them in-place without needing to rebuild or reinstall the core application.
  - Automatically compares installed plugin versions against the latest release assets published on GitHub (.rtvs-addon and .zip packages).
  - Displays a detailed update summary showing current vs. remote versions (e.g. WordPress Publisher: v2.8.0 -> v2.9.1) with one-click batch updating.
- **Enhanced In-App Plugin Browser & Update Actions**:
  - Updated the GitHub Plugins Browser dialog to detect when an installed plugin has a newer version available on GitHub, showing highlighted "Update Available (v...)" badges.
  - Added dedicated "Update to v..." action buttons for each outdated plugin, along with an "Update All Available" batch button on the toolbar.
  - Automatically reloads updated plugins dynamically and refreshes export menus immediately upon installation without requiring an app restart.
- **WordPress Publisher Plugin Custom Header / Footer Notices**:
  - Added custom header/footer text areas with placement selection (top or bottom of post).
  - Added search engine directive suppression (data-nosnippet="true" and <!--googleoff: all-->...<!--googleon: all-->) to prevent disclaimer text from overriding search engine result snippets while keeping the article fully indexable.
  - Added WordPress excerpt exclusion to keep post summaries clean in theme archives.
  - Added "Save Text & Options as Default" to persist custom notice text across all future posts.
- **Export UI Stability & Widget Proxy Fix**:
  - Fixed AttributeError: 'ResizableTextEdit' object has no attribute 'setPlaceholderText' by implementing complete QTextEdit method forwarding (setPlaceholderText, placeholderText, clear, text, document, and dynamic __getattr__ delegation) on ResizableTextEdit.
- **Independent Modular Plugin Build & Packaging Tooling**:
  - Added --plugin <name> CLI option to build_installer.py (e.g., python build_installer.py --plugin wordpress) to package .rtvs-addon packages independently of the full installer.
  - Updated CI/CD workflow (.github/workflows/build.yml) to support standalone plugin builds.


## v2.8.7
- **Speaker Detection & Diarization Native Runtime Resolution**:
  - Resolved Python virtual environment execution pathways for PyAnnote speaker diarization on Linux, macOS, and Windows.
  - Added robust fallback logic for embedded standalone binary runtimes in packaged pyinstaller distributions.
- **Model Management & Transcription Enhancements**:
  - Upgraded Faster-Whisper integration with improved memory management and chunked audio decoding.
  - Added detailed progress feedback during multi-file batch transcription.

## v2.8.6
- **Modular Plugin Architecture**:
  - Decoupled core application logic from publishing and translation extensions into isolated modular add-ons (wordpress, youtube, translation).
  - Added dynamic plugin discovery and execution from user data directories and bundled packages.
- **UI Design System Refinements**:
  - Upgraded all dialogs with a high-contrast warm neutral palette, consistent typographic scales, and optimized spacing.

## v2.8.5
- **Enhanced Export Suite**:
  - Added advanced formatting controls for Word (.docx), subtitle (.srt), and plain text exports.
  - Improved paragraph reflowing and timestamp alignment.

## v2.8.3
- **Audio Workspace Performance**:
  - Optimized waveform rendering cache for long-form audio recordings (up to 4+ hours).
  - Reduced memory footprint during multi-speaker diarization passes.

## v2.8.2
- **Translation & Localization**:
  - Added local neural machine translation support via MarianMT models for offline bilingual publishing.

## v2.8.1
- **Initial Modular Release**:
  - Established core desktop suite architecture for radio and TV story segmentation, transcription, and broadcast publishing.
`;

interface ReleaseSection {
  version: string;
  title: string;
  content: string[];
}

export function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedVersion, setSelectedVersion] = useState('all');
  const [copiedVersion, setCopiedVersion] = useState<string | null>(null);
  const [expandedVersions, setExpandedVersions] = useState<Record<string, boolean>>({ 'v2.9.2': true, 'v2.9.1': true });


  const releases: ReleaseSection[] = useMemo(() => {
    const rawSections = CHANGELOG_MARKDOWN.split(/\n(?=## )/);
    const parsed: ReleaseSection[] = [];

    for (const section of rawSections) {
      const lines = section.trim().split('\n');
      if (lines.length === 0) continue;
      const headerLine = lines[0];
      if (!headerLine.startsWith('## ')) continue;

      const versionMatch = headerLine.match(/##\s+(v[\d\.]+)/);
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
    const text = `## ${version}\n${content.join('\n')}`;
    navigator.clipboard.writeText(text);
    setCopiedVersion(version);
    setTimeout(() => setCopiedVersion(null), 2000);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-30">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20 text-white font-bold">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base sm:text-lg tracking-tight text-white">Radio & TV Segmenter</span>
                <span className="px-2.5 py-0.5 text-xs font-semibold bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 rounded-full flex items-center gap-1">
                  <Sparkles className="w-3 h-3" /> v2.9.2 Latest
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">Full Interactive Project Release Changelog</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a
              href="https://github.com/bradlinder/RTVS"
              target="_blank"
              rel="noreferrer"
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 transition flex items-center gap-1.5 border border-slate-700"
            >
              <ExternalLink className="w-3.5 h-3.5 text-slate-400" /> GitHub Repository
            </a>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 flex flex-col gap-6">
        {/* Intro banner / Search & Filter */}
        <div className="flex flex-col md:flex-row gap-4 items-stretch md:items-center justify-between bg-slate-900/50 border border-slate-800/80 rounded-2xl p-4 sm:p-6 shadow-xl">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2">
              <span>Release History & Changelog</span>
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Explore the complete evolution, modular plugin upgrades, and bug fixes across all versions.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-3">
            {/* Version Filter */}
            <div className="relative w-full sm:w-auto">
              <select
                value={selectedVersion}
                onChange={e => setSelectedVersion(e.target.value)}
                className="w-full sm:w-44 bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-xl px-3 py-2.5 focus:outline-none focus:border-cyan-500 transition cursor-pointer"
              >
                <option value="all">All Versions ({releases.length})</option>
                {releases.map(r => (
                  <option key={r.version} value={r.version}>{r.title}</option>
                ))}
              </select>
            </div>

            {/* Search Input */}
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search changelog..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-xl pl-9 pr-3 py-2.5 focus:outline-none focus:border-cyan-500 transition placeholder:text-slate-500"
              />
            </div>
          </div>
        </div>

        {/* Releases List */}
        <div className="flex flex-col gap-4">
          {filteredReleases.length === 0 ? (
            <div className="text-center py-16 bg-slate-900/30 border border-slate-800 rounded-2xl">
              <FileText className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-300 font-medium text-sm">No matching release notes found</p>
              <p className="text-slate-500 text-xs mt-1">Try adjusting your search query or version filter.</p>
            </div>
          ) : (
            filteredReleases.map((release) => {
              const isExpanded = expandedVersions[release.version] ?? true;
              const isCopied = copiedVersion === release.version;

              return (
                <div 
                  key={release.version}
                  className="bg-slate-900/60 border border-slate-800/80 rounded-2xl overflow-hidden shadow-lg transition hover:border-slate-700"
                >
                  {/* Release Header */}
                  <div 
                    onClick={() => toggleExpand(release.version)}
                    className="px-6 py-4 flex items-center justify-between cursor-pointer bg-slate-900/90 select-none border-b border-slate-800/50"
                  >
                    <div className="flex items-center gap-3">
                      <button className="text-slate-400 hover:text-slate-200 transition">
                        {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </button>
                      <span className="font-bold text-base text-white tracking-wide">
                        {release.title}
                      </span>
                      {release.version === releases[0]?.version && (
                        <span className="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded-full uppercase tracking-wider">
                          Latest
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                      <button
                        onClick={() => copyChangelog(release.version, release.content)}
                        className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition flex items-center gap-1.5 border border-slate-700"
                        title="Copy release notes"
                      >
                        {isCopied ? (
                          <>
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                            <span className="text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5 text-slate-400" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Release Content */}
                  {isExpanded && (
                    <div className="p-6 text-slate-300 text-sm leading-relaxed space-y-3 bg-slate-950/40">
                      {release.content.map((line, idx) => {
                        const trimmed = line.trim();
                        if (!trimmed) return null;

                        if (trimmed.startsWith('- **') || trimmed.startsWith('- *')) {
                          const parts = trimmed.replace(/^- \*\*/, '').split('**:');
                          const title = parts[0];
                          const body = parts.slice(1).join('**:');

                          return (
                            <div key={idx} className="mt-3 first:mt-0">
                              <div className="flex items-start gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 mt-2 shrink-0"></span>
                                <div>
                                  <span className="font-semibold text-white">{title}</span>
                                  {body && <span className="text-slate-300">:{body}</span>}
                                </div>
                              </div>
                            </div>
                          );
                        } else if (trimmed.startsWith('  - ')) {
                          const subText = trimmed.replace(/^  - /, '');
                          return (
                            <div key={idx} className="ml-5 flex items-start gap-2 text-xs text-slate-400 my-1">
                              <span className="w-1 h-1 rounded-full bg-slate-600 mt-1.5 shrink-0"></span>
                              <span>{subText}</span>
                            </div>
                          );
                        } else {
                          return (
                            <p key={idx} className="text-xs text-slate-400">{trimmed}</p>
                          );
                        }
                      })}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-900/40 py-6 mt-12 text-center text-xs text-slate-500">
        <p>Radio & TV Segmenter v2.9.2 — Professional Broadcast Story Segmentation & Modular Publishing Suite</p>
      </footer>

    </div>
  );
}

export default App;
