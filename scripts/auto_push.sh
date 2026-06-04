#!/usr/bin/env bash
# Stop hook: commit all changes and push to GitHub after each session.

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

git add -A

if git diff --cached --quiet; then
    exit 0
fi

git commit -m "auto: $(date '+%Y/%m/%d %H:%M') session update"
git push
