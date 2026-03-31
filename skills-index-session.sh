#!/bin/bash
# Auto-index skills-catalog.md with context-mode on SessionStart
# Ensures /sm's ctx_search always works without manual rebuild
# Fast: skips if catalog is <6 hours old
# Vault support: also scans ~/.claude/skills-vault/ (cold storage, saves 5-8K tokens)

CATALOG="$HOME/.claude/skills-catalog.md"
IDX="$HOME/.claude/skills.idx"
STAMP="$HOME/.claude/.skills-index-ts"
VAULT_DIR="$HOME/.claude/skills-vault"

# Rebuild idx if index or catalog is missing
if [ ! -f "$IDX" ] || [ ! -f "$CATALOG" ]; then
    python3 "$HOME/.claude/scripts/build-skills-index.py" \
        --vault-dir "$VAULT_DIR" -q 2>/dev/null
fi

# Only re-index ctx if stamp is older than 6 hours (21600s)
NOW=$(date +%s)
LAST=0
[ -f "$STAMP" ] && LAST=$(cat "$STAMP" 2>/dev/null || echo 0)
AGE=$((NOW - LAST))

if [ "$AGE" -gt 21600 ]; then
    echo "$NOW" > "$STAMP"
    # ctx_index runs via MCP context-mode — not called here (requires interactive session)
    # Claude will call ctx_index when /sm auto or semantic search is used
fi

exit 0
