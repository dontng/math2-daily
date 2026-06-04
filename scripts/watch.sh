#!/usr/bin/env bash
# Watch pictures/ for new images, auto-OCR + solve via Gemini.
# Usage: bash scripts/watch.sh
#
# Install once:
#   sudo apt install inotify-tools
#   pip install anthropic
#
# Set API key (one-time):
#   echo 'ANTHROPIC_API_KEY=your_key' >> /home/djology/math2-daily/.env

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PICTURES_DIR="$REPO_DIR/pictures"
DONE_DIR="$PICTURES_DIR/done"

mkdir -p "$PICTURES_DIR" "$DONE_DIR"

# load .env
[[ -f "$REPO_DIR/.env" ]] && set -a && source "$REPO_DIR/.env" && set +a

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ── check deps ────────────────────────────────────────────────────────────────

if ! command -v inotifywait &>/dev/null; then
    echo "Error: inotifywait not found"
    echo "  sudo apt install inotify-tools"
    exit 1
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "Error: ANTHROPIC_API_KEY not set"
    echo "  echo 'ANTHROPIC_API_KEY=your_key' >> $REPO_DIR/.env"
    exit 1
fi

# ── process one file ──────────────────────────────────────────────────────────

process() {
    local path="$1"
    local filename
    filename=$(basename "$path")

    # only image files
    case "${filename,,}" in
        *.jpg|*.jpeg|*.png|*.webp|*.heic|*.bmp|*.gif) ;;
        *) return 0 ;;
    esac

    log "← $filename"
    if ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" python3 "$REPO_DIR/scripts/solve.py" "$path"; then
        mv "$path" "$DONE_DIR/"
        log "✓ done → pictures/done/$filename"
    else
        log "✗ solve failed, leaving in pictures/"
    fi
}

# ── process any images already sitting in pictures/ on startup ───────────────

for f in "$PICTURES_DIR"/*.{jpg,jpeg,png,webp,heic,bmp,gif} 2>/dev/null; do
    [[ -f "$f" ]] && process "$f"
done

# ── watch loop ────────────────────────────────────────────────────────────────

log "watching  $PICTURES_DIR"
log "drop images here → auto-solve → problems/"
echo

inotifywait -m -e close_write -e moved_to \
    --format '%f' \
    "$PICTURES_DIR" 2>/dev/null |
while IFS= read -r filename; do
    path="$PICTURES_DIR/$filename"
    [[ -f "$path" ]] && process "$path"
done
