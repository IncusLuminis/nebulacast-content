#!/usr/bin/env zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_NAME="media-nebulacast"
MEDIA_DIR="$ROOT/media"

if ! command -v wrangler >/dev/null 2>&1; then
  print -u2 "wrangler is required (v4+). Install it with: npm install -D wrangler@latest"
  exit 1
fi

python3 "$ROOT/tools/build_media_index.py" --media-dir "$MEDIA_DIR" --validate-pages

wrangler pages deploy "$MEDIA_DIR" \
  --project-name "$PROJECT_NAME" \
  --branch main \
  --commit-dirty=true
