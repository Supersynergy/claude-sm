#!/bin/bash
# HUD Extra Command — CTS Token Savings + Services + Tasks
# Output: JSON { "label": "..." } (max 50 chars)
# Called ~300ms by claude-hud — MUST be <100ms. All heavy ops use caches.
#
# Label format: ⚡18K|ctx:83%|V:250|sf | CRM+SDB | 2wip/3t

CACHE_DIR="/tmp/hud-cache"
CTS_CACHE_DIR="$HOME/.claude/cache"
mkdir -p "$CACHE_DIR" "$CTS_CACHE_DIR" 2>/dev/null

# Fast staleness check — returns 0 (stale) or 1 (fresh)
_fresh() { [ -f "$1" ] && [ $(( $(date +%s) - $(stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0) )) -lt "$2" ]; }

parts=()

# ── 1. CTS Token Savings (cached 30s) ────────────────────────────────────────
# Shows: RTK tokens saved this session, ctx-mode reduction %, vault count, shellfirm
CTS_CACHE="$CACHE_DIR/cts"
if ! _fresh "$CTS_CACHE" 30; then
  s=()
  # RTK savings — parse "Tokens saved: 18.0K"
  if command -v rtk &>/dev/null; then
    saved=$(rtk gain 2>/dev/null | awk '/Tokens saved:/{print $3}')
    [ -n "$saved" ] && s+=("⚡${saved}")
  fi
  # ctx-mode % — written by cts-cache-refresh.sh via ctx_stats
  if [ -f "$CTS_CACHE_DIR/ctx-pct.txt" ]; then
    p=$(tr -d ' %' < "$CTS_CACHE_DIR/ctx-pct.txt" 2>/dev/null)
    [ -n "$p" ] && [ "$p" != "0" ] && s+=("ctx:${p}%")
  fi
  # Vault skill count — fast awk on skills.idx
  IDX="$HOME/.claude/skills.idx"
  if [ -f "$IDX" ]; then
    v=$(awk -F'\t' '$5=="1"' "$IDX" 2>/dev/null | wc -l | tr -d ' ')
    [ "${v:-0}" -gt 0 ] && s+=("V:${v}")
  fi
  # shellfirm active
  command -v shellfirm &>/dev/null && s+=("sf")
  if [ ${#s[@]} -gt 0 ]; then
    printf '%s' "$(IFS='|'; echo "${s[*]}")" > "$CTS_CACHE"
  else
    printf '' > "$CTS_CACHE"
  fi
fi
cts=$(cat "$CTS_CACHE" 2>/dev/null)
[ -n "$cts" ] && parts+=("$cts")

# ── 2. Running services (cached 30s) ─────────────────────────────────────────
SVC_CACHE="$CACHE_DIR/services"
if ! _fresh "$SVC_CACHE" 30; then
  svcs=""
  lsof -iTCP:3001 -sTCP:LISTEN &>/dev/null && svcs="${svcs}CRM+"
  lsof -iTCP:9926 -sTCP:LISTEN &>/dev/null && svcs="${svcs}SDB+"
  lsof -iTCP:8000 -sTCP:LISTEN &>/dev/null && svcs="${svcs}SSCRM+"
  lsof -iTCP:7777 -sTCP:LISTEN &>/dev/null && svcs="${svcs}ZC+"
  lsof -iTCP:11434 -sTCP:LISTEN &>/dev/null && svcs="${svcs}LLM+"
  lsof -iTCP:5173 -sTCP:LISTEN &>/dev/null && svcs="${svcs}DEV+"
  lsof -iTCP:8090 -sTCP:LISTEN &>/dev/null && svcs="${svcs}PLN+"
  printf '%s' "${svcs%+}" > "$SVC_CACHE"
fi
svc=$(cat "$SVC_CACHE" 2>/dev/null)
[ -n "$svc" ] && parts+=("$svc")

# ── 3. Beads tasks (cached 60s) ───────────────────────────────────────────────
BD_CACHE="$CACHE_DIR/beads"
if ! _fresh "$BD_CACHE" 60; then
  if command -v bd &>/dev/null; then
    wip=$(bd list --status=in_progress 2>/dev/null | grep -c "^beads-" || true)
    open=$(bd list --status=open 2>/dev/null | grep -c "^beads-" || true)
    printf '%s' "${wip:-0}:${open:-0}" > "$BD_CACHE"
  else
    printf '%s' "0:0" > "$BD_CACHE"
  fi
fi
bd_data=$(cat "$BD_CACHE" 2>/dev/null)
wip="${bd_data%%:*}"; open="${bd_data##*:}"
if [ "${wip:-0}" -gt 0 ] 2>/dev/null; then
  parts+=("${wip}wip/${open}t")
elif [ "${open:-0}" -gt 0 ] 2>/dev/null; then
  parts+=("${open}t")
fi

# ── Output ────────────────────────────────────────────────────────────────────
if [ ${#parts[@]} -eq 0 ]; then
  echo '{"label":""}'
else
  label=$(IFS="|"; echo "${parts[*]}")
  printf '{"label":"%s"}\n' "${label:0:50}"
fi
