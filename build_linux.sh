#!/usr/bin/env bash
set -e

# Change directory to the root of the project
cd "$(dirname "$0")"

echo "====================================================================="
echo " Radio & TV Story Segmenter v1.5 - Automated 1-Click Build (Linux)"
echo "====================================================================="
echo ""

# 1. Locate Python 3
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" &> /dev/null; then
    echo "[ERROR] Python 3 was not found on your PATH."
    echo "Please install Python 3.10+ (e.g. 'sudo apt install python3 python3-venv python3-pip')"
    exit 1
fi

echo "[1/4] Using Python: $("$PYTHON_BIN" --version)"

# 2. Setup or verify isolated build virtual environment
if [ ! -d ".venv-build" ]; then
    echo "[2/4] Creating dedicated build virtual environment (.venv-build)..."
    "$PYTHON_BIN" -m venv .venv-build
else
    echo "[2/4] Using existing build virtual environment (.venv-build)..."
fi

source .venv-build/bin/activate

# 3. Upgrade pip and install build dependencies
echo "[3/4] Installing / verifying lightweight CPU build dependencies..."
pip install --upgrade pip --quiet
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu --quiet
pip install -r requirements.txt -r requirements-build.txt --quiet

# 4. Run the installer builder
echo "[4/4] Running PyInstaller binary compilation..."
python3 build_installer.py

echo ""
echo "====================================================================="
echo " BUILD COMPLETE! Standalone binary is located in: dist/RadioTVSegmenter/"
echo "====================================================================="
