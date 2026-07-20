#!/usr/bin/env bash
# Regenerate the README diagram PNGs from their SVG sources.
#
# The SVGs are the source of truth; edit those, then run this. The README
# embeds the PNGs because GitHub and most markdown previewers refuse to render
# a linked SVG (sanitizer policy), which leaves a broken image icon.
#
# The README links these by absolute raw.githubusercontent.com URL, not by
# relative path: GitHub only rewrites a relative image path when the renderer
# knows the repo root, so previewers outside the repo page show it broken.
# After renaming the repo or its default branch, update those two URLs.
#
# No rsvg-convert/ImageMagick dependency: headless Chrome is already required
# for the design doc PDF, so it renders these too. 2x device scale keeps the
# 10px labels legible.
set -euo pipefail

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

render() {
  local name=$1 w=$2 h=$3
  printf '<style>html,body{margin:0;padding:0;background:#fff}img{display:block;width:%spx;height:%spx}</style><img src="file://%s/%s.svg">' \
    "$w" "$h" "$DIR" "$name" > "$TMP/$name.html"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=2 --virtual-time-budget=3000 \
    --window-size="$w,$h" --screenshot="$DIR/$name.png" \
    "file://$TMP/$name.html" 2>/dev/null
  echo "rendered $name.png (${w}x${h} @2x)"
}

# width/height must match each SVG's viewBox
render approach_a_vanilla_rag 980 700
render approach_b_agent 980 760
