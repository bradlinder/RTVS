#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_NAME="RadioTVSegmenter"
VERSION=$(python3 -c "from prs_shared import PROJECT_VERSION; print(PROJECT_VERSION)" 2>/dev/null || echo "1.6")
DIST="$ROOT/dist"
APP="$DIST/${APP_NAME}.app"
DMG="$DIST/${APP_NAME}-${VERSION}-macOS.dmg"

if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP does not exist. Run python build_installer.py first."
  exit 1
fi

# Ensure embedded helper binaries are executable before signing.
find "$APP/Contents" -type f \( -name ffmpeg -o -name ffprobe -o -name prs_worker -o -name radio_tv_story_segmenter_worker.py \) -exec chmod 755 {} \;
if [[ -d "$APP/Contents/MacOS" ]]; then
  chmod +x "$APP/Contents/MacOS/$APP_NAME" || true
fi

if [[ -n "${DEVELOPER_ID_APPLICATION:-}" ]]; then
  echo "Signing $APP with Developer ID"
  codesign --force --deep --options runtime --timestamp \
    --sign "$DEVELOPER_ID_APPLICATION" "$APP"
  codesign --verify --deep --strict --verbose=2 "$APP"
else
  echo "DEVELOPER_ID_APPLICATION is not set; applying ad-hoc code signature (-s -)."
  codesign --force --deep -s - "$APP" || true
fi

rm -f "$DMG"
hdiutil create -volname "Radio & TV Segmenter $VERSION" \
  -srcfolder "$APP" -ov -format UDZO "$DMG"

echo "Created: $DMG"

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  echo "Submitting DMG for notarization using profile $NOTARY_PROFILE"
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG" || true
  xcrun stapler validate "$DMG" || true
fi
