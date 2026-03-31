#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║  claude-token-saver (cts) — Universal Fail-Safe Installer       ║
# ║  4–5M tokens/month saved. One command: /sm init                 ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Supersynergy/claude-sm/main/install.sh | bash
#   bash install.sh                    # interactive (default)
#   bash install.sh --dry-run          # preview only, no changes
#   bash install.sh --silent           # no prompts, safe defaults
#   bash install.sh --upgrade          # upgrade existing install
#   bash install.sh --no-vault         # skip zero-startup vault setup
#   bash install.sh --no-shellfirm     # skip shellfirm install
#   bash install.sh --skills-dir PATH  # custom skills dir
#   bash install.sh --vault-dir PATH   # custom vault dir

set -euo pipefail

# ── Parse arguments ───────────────────────────────────────────────────────────
DRY_RUN=false
SILENT=false
UPGRADE=false
NO_VAULT=false
NO_SHELLFIRM=false
CUSTOM_SKILLS_DIR=""
CUSTOM_VAULT_DIR=""

for arg in "$@"; do
  case "$arg" in
    --dry-run)       DRY_RUN=true ;;
    --silent)        SILENT=true ;;
    --upgrade)       UPGRADE=true ;;
    --no-vault)      NO_VAULT=true ;;
    --no-shellfirm)  NO_SHELLFIRM=true ;;
    --skills-dir=*)  CUSTOM_SKILLS_DIR="${arg#*=}" ;;
    --vault-dir=*)   CUSTOM_VAULT_DIR="${arg#*=}" ;;
    --help|-h)
      grep '^#' "$0" | head -15 | sed 's/^# \?//'
      exit 0 ;;
  esac
done

# ── Colors & helpers ──────────────────────────────────────────────────────────
if [ -t 1 ]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
  BOLD='\033[1m'; DIM='\033[2m'; RED='\033[0;31m'; RESET='\033[0m'
else
  GREEN=''; YELLOW=''; CYAN=''; BOLD=''; DIM=''; RED=''; RESET=''
fi

ok()    { echo -e "${GREEN}✓${RESET} $1"; }
info()  { echo -e "${CYAN}→${RESET} $1"; }
warn()  { echo -e "${YELLOW}⚠${RESET}  $1"; }
err()   { echo -e "${RED}✗${RESET} $1" >&2; }
head()  { echo -e "\n${BOLD}$1${RESET}"; }
dim()   { echo -e "${DIM}  $1${RESET}"; }
dryrun(){ $DRY_RUN && echo -e "${YELLOW}[dry-run]${RESET} $1"; }

ask() {
  # ask <prompt> <default Y|N>
  # Returns 0 (yes) or 1 (no). In silent mode: uses default.
  local prompt="$1" default="${2:-Y}"
  if $SILENT || $DRY_RUN; then
    [[ "$default" == "Y" ]] && return 0 || return 1
  fi
  local yn
  if [[ "$default" == "Y" ]]; then
    printf "%s [Y/n] " "$prompt"
  else
    printf "%s [y/N] " "$prompt"
  fi
  read -r yn </dev/tty
  case "${yn:-$default}" in
    [Yy]*) return 0 ;;
    *)     return 1 ;;
  esac
}

safe_run() {
  # Run command only if not dry-run
  if $DRY_RUN; then
    dryrun "would run: $*"
  else
    "$@"
  fi
}

# ── Detect environment ────────────────────────────────────────────────────────
detect_os() {
  if [[ "$(uname)" == "Darwin" ]]; then echo "macos"
  elif grep -qi microsoft /proc/version 2>/dev/null; then echo "wsl"
  elif [[ "$(uname)" == "Linux" ]]; then echo "linux"
  else echo "unknown"
  fi
}

detect_pkg_manager() {
  command -v brew &>/dev/null && echo "brew" && return
  command -v apt-get &>/dev/null && echo "apt" && return
  command -v dnf &>/dev/null && echo "dnf" && return
  command -v pacman &>/dev/null && echo "pacman" && return
  echo "none"
}

OS=$(detect_os)
PKG=$(detect_pkg_manager)
REPO_RAW="https://raw.githubusercontent.com/Supersynergy/claude-sm/main"

# ── Locate Claude config dir ──────────────────────────────────────────────────
find_claude_dir() {
  # Respect env override
  [ -n "${CLAUDE_DIR:-}" ] && { echo "$CLAUDE_DIR"; return; }
  # Standard locations
  for d in "$HOME/.claude" "$HOME/Library/Application Support/Claude" "$HOME/.config/claude"; do
    [ -d "$d" ] && { echo "$d"; return; }
  done
  # Default to ~/.claude (will be created)
  echo "$HOME/.claude"
}

CLAUDE_DIR=$(find_claude_dir)
SKILLS_DIR="${CUSTOM_SKILLS_DIR:-$CLAUDE_DIR/skills}"
VAULT_DIR="${CUSTOM_VAULT_DIR:-$CLAUDE_DIR/skills-vault}"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
HOOKS_DIR="$CLAUDE_DIR/hooks"
SETTINGS="$CLAUDE_DIR/settings.json"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
head "Pre-flight checks"

# Check Python 3
if ! command -v python3 &>/dev/null; then
  err "python3 not found — required for index builder"
  err "Install: brew install python3 (macOS) or apt install python3 (Linux)"
  exit 1
fi
ok "Python 3: $(python3 --version 2>&1 | awk '{print $2}')"

# Check ripgrep
if ! command -v rg &>/dev/null; then
  warn "ripgrep (rg) not found — grep fallback used (slower)"
  case "$PKG" in
    brew)   info "Install: brew install ripgrep" ;;
    apt)    info "Install: sudo apt install ripgrep" ;;
    dnf)    info "Install: sudo dnf install ripgrep" ;;
    pacman) info "Install: sudo pacman -S ripgrep" ;;
  esac
else
  ok "ripgrep: $(rg --version | head -1 | awk '{print $2}')"
fi

# Check Claude Code directory
if [ ! -d "$CLAUDE_DIR" ]; then
  warn "~/.claude not found — will create"
fi
ok "Claude dir: $CLAUDE_DIR"

# Detect existing CTS install
CTS_INSTALLED=false
[ -f "$SKILLS_DIR/sm.md" ] && CTS_INSTALLED=true
if $CTS_INSTALLED; then
  existing_ver=$(grep -m1 "^version:" "$SKILLS_DIR/sm.md" 2>/dev/null | awk '{print $2}')
  ok "Existing install detected${existing_ver:+ (v$existing_ver)}"
else
  ok "Fresh install"
fi

# ── Backup existing configs ───────────────────────────────────────────────────
BACKUP_DIR=""
if $CTS_INSTALLED && ! $UPGRADE; then
  head "Backup"
  BACKUP_DIR="$CLAUDE_DIR/backups/cts-$(date +%Y%m%d-%H%M%S)"
  safe_run mkdir -p "$BACKUP_DIR"
  [ -f "$SKILLS_DIR/sm.md" ]               && safe_run cp "$SKILLS_DIR/sm.md" "$BACKUP_DIR/"
  [ -f "$SCRIPTS_DIR/build-skills-index.py" ] && safe_run cp "$SCRIPTS_DIR/build-skills-index.py" "$BACKUP_DIR/"
  [ -f "$HOOKS_DIR/skills-index-session.sh" ] && safe_run cp "$HOOKS_DIR/skills-index-session.sh" "$BACKUP_DIR/"
  [ -f "$SETTINGS" ]                        && safe_run cp "$SETTINGS" "$BACKUP_DIR/settings.json"
  ok "Backed up to: $BACKUP_DIR"
fi

# ── Create directories ────────────────────────────────────────────────────────
head "Setup directories"
safe_run mkdir -p "$SKILLS_DIR" "$VAULT_DIR" "$SCRIPTS_DIR" "$HOOKS_DIR" "$CLAUDE_DIR/cache"
ok "Directories ready"

# ── Download or copy files ────────────────────────────────────────────────────
install_file() {
  local src="$1" dst="$2" label="$3"
  if $DRY_RUN; then
    dryrun "would install: $label → $dst"
    return
  fi
  # Try local first (running from repo clone), then fetch
  if [ -f "$src" ]; then
    cp "$src" "$dst"
  elif [ -f "$(dirname "$0")/$src" ]; then
    cp "$(dirname "$0")/$src" "$dst"
  else
    if ! curl -fsSL "$REPO_RAW/$src" -o "$dst" 2>/dev/null; then
      err "Failed to fetch: $src"
      return 1
    fi
  fi
  ok "$label"
}

head "Installing core files"
install_file "sm.md"                    "$SKILLS_DIR/sm.md"                   "/sm skill → $SKILLS_DIR/sm.md"
install_file "build-skills-index.py"   "$SCRIPTS_DIR/build-skills-index.py"  "Index builder → $SCRIPTS_DIR/"
install_file "skills-index-session.sh" "$HOOKS_DIR/skills-index-session.sh"  "Session hook → $HOOKS_DIR/"
install_file "hud-savings.sh"          "$HOOKS_DIR/cts-cache-refresh.sh"     "CTS cache refresh → $HOOKS_DIR/"

if ! $DRY_RUN; then
  chmod +x "$HOOKS_DIR/skills-index-session.sh" "$HOOKS_DIR/cts-cache-refresh.sh" \
           "$SCRIPTS_DIR/build-skills-index.py" 2>/dev/null || true
fi

# ── Merge settings.json (never overwrite, surgical additions only) ─────────────
head "Wiring hooks (merge-safe)"
if $DRY_RUN; then
  dryrun "would merge SessionStart + PostToolUse hooks into settings.json"
else
python3 - <<PYEOF
import json, os, sys

path = os.path.expanduser("${SETTINGS}")

# Initialize settings.json if missing
if not os.path.exists(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump({}, f, indent=2)
    print("  Created settings.json")

try:
    with open(path) as f:
        s = json.load(f)
except (json.JSONDecodeError, IOError) as e:
    print(f"  Warning: Could not read settings.json ({e}), skipping hook wiring")
    sys.exit(0)

hooks = s.setdefault("hooks", {})
changed = False

# SessionStart — skills index rebuild
ss = hooks.setdefault("SessionStart", [])
session_hook = {"async": True, "command": 'bash "$HOME/.claude/hooks/skills-index-session.sh"', "type": "command"}
if not any("skills-index-session" in str(h) for h in ss):
    ss.append({"hooks": [session_hook]})
    print("  + SessionStart: skills-index-session.sh")
    changed = True
else:
    print("  ✓ SessionStart hook already present")

# PostToolUse — CTS cache refresh (async, non-blocking)
pt = hooks.setdefault("PostToolUse", [])
if not any("cts-cache-refresh" in str(h) for h in pt):
    pt.append({
        "description": "CTS token savings cache refresh (async)",
        "hooks": [{"async": True, "command": 'bash "$HOME/.claude/hooks/cts-cache-refresh.sh"', "timeout": 10, "type": "command"}],
        "matcher": "Bash"
    })
    print("  + PostToolUse: cts-cache-refresh.sh (async)")
    changed = True
else:
    print("  ✓ PostToolUse cache hook already present")

if changed:
    # Write with backup
    import shutil
    backup = path + ".cts-backup"
    shutil.copy2(path, backup)
    with open(path, "w") as f:
        json.dump(s, f, indent=2)
    print(f"  Saved (backup: {backup})")
PYEOF
fi

# ── Build initial index ────────────────────────────────────────────────────────
head "Building skills index"
if $DRY_RUN; then
  dryrun "would run: python3 build-skills-index.py --skills-dir $SKILLS_DIR --vault-dir $VAULT_DIR"
else
  if python3 "$SCRIPTS_DIR/build-skills-index.py" \
      --skills-dir "$SKILLS_DIR" \
      --vault-dir "$VAULT_DIR" \
      --output-dir "$CLAUDE_DIR" -q 2>/dev/null; then
    IDX="$CLAUDE_DIR/skills.idx"
    TOTAL=$(wc -l < "$IDX" 2>/dev/null | tr -d ' ')
    HOT=$(awk -F'\t' '$5=="0"' "$IDX" 2>/dev/null | wc -l | tr -d ' ')
    VCNT=$(awk -F'\t' '$5=="1"' "$IDX" 2>/dev/null | wc -l | tr -d ' ')
    ok "Indexed: $TOTAL skills ($HOT hot + $VCNT vault)"
    STARTUP_SAVED=$(( VCNT * 40 ))
    dim "Startup savings: ~${STARTUP_SAVED} tokens/session from vault"
  else
    warn "Index build failed — run manually later: python3 $SCRIPTS_DIR/build-skills-index.py"
  fi
fi

# ── Zero-startup vault setup (optional) ───────────────────────────────────────
if ! $NO_VAULT && ! $DRY_RUN; then
  HOT_NON_SM=$(find "$SKILLS_DIR" -maxdepth 1 \( -name "*.md" -o -type d \) ! -name "sm.md" ! -path "$SKILLS_DIR" 2>/dev/null | wc -l | tr -d ' ')

  if [ "${HOT_NON_SM:-0}" -gt 0 ]; then
    head "Zero-startup setup"
    info "Found $HOT_NON_SM skills in hot dir (excluding sm.md)"
    info "Moving them to vault saves ~$(( HOT_NON_SM * 40 )) startup tokens/session"

    if ask "  Move all skills to vault? (sm.md stays hot)" Y; then
      moved=0
      while IFS= read -r -d '' item; do
        name=$(basename "$item")
        [ "$name" = "sm.md" ] && continue
        mv "$item" "$VAULT_DIR/" 2>/dev/null && (( moved++ )) || true
      done < <(find "$SKILLS_DIR" -maxdepth 1 \( -name "*.md" -o -type d \) ! -path "$SKILLS_DIR" -print0 2>/dev/null)

      python3 "$SCRIPTS_DIR/build-skills-index.py" \
        --skills-dir "$SKILLS_DIR" --vault-dir "$VAULT_DIR" \
        --output-dir "$CLAUDE_DIR" -q 2>/dev/null

      ok "Moved $moved skills to vault — zero startup!"
    else
      info "Skipped. Run /sm vault <name> to move skills manually."
    fi
  else
    ok "Already zero-startup (only sm.md in hot dir)"
  fi
fi

# ── Optional: RTK ─────────────────────────────────────────────────────────────
head "Token Layer 1: RTK (Bash compression 60-90%)"
if command -v rtk &>/dev/null; then
  VER=$(rtk --version 2>/dev/null | head -1)
  ok "RTK installed: $VER"
  # Verify hook is wired
  if rtk verify &>/dev/null 2>&1; then
    ok "RTK hook: active (auto-compresses all Bash)"
  else
    warn "RTK hook may need refresh: rtk init -g"
  fi
else
  warn "RTK not installed — saves 60-90% on every Bash call"
  case "$PKG" in
    brew)
      if ask "  Install RTK via brew?" Y; then
        safe_run brew install rtk-ai/tap/rtk && safe_run rtk init -g
        ok "RTK installed and hook wired"
      else
        dim "Manual: brew install rtk-ai/tap/rtk && rtk init -g"
      fi
      ;;
    *)
      dim "Manual: see https://rtk-ai.app for Linux install"
      ;;
  esac
fi

# ── Optional: shellfirm ───────────────────────────────────────────────────────
if ! $NO_SHELLFIRM; then
  head "Safety Layer: shellfirm (AI agent guardrails)"
  if command -v shellfirm &>/dev/null; then
    SF_VER=$(shellfirm --version 2>/dev/null | head -1)
    ok "shellfirm: $SF_VER"
    if ! grep -q "shellfirm" "$SETTINGS" 2>/dev/null; then
      info "Connecting to Claude Code..."
      safe_run shellfirm connect claude-code && ok "shellfirm connected (PreToolUse + MCP)"
    else
      ok "shellfirm already connected"
    fi
  else
    warn "shellfirm not installed — protects against rm -rf, force-push, etc."
    dim "\"Humans make mistakes. AI agents make them faster.\""
    case "$PKG" in
      brew)
        if ask "  Install shellfirm via brew?" Y; then
          safe_run brew tap kaplanelad/tap
          safe_run brew install shellfirm
          safe_run shellfirm connect claude-code
          ok "shellfirm installed and connected"
        else
          dim "Manual: brew tap kaplanelad/tap && brew install shellfirm && shellfirm connect claude-code"
        fi
        ;;
      *)
        if command -v cargo &>/dev/null && ask "  Install shellfirm via cargo?" Y; then
          safe_run cargo install shellfirm
          safe_run shellfirm connect claude-code
          ok "shellfirm installed via cargo"
        else
          dim "Manual: cargo install shellfirm OR npm install -g @shellfirm/cli"
        fi
        ;;
    esac
  fi
fi

# ── context-mode check ────────────────────────────────────────────────────────
head "Token Layer 2: context-mode (ctx_batch_execute, 90% savings)"
if grep -q "context-mode\|ctx_batch_execute" "$SETTINGS" 2>/dev/null || \
   find "${HOME}/.npm/_npx" -name "context-mode" 2>/dev/null | grep -q .; then
  ok "context-mode: active"
  dim "Use ctx_batch_execute for 2+ Bash calls (90% savings)"
elif command -v npx &>/dev/null; then
  ok "context-mode: available via npx"
  dim "Or install globally: npm install -g context-mode"
else
  warn "context-mode not detected"
  dim "Install: npm install -g context-mode"
  dim "Or via ECC: https://github.com/Supersynergy/everything-claude-code"
fi

# ── HUD check ─────────────────────────────────────────────────────────────────
head "HUD: claude-hud + savings panel"
HUD_SH="$HOOKS_DIR/claude-hud.sh"
if [ -f "$HUD_SH" ]; then
  ok "claude-hud.sh: present"
  ok "hud-extra.sh: savings panel active (⚡RTK|ctx%|V:n|sf)"
  dim "HUD shows: context bar + 5h/7d usage windows + savings label"
else
  warn "claude-hud.sh not found"
  dim "Install via ECC or: https://github.com/jarrodwatts/claude-hud"
fi

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════════════${RESET}"
if $DRY_RUN; then
  echo -e "${YELLOW}DRY RUN complete — no changes made${RESET}"
else
  ok "claude-token-saver installed!"
fi
echo ""
echo -e "${BOLD}Run in Claude Code:${RESET}"
echo "  /sm init              — activate all layers, see savings dashboard"
echo ""
echo -e "${BOLD}Key commands:${RESET}"
echo "  /sm search <query>    — find skills  (~0 tokens)"
echo "  /sm auto <intent>     — find + invoke best skill"
echo "  /sm load <name>       — load from vault on demand"
echo "  /sm vault <name>      — move to cold storage"
echo "  /sm stats             — savings report"
echo "  /sm tokens            — full cheatsheet"
echo ""
echo -e "${BOLD}Stack summary:${RESET}"
echo "  Vault (~0)  RTK (60-90%)  ctx-mode (90%)  shellfirm (safety)"
echo "  Combined: 4–5M tokens/month saved"
echo ""
if [ -n "$BACKUP_DIR" ]; then
  dim "Backup saved: $BACKUP_DIR"
fi
