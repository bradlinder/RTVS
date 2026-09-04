#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Radio & TV Segmenter — Debian / Ubuntu (.deb) Package Builder
# ==============================================================================

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_NAME="RadioTVSegmenter"
PKG_NAME="radiotvsegmenter"

# Extract project version from single source of truth (prs_shared.py)
VERSION=$(python3 -c "from prs_shared import PROJECT_VERSION; print(PROJECT_VERSION)" 2>/dev/null || echo "1.7")
DIST="$ROOT/dist"
SOURCE_APP="$DIST/$APP_NAME"
DEB_FILENAME="RadioTVSegmenter-${VERSION}-Linux-amd64.deb"
DEB_OUTPUT="$DIST/$DEB_FILENAME"
DEB_CANONICAL_OUTPUT="$DIST/${PKG_NAME}_${VERSION}_amd64.deb"

echo "====================================================================="
echo " Packaging Debian / Ubuntu Package (.deb) for ${APP_NAME} v${VERSION}"
echo "====================================================================="

if [[ ! -d "$SOURCE_APP" ]]; then
    echo "[ERROR] Application directory not found: $SOURCE_APP"
    echo "Please compile the application binary first using 'python3 build_installer.py'."
    exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "[ERROR] 'dpkg-deb' utility not found."
    echo "Please install dpkg-dev (e.g. 'sudo apt-get install dpkg-dev')."
    exit 1
fi

STAGING="$DIST/deb_staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"

# 1. Create target Debian filesystem layout
echo "[1/5] Creating Debian package filesystem layout..."
mkdir -p "$STAGING/opt/$APP_NAME"
mkdir -p "$STAGING/usr/bin"
mkdir -p "$STAGING/usr/share/applications"
mkdir -p "$STAGING/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$STAGING/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$STAGING/usr/share/doc/$PKG_NAME"
mkdir -p "$STAGING/DEBIAN"

# 2. Copy compiled application files to /opt/RadioTVSegmenter
echo "[2/5] Copying application files to /opt/$APP_NAME..."
cp -a "$SOURCE_APP/." "$STAGING/opt/$APP_NAME/"

# Ensure executable permissions for binaries
chmod 755 "$STAGING/opt/$APP_NAME/$APP_NAME"
if [[ -d "$STAGING/opt/$APP_NAME/runtime/bin" ]]; then
    chmod 755 "$STAGING/opt/$APP_NAME/runtime/bin/"* 2>/dev/null || true
fi

# 3. Create convenient PATH symlinks
echo "[3/5] Creating executable symlinks in /usr/bin..."
ln -sf "/opt/$APP_NAME/$APP_NAME" "$STAGING/usr/bin/$PKG_NAME"
ln -sf "/opt/$APP_NAME/$APP_NAME" "$STAGING/usr/bin/$APP_NAME"

# 4. Install Desktop file, icons, and legal documentation
echo "[4/5] Installing desktop integration files & metadata..."
cp "$ROOT/installer/Linux/radiotvsegmenter.desktop" "$STAGING/usr/share/applications/radiotvsegmenter.desktop"
chmod 644 "$STAGING/usr/share/applications/radiotvsegmenter.desktop"

if [[ -f "$ROOT/resources/icon.svg" ]]; then
    cp "$ROOT/resources/icon.svg" "$STAGING/usr/share/icons/hicolor/scalable/apps/radiotvsegmenter.svg"
    chmod 644 "$STAGING/usr/share/icons/hicolor/scalable/apps/radiotvsegmenter.svg"
fi

if [[ -f "$ROOT/resources/icon.png" ]]; then
    cp "$ROOT/resources/icon.png" "$STAGING/usr/share/icons/hicolor/256x256/apps/radiotvsegmenter.png"
    chmod 644 "$STAGING/usr/share/icons/hicolor/256x256/apps/radiotvsegmenter.png"
fi

if [[ -f "$ROOT/NOTICES.txt" ]]; then
    cp "$ROOT/NOTICES.txt" "$STAGING/usr/share/doc/$PKG_NAME/copyright"
fi
if [[ -f "$ROOT/LICENSE" ]]; then
    cp "$ROOT/LICENSE" "$STAGING/usr/share/doc/$PKG_NAME/LICENSE"
fi

# Calculate installed size in KiB
INSTALLED_SIZE=$(du -sk "$STAGING" | cut -f1)

# Generate DEBIAN/control file
cat <<EOF > "$STAGING/DEBIAN/control"
Package: ${PKG_NAME}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: amd64
Maintainer: Radio & TV Segmenter Team <https://github.com/bradlinder/RTVS>
Installed-Size: ${INSTALLED_SIZE}
Depends: ffmpeg, libxcb-cursor0, libpulse0
Recommends: pulseaudio | pipewire-pulse
Description: Radio & TV Segmenter
 AI-powered story segmenting, transcription, and editing for broadcast audio/video.
 Radio & TV Segmenter helps journalists, broadcasters, and podcasters
 automatically transcribe audio/video, detect speakers, identify stories,
 and export polished broadcast segments.
EOF

chmod 644 "$STAGING/DEBIAN/control"

# Generate DEBIAN/postinst script (updates desktop & icon caches)
cat <<'EOF' > "$STAGING/DEBIAN/postinst"
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "$STAGING/DEBIAN/postinst"

# Generate DEBIAN/postrm script (cleans up desktop & icon caches)
cat <<'EOF' > "$STAGING/DEBIAN/postrm"
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "$STAGING/DEBIAN/postrm"

# 5. Build .deb package using high-efficiency XZ compression
echo "[5/5] Building .deb archive using XZ compression..."
rm -f "$DEB_OUTPUT" "$DEB_CANONICAL_OUTPUT"
dpkg-deb --build --root-owner-group -Zxz "$STAGING" "$DEB_OUTPUT"
cp "$DEB_OUTPUT" "$DEB_CANONICAL_OUTPUT"

# Cleanup staging directory
rm -rf "$STAGING"

PKG_SIZE=$(ls -lh "$DEB_OUTPUT" | awk '{print $5}')
echo ""
echo "====================================================================="
echo " DEBIAN PACKAGE CREATED SUCCESSFULLY!"
echo " Output File : $DEB_OUTPUT (${PKG_SIZE})"
echo " Standard Ref: $DEB_CANONICAL_OUTPUT"
echo " Installation: sudo apt install ./${DEB_FILENAME}"
echo "====================================================================="
