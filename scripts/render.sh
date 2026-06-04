#!/usr/bin/env bash
# Render problems markdown to compact A4 PDF for printing.
# Usage: bash scripts/render.sh [FILE.md]
#        bash scripts/render.sh          # uses today's file
#
# Install deps (once):
#   sudo apt install pandoc texlive-xetex texlive-latex-extra texlive-science

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROBLEMS_DIR="$REPO_DIR/problems"

# ── resolve source file ───────────────────────────────────────────────────────

if [[ -n "${1:-}" ]]; then
    src="$(realpath "$1")"
else
    mmdd=$(date '+%m%d')
    src=$(find "$PROBLEMS_DIR" -name "${mmdd}-day*.md" 2>/dev/null | head -1)
    if [[ -z "$src" ]]; then
        echo "No problems file found for today ($mmdd). Run solve.py first." >&2
        exit 1
    fi
fi

out="${src%.md}.pdf"
echo "→ $(realpath --relative-to="$REPO_DIR" "$out")"

# ── check deps ────────────────────────────────────────────────────────────────

for cmd in pandoc xelatex; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: $cmd not found"
        echo "  sudo apt install pandoc texlive-xetex texlive-latex-extra texlive-science"
        exit 1
    fi
done

# ── render ────────────────────────────────────────────────────────────────────

pandoc "$src" \
    -o "$out" \
    --pdf-engine=xelatex \
    --variable=geometry:"top=1.5cm, bottom=1.5cm, left=2cm, right=2cm" \
    --variable=fontsize:10pt \
    --variable=linestretch:1.1 \
    --variable=CJKmainfont:"WenQuanYi Zen Hei" \
    --variable=mainfont:"DejaVu Serif" \
    --variable=mathfont:"TeX Gyre Termes Math" \
    --variable=colorlinks:true \
    --highlight-style=tango

echo "done: $out"
