#!/usr/bin/env bash
# PreToolUse hook — intercepts WebFetch and scraping-like Bash commands,
# logs them, and nudges the agent to use hyperfetch instead.
#
# Input: JSON on stdin with tool_name and tool_input
# Output: JSON with {"decision":"block","reason":"..."} to block,
#         or exit 0 silently to allow
# Exit 0 to allow. Non-zero to hard-fail.

set +e

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("tool_name",""))' 2>/dev/null)

LOG=/tmp/claude-hyperstack-pretool.log
echo "[$(date +%H:%M:%S)] $TOOL_NAME" >> "$LOG" 2>/dev/null

case "$TOOL_NAME" in
  WebFetch)
    URL=$(echo "$INPUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("tool_input",{}).get("url",""))' 2>/dev/null)
    cat <<JSON
{
  "decision": "block",
  "reason": "WebFetch is disabled by the Hyperstack policy. Use the hyperfetch CLI instead:\n\n    hyperfetch '$URL' --team-ns <mission-name>\n\nOr delegate to the hyperstack-scraper subagent for bulk work. See ~/.claude/skills/hyperstack.md for the full guide. This saves 75x-10,000x tokens vs raw WebFetch."
}
JSON
    exit 0
    ;;
  Bash)
    CMD=$(echo "$INPUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("tool_input",{}).get("command",""))' 2>/dev/null)
    # Nudge patterns: raw curl/wget/playwright against a URL that isn't localhost
    if echo "$CMD" | grep -qE '^\s*(curl|wget)\s+(-[A-Za-z]+\s+)*https?://' && \
       ! echo "$CMD" | grep -qE '(localhost|127\.0\.0\.1|0\.0\.0\.0|::1|api\.anthropic|install\.(surrealdb|astral))'; then
      URL=$(echo "$CMD" | grep -oE 'https?://[^ \x27"]+' | head -1)
      cat <<JSON
{
  "decision": "block",
  "reason": "Raw curl/wget against external URLs is disabled by Hyperstack. Use:\n\n    hyperfetch '$URL' --team-ns <mission>\n\nThis goes through the 4-stage escalation (curl_cffi → camoufox → domshell → browser) with team cache + gemma summarization. If you genuinely need raw curl (e.g., a POST with custom body), prefix your command with HYPERSTACK_BYPASS=1 to override."
}
JSON
      exit 0
    fi
    # Playwright/puppeteer direct use — match only as executed command, not string arg
    if echo "$CMD" | grep -qE '(^|[;&|]|\bnpx[[:space:]]+|\buv[[:space:]]+run[[:space:]]+)(playwright|puppeteer|chrome-devtools-mcp)([[:space:]]|$)' && \
       ! echo "$CMD" | grep -qE 'HYPERSTACK_BYPASS=1'; then
      cat <<JSON
{
  "decision": "block",
  "reason": "Playwright/Puppeteer direct use is disabled. Use 'dsh' (DOMShell REPL) instead:\n\n    dsh --session <name> goto <url>\n    dsh --session <name> read <selector>\n\ndsh is stateful, JSON-only, and uses your patched camoufox + domshell-lite underneath. See ~/.claude/skills/hyperstack.md."
}
JSON
      exit 0
    fi
    ;;
esac

exit 0
