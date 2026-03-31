#!/bin/bash
# CTS Cache Refresh — keeps HUD savings data fresh
# Installed to: ~/.claude/hooks/cts-cache-refresh.sh
# Wired as: async PostToolUse hook (matcher: Bash)
#
# Writes cache files read by hud-extra.sh every 300ms:
#   ~/.claude/cache/ctx-pct.txt    — context-mode reduction %
#   ~/.claude/cache/rtk-summary.txt — RTK session summary
#   ~/.claude/cache/vault-count.txt — vault skill count

CTS_DIR="${HOME}/.claude/cache"
mkdir -p "$CTS_DIR" 2>/dev/null

# ── ctx-mode reduction % (refreshed every 60s) ────────────────────────────────
CTX_CACHE="$CTS_DIR/ctx-pct.txt"
CTX_MAX_AGE=60
_ctx_stale=true
if [ -f "$CTX_CACHE" ]; then
  age=$(( $(date +%s) - $(stat -f %m "$CTX_CACHE" 2>/dev/null || stat -c %Y "$CTX_CACHE" 2>/dev/null || echo 0) ))
  [ "$age" -lt "$CTX_MAX_AGE" ] && _ctx_stale=false
fi

if $_ctx_stale; then
  pct=""
  # Check raw stats file (written by /sm init via ctx_stats)
  if [ -f "$CTS_DIR/ctx-stats-raw.txt" ]; then
    pct=$(grep -iE "compression|reduction|saved|percent" "$CTS_DIR/ctx-stats-raw.txt" 2>/dev/null \
          | grep -oE '[0-9]+(\.[0-9]+)?' | head -1)
  fi
  # Fallback: context-mode installed = 83% baseline (documented average)
  if [ -z "$pct" ]; then
    _cm_active=false
    grep -q "context-mode" "${HOME}/.claude/settings.json" 2>/dev/null && _cm_active=true
    find "${HOME}/.npm/_npx" -name "context-mode" 2>/dev/null | grep -q . && _cm_active=true
    $_cm_active && pct="83"
  fi
  [ -n "$pct" ] && printf '%s' "$pct" > "$CTX_CACHE"
fi

# ── vault count (fast awk, refresh every 120s) ────────────────────────────────
VC_CACHE="$CTS_DIR/vault-count.txt"
VC_MAX_AGE=120
_vc_stale=true
if [ -f "$VC_CACHE" ]; then
  age=$(( $(date +%s) - $(stat -f %m "$VC_CACHE" 2>/dev/null || stat -c %Y "$VC_CACHE" 2>/dev/null || echo 0) ))
  [ "$age" -lt "$VC_MAX_AGE" ] && _vc_stale=false
fi
if $_vc_stale; then
  IDX="${HOME}/.claude/skills.idx"
  if [ -f "$IDX" ]; then
    v=$(awk -F'\t' '$5=="1"' "$IDX" 2>/dev/null | wc -l | tr -d ' ')
    printf '%s' "${v:-0}" > "$VC_CACHE"
  fi
fi

# ── RTK summary (parsed from rtk gain, refresh every 120s) ───────────────────
RTK_CACHE="$CTS_DIR/rtk-summary.txt"
RTK_MAX_AGE=120
_rtk_stale=true
if [ -f "$RTK_CACHE" ]; then
  age=$(( $(date +%s) - $(stat -f %m "$RTK_CACHE" 2>/dev/null || stat -c %Y "$RTK_CACHE" 2>/dev/null || echo 0) ))
  [ "$age" -lt "$RTK_MAX_AGE" ] && _rtk_stale=false
fi
if $_rtk_stale && command -v rtk &>/dev/null; then
  rtk gain 2>/dev/null | grep -E "Tokens saved:|Total commands:" | head -2 > "$RTK_CACHE" 2>/dev/null || true
fi
