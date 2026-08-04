#!/usr/bin/env bash
# Build the Linux AppImage locally and report its final size.
# Run from the project root (same folder as build_app.py).

set -e

APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
GITHUB_LIMIT_BYTES=2147483648  # 2 GiB, GitHub Releases' hard per-file cap
ICON_PATH="${1:-}"             # optional: pass a path to a .png as the first arg

echo "== 1. Building PyInstaller bundle =="
python build_app.py

echo
echo "== 2. Bundle size breakdown (largest first) =="
du -sh dist/EfStrGenerator
du -sh dist/EfStrGenerator/* 2>/dev/null | sort -rh | head -20

echo
echo "== 3. Assembling AppDir =="
rm -rf AppDir
mkdir -p AppDir/usr/bin
mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps
cp -r dist/EfStrGenerator/* AppDir/usr/bin/

cat << 'EOF' > AppDir/AppRun
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/EfStrGenerator" "$@"
EOF
chmod +x AppDir/AppRun

cat << 'EOF' > AppDir/EfStrGenerator.desktop
[Desktop Entry]
Type=Application
Name=EfStrGenerator
Exec=EfStrGenerator
Icon=efstrgenerator
Categories=AudioVideo;AudioVideoEditing;
EOF

if [ -n "$ICON_PATH" ] && [ -f "$ICON_PATH" ]; then
    cp "$ICON_PATH" AppDir/efstrgenerator.png
else
    echo "  (no icon passed — leaving efstrgenerator.png unset; pass one as: $0 /path/to/icon.png)"
    convert -size 256x256 xc:blue AppDir/efstrgenerator.png || touch AppDir/efstrgenerator.png
fi

echo
echo "== 4. Fetching appimagetool (reused if already present) =="
if [ ! -f appimagetool ]; then
    wget -q "$APPIMAGETOOL_URL" -O appimagetool
    chmod +x appimagetool
fi

echo
echo "== 5. Building AppImage =="
OUTPUT="EfStrGenerator-x86_64.AppImage"
rm -f "$OUTPUT"
if ! ARCH=x86_64 ./appimagetool AppDir "$OUTPUT" 2>/tmp/appimagetool_err; then
    echo "  Direct run failed (likely missing FUSE) — retrying with APPIMAGE_EXTRACT_AND_RUN=1"
    cat /tmp/appimagetool_err
    APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 ./appimagetool AppDir "$OUTPUT"
fi

echo
echo "== 6. Final size =="
if [ -f "$OUTPUT" ]; then
    SIZE_BYTES=$(stat -c%s "$OUTPUT" 2>/dev/null || stat -f%z "$OUTPUT")
    ls -lh "$OUTPUT"
    echo "  $SIZE_BYTES bytes"
    if [ "$SIZE_BYTES" -gt "$GITHUB_LIMIT_BYTES" ]; then
        OVER=$(( (SIZE_BYTES - GITHUB_LIMIT_BYTES) / 1024 / 1024 ))
        echo "  ⚠️  Over GitHub's 2 GiB release limit by ~${OVER} MB"
    else
        MARGIN=$(( (GITHUB_LIMIT_BYTES - SIZE_BYTES) / 1024 / 1024 ))
        echo "  ✅ Under the 2 GiB limit, ~${MARGIN} MB to spare"
    fi
else
    echo "  ❌ $OUTPUT was not created — check the appimagetool output above"
    exit 1
fi
