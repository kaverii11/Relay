#!/bin/sh
# Build the Drive folder (K, 2026-11-11 §52 item 11). Re-run after every change; it rebuilds from scratch.
#   sh scripts/package.sh [OUT]        default OUT = ~/Relay_submission
# In:  code, results.csv, raw/ (with probe/raw/), the write-up, DECISIONS.md, README, and a conversations/ slot
#      for TWO exports (this Claude Code session, K's claude.ai chat; the Gemini chat was temporary, not exportable).
# Out: .env, the key, .venv, .git, caches, data/ (chunk files, rebuilt on first run), papers/ (fetched by
#      library/fetch_papers.py at the pinned versions).
set -e
cd "$(dirname "$0")/.."
OUT="${1:-$HOME/Relay_submission}"
rm -rf "$OUT"
mkdir -p "$OUT/conversations"
.venv/bin/python scripts/redact_org.py
rsync -a --exclude='.env' --exclude='.env.*' --exclude='.venv/' --exclude='.git/' --exclude='__pycache__/' \
      --exclude='*.pyc' --exclude='.DS_Store' --exclude='data/' --exclude='papers/' --exclude='conversations/' \
      --exclude='raw/_verify_*' \
      relay standin load eval analysis probe scripts library writeup raw requirements.txt README.md DECISIONS.md \
      results.csv "$OUT/"
# the exports live in ~/Relay/conversations/ (gitignored, never pushed) and are copied in on every build
if [ -d conversations ]; then rsync -a --exclude='.DS_Store' conversations/ "$OUT/conversations/"; fi
[ -f "$OUT/conversations/README.md" ] || cat > "$OUT/conversations/README.md" <<'EOF'
# Conversation history (the brief: "your real conversation history with it, not a cleaned-up one")

Put the two exports here, unedited:

1. `claude_code_session.*`: this Claude Code session (the one that built and ran everything).
2. `claude_ai_chat.*`: Kaveri's claude.ai chat (the second assistant that reviewed plans and results).

Not attached: Gemini (used only to tidy the English of text Kaveri wrote) ran in a temporary chat, which is not
saved and cannot be exported.
EOF
echo "built $OUT"
find "$OUT" -type f | wc -l | xargs echo "files:"
du -sh "$OUT" | cut -f1 | xargs echo "size:"
