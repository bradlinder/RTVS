# Radio & TV Story Segmenter

Radio & TV Story Segmenter is a cross-platform desktop application built with Python and PySide6. Designed for broadcast journalists, audio producers, podcasters, and researchers, it transcribes long-form audio and video recordings, labels distinct speakers, translates text across languages, and segments programs into independent, publishable stories.

---

## Features

* Automated Speech Transcription: Powered by faster-whisper (CTranslate2) with local Whisper models from tiny up to large-v3.
* Speaker Diarization: Uses diarize (Silero VAD + WeSpeaker ONNX embeddings) to detect and attribute speakers across multi-person interviews and panel segments without requiring heavy PyTorch dependencies in the core application.
* Bilingual Translation: Direct in-app Spanish/English translation using local Helsinki-NLP MarianMT transformer models with sentence-level alignment via an isolated plugin runtime.
* Interactive Transcript Editor: Click-to-seek playback navigation, inline text correction, customizable font scaling, and speaker reattribution tools.
* Visual Waveform Timeline: Synchronized timeline with zoom, scrub markers, region selection, and optional video thumbnail strips.
* Hardware Acceleration: Optional NVIDIA CUDA acceleration (Windows) for faster-whisper and diarization via an on-demand download, keeping the default application CPU-first and lightweight across platforms.
* Multi-Format Publishing & Exports:
  * Standard Subtitles (SRT, VTT)
  * Plain and annotated transcripts (TXT, Markdown, CSV)
  * Cockos Reaper Digital Audio Workstation project markers (EDL)
  * WordPress REST API direct draft/post creation
  * Audio segment extractions sliced directly through FFmpeg



---

## Installation & Setup

### 1. Prerequisites

* Python: 3.10 to 3.12 (64-bit recommended)
* FFmpeg: Must be installed and accessible in your system PATH (or placed in the project root directory).
* Node.js 18+ & npm: (Optional) Only required if building the integrated React/Vite transcript preview components.

### 2. Environment Configuration

Clone the repository and set up a virtual environment:

Windows:
python -m venv venv
venv\Scripts\activate

Linux / macOS:
python3 -m venv venv
source venv/bin/activate

Install standard application requirements:
pip install -r requirements.txt

### 3. GPU Hardware Acceleration (Optional - Windows NVIDIA)

The base application is CPU-first by design to keep download and install footprints minimal and universally compatible across platforms. On Windows systems equipped with a supported NVIDIA GPU, you can optionally download and enable a dedicated CUDA-accelerated Whisper and diarization environment:
1. Open the application.
2. Go to **Settings > GPU Acceleration (NVIDIA CUDA)...**
3. Click **Download and Install** to provision the isolated CUDA runtime.
4. Check **Use GPU acceleration when available**.

---

## Running the Application

Launch the desktop client via:
python RadioTVSegmenter.py

Or on Windows:
Run_RadioTVSegmenter.bat

---

## Workflows & Export Integrations

### Segmenting Stories

1. Load Media: Drag and drop an audio or video file onto the timeline canvas or select File -> Open Media...
2. Process Pipeline: Use Tools -> Multi-Stage Processing... (Ctrl+R / Cmd+R) to run transcription, speaker detection, and automated story segmentation in sequence.
3. Refine Segments: Highlight text in the transcript or drag region handles on the timeline, then click Add Story to create segment boundaries.

### Cockos Reaper DAW (EDL Marker Export)

* Exports selected stories and timeline cuts into a standard EDL (.edl) edit decision list compatible with Reaper and Samplitude.
* Import into Reaper:
1. Open Cockos Reaper.
2. Choose File -> Open Project or Item -> Open Items in Editor.
3. Select the generated .edl file. Segments will map onto the timeline with speaker markers preserved.



### WordPress Direct Publishing

* Pushes selected segmented stories and transcribed body copy directly to WordPress sites via the REST API.
* Setup & Authentication:
1. In WordPress Admin, navigate to Users -> Profile.
2. Scroll down to Application Passwords, enter a descriptive name (e.g., StorySegmenter), and click Add New Application Password.
3. Copy the 24-character generated password (with spaces) into the application's WordPress Export dialog along with your site URL and username. Note: Your regular login password is not accepted by the REST API.



---

## Keyboard Shortcuts

| Category | Action | Windows / Linux | macOS |
| --- | --- | --- | --- |
| **Playback** | Play / Pause | `Space` | `Space` |
| **Playback** | Seek Forward / Backward | `Right` / `Left` | `Right` / `Left` |
| **Playback** | Seek to Start / End | `Home` / `End` | `Home` / `End` |
| **Playback** | Timeline Zoom | `+` / `-` | `+` / `-` |
| **Display** | Transcript Font Scale | `Ctrl++` / `Ctrl+-` / `Ctrl+0` | `Cmd++` / `Cmd+-` / `Cmd+0` |
| **File** | New Project | `Ctrl+N` | `Cmd+N` |
| **File** | Open Media File | `Ctrl+O` | `Cmd+O` |
| **File** | Open Document | `Ctrl+Alt+O` | `Cmd+Option+O` |
| **File** | Open Project Session | `Ctrl+Shift+O` | `Cmd+Shift+O` |
| **File** | Close Project | `Ctrl+W` | `Cmd+W` |
| **File** | Save Project / Save As | `Ctrl+S` / `Ctrl+Shift+S` | `Cmd+S` / `Cmd+Shift+S` |
| **File** | Export Dialog | `Ctrl+E` | `Cmd+E` |
| **File** | Batch Processing | `Ctrl+Shift+B` | `Cmd+Shift+B` |
| **File** | Exit Application | `Ctrl+Q` | `Cmd+Q` |
| **Panels** | Toggle Timeline Panel | `Alt+1` | `Ctrl+Option+1` |
| **Panels** | Toggle Transcript Panel | `Alt+2` | `Ctrl+Option+2` |
| **Panels** | Toggle Stories Panel | `Alt+3` | `Ctrl+Option+3` |
| **Panels** | Toggle Activity History Panel | `Alt+4` | `Ctrl+Option+4` |
| **View** | Toggle Waveform Display | `Ctrl+Alt+W` | `Cmd+Option+W` |
| **View** | Toggle Video Thumbnails | `Ctrl+Alt+T` | `Cmd+Option+T` |
| **View** | Toggle Video Preview Window | `Ctrl+Shift+M` | `Cmd+Shift+M` |
| **View** | Toggle Speaker Labels | `Ctrl+Alt+S` | `Cmd+Option+S` |
| **View** | Toggle Timestamps | `Ctrl+Alt+I` | `Cmd+Option+I` |
| **Edit** | Undo / Redo | `Ctrl+Z` / `Ctrl+Y` | `Cmd+Z` / `Cmd+Shift+Z` |
| **Edit** | Find and Replace | `Ctrl+F` | `Cmd+F` |
| **Edit** | Find Next Match | `Ctrl+G` | `Cmd+G` |
| **Tools** | Transcribe Audio | `Ctrl+T` | `Cmd+T` |
| **Tools** | Detect Speakers (Diarization) | `Ctrl+D` | `Cmd+D` |
| **Tools** | Detect Stories | `Ctrl+Shift+A` | `Cmd+Shift+A` |
| **Tools** | Translate Transcript | `Ctrl+Shift+L` | `Cmd+Shift+L` |
| **Tools** | Multi-Stage Processing Pipeline | `Ctrl+R` | `Cmd+R` |
| **Tools** | Batch Processing | `Ctrl+B` | `Cmd+B` |
| **Tools** | Regenerate Waveform | `Ctrl+Shift+W` | `Cmd+Shift+W` |
| **Tools** | Regenerate Video Thumbnails | `Ctrl+Shift+T` | `Cmd+Shift+T` |
| **Tools** | Clear Temporary Cache | `Ctrl+Alt+C` | `Cmd+Option+C` |
| **Tools** | Manage AI Models | `Ctrl+M` | `Cmd+M` |
| **Tools** | Manage Plugins & Add-ons | `Ctrl+Shift+X` | `Cmd+Shift+X` |
| **Settings** | Preferences | `Ctrl+P` | `Cmd+,` |
| **Settings** | Customize Keyboard Shortcuts | `Ctrl+K` | `Cmd+K` |
| **Settings** | GPU Acceleration Settings | `Ctrl+Alt+G` | `Cmd+Option+G` |
| **Settings** | Glossary & Custom Vocabulary | `Ctrl+Shift+G` | `Cmd+Shift+G` |
| **Settings** | Check for Updates | `Ctrl+U` | `Cmd+U` |
| **Help** | Keyboard Shortcuts Reference | `F1` | `Cmd+?` |
| **Help** | About Radio & TV Story Segmenter | `Shift+F1` | `Shift+F1` |
| **Help** | Open Diagnostic Log Folder | `Ctrl+Shift+K` | `Cmd+Shift+K` |
| **Help** | Third-Party Licenses | `Ctrl+Shift+F1` | `Cmd+Shift+F1` |

---

## AI Studio Web Preview

The web preview in Google AI Studio is configured to serve as the live, interactive **Changelog & Release Notes Viewer** for the project (sourced from `CHANGELOG.md`). It provides search, version filtering, collapsible release cards, and markdown copying capabilities for desktop application updates.

---

## Third-Party Notices & License

Radio & TV Story Segmenter is released under the MIT License.

This application incorporates or interfaces with several open source libraries and pre-trained models:

* faster-whisper & CTranslate2: MIT License
* diarize: Apache 2.0 License (FoxNoseTech)
* Silero VAD: MIT License
* WeSpeaker & sherpa-onnx: Apache 2.0 License
* onnxruntime: MIT License
* Hugging Face Transformers & MarianMT (Translation Plugin): Apache 2.0 License
* uv (Isolated Python & Dependency Packaging): MIT / Apache 2.0 License (Astral Software)
* PySide6 / Qt 6: LGPL v3 / Commercial
* scipy & scikit-learn: BSD 3-Clause License
* cryptography & keyring: Apache 2.0 / PSF License
* FFmpeg: LGPL v2.1+ / GPL v2+ (executed externally)

For full license texts and copyright acknowledgments, see NOTICES.txt or open Help -> Third-Party Licenses within the application.

## Acknowledgments

This project was developed with the aid of AI collaboration tools, including Gemini, Claude, and ChatGPT.
