# Radio & TV Segmenter 1.7

Cross-platform story segmenter and transcriber for Windows, macOS, and Linux (Debian/Ubuntu).

## Distribution model

The base application is **CPU-first and CPU-only**. Large optional GPU packages are not included in the installer. AI models are downloaded only when needed, and optional NVIDIA CUDA support can be installed later from Settings on supported Windows systems.

Mutable data (models, logs, cached translation models, optional runtimes, and settings) is stored in the user's application-data directory rather than beside the installed executable.

## Build the application

Build on the target operating system; PyInstaller does not cross-compile.

1. Create a clean Python 3.12 build environment.
2. Install the build/runtime dependencies from `requirements.txt` and `requirements-build.txt`.
3. Install **CPU-only PyTorch** in the build environment. For Windows/Linux, use the PyTorch CPU wheel index so CUDA libraries are not accidentally added to the installer.
4. Make `ffmpeg` and `ffprobe` available on PATH, or set `PRS_FFMPEG_DIR` to the directory containing them.
5. Run:

```text
python build_installer.py
```

The build copies FFmpeg/ffprobe into the application's private runtime directory. End users do not need a separate FFmpeg installation.

### Windows installer

Build `dist\\RadioTVSegmenter` first, then open `installer/Windows/RadioTVStorySegmenter.iss` with Inno Setup and compile it. The resulting installer is written to `dist\\installer`.

The installer does **not** remove the user's application-data directory when uninstalled.

### macOS installer

Build `dist/RadioTVSegmenter.app` first, then run:

```text
installer/macOS/build_app.sh
```

Set `DEVELOPER_ID_APPLICATION` before running the script to sign the app. Set `NOTARY_PROFILE` to an existing `notarytool` keychain profile to submit and staple the DMG.

### Linux (Debian / Ubuntu) installer

Build `dist/RadioTVSegmenter` first, then run:

```text
bash installer/Linux/build_deb.sh
```

Or run the automated 1-click build script:

```text
./build_linux.sh
```

The resulting package `dist/RadioTVSegmenter-1.7-Linux-amd64.deb` can be installed on any Debian or Ubuntu system using:

```text
sudo apt install ./dist/RadioTVSegmenter-1.7-Linux-amd64.deb
```

A standalone compressed tarball (`dist/RadioTVSegmenter-1.7-Linux-x86_64.tar.gz`) is also generated for non-Debian distributions.

## Optional GPU support

The base installer does not contain CUDA, NVIDIA libraries, or a second Python environment. On supported Windows systems, Settings > Processing > GPU Acceleration (NVIDIA CUDA) can provision the optional environment after installation. The Windows package contains only the small `uv` runtime manager needed to create the private Python environment; the large CUDA-enabled packages are downloaded only if the user chooses GPU acceleration.

macOS currently runs CPU-only because the optional backend is NVIDIA CUDA.

## Size-control rules

- Do not use `--collect-all PySide6`; only the Qt modules actually used by the application are collected.
- Do not build with CUDA-enabled PyTorch.
- Do not bundle translation-only or GPU-only dependencies beyond what the current CPU pipeline actually imports.
- Keep AI model files out of the installer; download them on demand.

## Updates and Releases

Radio & TV Segmenter includes an integrated update mechanism that connects directly to GitHub Releases:

- **Check for Updates Dialog**: Access via **About > Check for Updates…** or the **Preferences > Updates & GitHub** category.
- **Automated Platform Asset Matching**: Queries the latest GitHub release metadata and identifies the correct binary package for the current operating system (`.exe` on Windows, `.dmg` on macOS, `.deb` on Debian/Ubuntu, `.tar.gz` on Linux).
- **Background Download & Installation**: Downloads releases with live progress and transfer speed indicators, then launches the installer and gracefully closes the running application.
- **Configurable Startup Checks**: Supports optional silent update checks on startup, alerting you in the status bar whenever a new version is published.
- **Repository Customization**: By default queries `bradlinder/RTVS` (https://github.com/bradlinder/RTVS), or a custom fork via `GITHUB_REPO` environment variable or the Preferences dialog.

## License & Attributions

Radio & TV Segmenter is licensed under the [MIT License](LICENSE).

This software incorporates, bundles, and interfaces with open-source software under their respective licenses:
* **PySide6 / Qt 6**: Licensed under the GNU Lesser General Public License version 3 ([LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html)). Dynamically linked; users may replace the Qt shared libraries with compatible builds.
* **FFmpeg / ffprobe**: Licensed under the [LGPLv2.1+](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html) / GPLv2+. Invoked as separate external executables. Source code is available from [ffmpeg.org](https://ffmpeg.org/).
* **faster-whisper & CTranslate2**: Licensed under the [MIT License](https://github.com/SYSTRAN/faster-whisper).
* **OpenAI Whisper**: Licensed under the [MIT License](https://github.com/openai/whisper).
* **PyTorch**: Licensed under the [BSD 3-Clause License](https://github.com/pytorch/pytorch).
* **Hugging Face Transformers & Hub**: Licensed under the [Apache License 2.0](https://github.com/huggingface/transformers).
* **NumPy**: Licensed under the [BSD 3-Clause License](https://github.com/numpy/numpy).
* **python-docx & pypdf**: Licensed under the [MIT License](https://github.com/python-openxml/python-docx) and [BSD 3-Clause License](https://github.com/py-pdf/pypdf).
* **Application Icon**: *"Electronic Media"* by Fatam Organa from [Noun Project](https://thenounproject.com/icon/electronic-media-5929933/), licensed under [Creative Commons Attribution 3.0 Unported (CC BY 3.0)](https://creativecommons.org/licenses/by/3.0/).

See [NOTICES.txt](NOTICES.txt) for the complete legal notices, copyright disclosures, and license texts.
