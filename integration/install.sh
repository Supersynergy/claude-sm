#!/usr/bin/env bash
# Hyperstack Claude Code integration installer.
# Drop-in for Claude Code v2.1.x harness. Safe to re-run.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CLAUDE="$HOME/.claude"
CTS_BIN="$HOME/.cts/bin"

echo "==> Hyperstack Claude Code integration installer"

mkdir -p "$CLAUDE"/{agents,hooks,skills,teams/hyperstack} "$CTS_BIN"

echo "==> Installing skill"
cp "$ROOT/skills/hyperstack.md" "$CLAUDE/skills/hyperstack.md"

echo "==> Installing subagents"
for a in scraper researcher heavy; do
  cp "$ROOT/agents/hyperstack-$a.md" "$CLAUDE/agents/hyperstack-$a.md"
done

echo "==> Installing hooks"
cp "$ROOT/hooks/hyperstack-pretool.sh" "$CLAUDE/hooks/hyperstack-pretool.sh"
cp "$ROOT/hooks/hyperstack-postcompact.sh" "$CLAUDE/hooks/hyperstack-postcompact.sh"
chmod +x "$CLAUDE/hooks/hyperstack-pretool.sh" "$CLAUDE/hooks/hyperstack-postcompact.sh"

echo "==> Installing team config"
cp "$ROOT/teams/hyperstack/config.json" "$CLAUDE/teams/hyperstack/config.json"

echo "==> Installing loop mode"
cp "$ROOT/loop-hyperstack.md" "$CLAUDE/loop-hyperstack.md"

echo "==> Installing hyperfetch CLI"
cp "$ROOT/cli/hyperfetch" "$CTS_BIN/hyperfetch"
chmod +x "$CTS_BIN/hyperfetch"

echo ""
echo "==> Manual step: wire settings.json"
echo ""
echo "Add to $CLAUDE/settings.json under hooks:"
cat <<'JSON'

"PreToolUse": [
  {
    "matcher": "WebFetch|Bash",
    "hooks": [{
      "type": "command",
      "command": "bash \"/Users/YOUR_USER/.claude/hooks/hyperstack-pretool.sh\""
    }]
  }
],
"PostCompact": [
  {
    "hooks": [{
      "type": "command",
      "command": "bash \"/Users/YOUR_USER/.claude/hooks/hyperstack-postcompact.sh\"",
      "async": true
    }]
  }
]

JSON

echo "==> Manual step: PATH"
echo '  echo "export PATH=\"\$HOME/.cts/bin:\$PATH\"" >> ~/.zshrc'
echo ""
echo "==> Manual step: Agent Teams env"
echo '  export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1'
echo ""
echo "==> Done. Restart Claude Code to pick up hooks."
echo ""
echo "Test:"
echo "  curl https://example.com      # should be blocked by hook"
echo "  hyperfetch https://example.com # should work"
