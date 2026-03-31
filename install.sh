#!/bin/bash
# Install claude-sm — Skill Manager for Claude Code
# Usage: curl -fsSL https://raw.githubusercontent.com/Supersynergy/claude-sm/main/install.sh | bash

set -e

SKILLS_DIR="$HOME/.claude/skills"
SCRIPTS_DIR="$HOME/.claude/scripts"
HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"

echo "=== claude-sm installer ==="
echo ""

# Create dirs
mkdir -p "$SKILLS_DIR" "$SCRIPTS_DIR" "$HOOKS_DIR"

# Copy files
REPO="https://raw.githubusercontent.com/Supersynergy/claude-sm/main"

echo "Installing /sm skill..."
curl -fsSL "$REPO/sm.md" -o "$SKILLS_DIR/sm.md"

echo "Installing build script..."
curl -fsSL "$REPO/build-skills-index.py" -o "$SCRIPTS_DIR/build-skills-index.py"
chmod +x "$SCRIPTS_DIR/build-skills-index.py"

echo "Installing session hook..."
curl -fsSL "$REPO/skills-index-session.sh" -o "$HOOKS_DIR/skills-index-session.sh"
chmod +x "$HOOKS_DIR/skills-index-session.sh"

# Add SessionStart hook to settings.json
if [ -f "$SETTINGS" ]; then
    python3 - <<'PYEOF'
import json, os

settings_path = os.path.expanduser("~/.claude/settings.json")
with open(settings_path) as f:
    s = json.load(f)

hook_cmd = 'bash "$HOME/.claude/hooks/skills-index-session.sh"'
new_hook = {"hooks": [{"async": True, "command": hook_cmd, "type": "command"}]}

hooks = s.setdefault("hooks", {})
session_start = hooks.setdefault("SessionStart", [])

already = any("skills-index-session" in str(h) for h in session_start)
if not already:
    session_start.append(new_hook)
    with open(settings_path, "w") as f:
        json.dump(s, f, indent=2)
    print("SessionStart hook added to settings.json")
else:
    print("SessionStart hook already present, skipping")
PYEOF
fi

# Build initial index
echo ""
echo "Building skills index..."
python3 "$SCRIPTS_DIR/build-skills-index.py"

echo ""
echo "✓ Done! Use /sm to discover skills:"
echo "  /sm search <query>   — find skills by keyword"
echo "  /sm list             — browse by category"
echo "  /sm auto <intent>    — find + invoke best match"
echo "  /sm rebuild          — refresh index after adding skills"
