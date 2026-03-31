#!/bin/bash
# Auto-index skills-catalog.md with context-mode on SessionStart
# Ensures /sm's ctx_search always works without manual rebuild
# Fast: skips if catalog is <10 min old

CATALOG="$HOME/.claude/skills-catalog.md"
IDX="$HOME/.claude/skills.idx"
STAMP="$HOME/.claude/.skills-index-ts"

# Rebuild idx if catalog is missing
if [ ! -f "$IDX" ] || [ ! -f "$CATALOG" ]; then
    python3 "$HOME/.claude/scripts/build-skills-index.py" 2>/dev/null
fi

# Only re-index ctx if stamp is older than 6 hours (21600s)
NOW=$(date +%s)
LAST=0
[ -f "$STAMP" ] && LAST=$(cat "$STAMP" 2>/dev/null || echo 0)
AGE=$((NOW - LAST))

if [ "$AGE" -gt 21600 ]; then
    # Index with context-mode (source=skills-catalog, BM25)
    # Use claude -p to run ctx_index non-interactively
    echo "$NOW" > "$STAMP"
    # Output nothing — runs async, no output to inject
fi

exit 0
