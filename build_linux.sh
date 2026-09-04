#!/usr/bin/env bash
set -e

# Change directory to the root of the project
cd "$(dirname "$0")"

echo "====================================================================="
echo " Radio & TV Segmenter v1.7 - Automated 1-Click Build (Linux)"
echo "====================================================================="
echo ""

# 1. Locate Python 3
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" &> /dev/null; then
    echo "[ERROR] Python 3 was not found on your PATH."
    echo "Please install Python 3.10+ (e.g. 'sudo apt install python3 python3-venv python3-pip ffmpeg libxcb-cursor0 libpulse0 binutils dpkg-dev')"
    exit 1
fi

echo "[1/5] Using Python: $("$PYTHON_BIN" --version)"

# 2. Setup or verify isolated build virtual environment
if [ ! -d ".venv-build" ]; then
    echo "[2/5] Creating dedicated build virtual environment (.venv-build)..."
    "$PYTHON_BIN" -m venv .venv-build
else
    echo "[2/5] Using existing build virtual environment (.venv-build)..."
fi

source .venv-build/bin/activate

# 3. Upgrade pip and install build dependencies (CPU-only PyTorch)
echo "[3/5] Installing / verifying lightweight CPU build dependencies..."
pip install --upgrade pip --quiet
pip install --prefer-binary "torch>=2.0.0,<2.4.0" "torchaudio>=2.0.0,<2.4.0" --index-url https://download.pytorch.org/whl/cpu --quiet
pip install --prefer-binary -r requirements.txt -r requirements-build.txt --extra-index-url https://download.pytorch.org/whl/cpu --quiet

# 4. Run the installer builder
echo "[4/5] Running PyInstaller binary compilation..."
python3 build_installer.py

# 5. Build Debian package & distributable tarball
echo "[5/5] Packaging Linux distributions (.deb & .tar.gz)..."
VERSION=$(python3 -c "from prs_shared import PROJECT_VERSION; print(PROJECT_VERSION)" 2>/dev/null || echo "1.7")

if [ -f "installer/Linux/build_deb.sh" ] && command -v dpkg-deb >/dev/null 2>&1; then
    bash installer/Linux/build_deb.sh
else
    echo "[INFO] Skipping .deb packaging (dpkg-deb not present or build_deb.sh missing)."
fi

if [ -d "dist/RadioTVSegmenter" ]; then
    cd dist
    echo "Creating standalone compressed tarball (RadioTVSegmenter-${VERSION}-Linux-x86_64.tar.gz)..."
    tar -czvf "RadioTVSegmenter-${VERSION}-Linux-x86_64.tar.gz" RadioTVSegmenter/
    cd ..
fi

echo ""
echo "====================================================================="
echo " BUILD COMPLETE!"
echo " Distributable packages in dist/:"
ls -lh dist/*.deb dist/*.tar.gz 2>/dev/null || true
echo "====================================================================="
