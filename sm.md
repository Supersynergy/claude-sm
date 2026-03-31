---
name: sm
description: Claude Skill Manager & Token Saver — find, load, and manage skills on demand with ~0 token overhead. Auto-invokes when user asks "what skill", "which command", "can you", "do you have a skill for", mentions needing a capability, or says "skills". Saves tokens via vault pattern (cold skills), lazy loading, ctx_search, and RTK integration.
argument-hint: "[search <q> | load <name> | list [cat] | auto <intent> | vault <name> | unvault <name> | stats | tokens | rebuild]"
allowed-tools: [Bash, Read, mcp__context-mode__ctx_search, mcp__context-mode__ctx_index, mcp__context-mode__ctx_batch_execute, mcp__context-mode__ctx_stats]
model: haiku
---

# Claude Skill Manager & Token Saver (`/sm`)

**Index**: `~/.claude/skills.idx` | 5-col TSV: name/cat/desc/path/vault | grep-able, instant
**Catalog**: `~/.claude/skills-catalog.md` | ctx-indexed, BM25 semantic
**Hot dir**: `~/.claude/skills/` — auto-loaded by Claude Code at startup
**Vault dir**: `~/.claude/skills-vault/` — cold storage, NOT loaded at startup (saves ~5-8K tokens)
**Rule**: NEVER load all skills. grep idx → ctx_search if fuzzy → Read() only the match.

`[V]` = vault skill (not auto-loaded). Still searchable + loadable on demand via `/sm load`.

---

## Dispatch on `$ARGUMENTS`

Parse the **first word** to select action. Default (no args) → help + stats.

---

### `search <query>` — Instant grep, 0 tokens

```bash
QUERY="${ARGUMENTS#search }"
IDX="$HOME/.claude/skills.idx"
[ ! -f "$IDX" ] && echo "Index missing. Run: /sm rebuild" && exit 0

echo "=== Skills matching: $QUERY ==="
RESULTS=$(rg -i "$QUERY" "$IDX" 2>/dev/null)

if [ -n "$RESULTS" ]; then
  echo "$RESULTS" | awk -F'\t' '{
    vault = ($5=="1") ? " [V]" : ""
    printf "  /%-28s [%s]%s %s\n", $1, $2, vault, $3
  }' | head -30
else
  echo "No exact match. Fuzzy:"
  for word in $QUERY; do
    rg -i "$word" "$IDX" 2>/dev/null
  done | sort -u | awk -F'\t' '{
    vault = ($5=="1") ? " [V]" : ""
    printf "  /%-28s [%s]%s %s\n", $1, $2, vault, $3
  }' | head -20
  echo ""
  echo "For semantic search: /sm auto $QUERY"
fi
```

---

### `load <name>` — Read one skill on demand (works for hot AND vault skills)

```bash
NAME="${ARGUMENTS#load }"
IDX="$HOME/.claude/skills.idx"

LINE=$(rg "^${NAME}\t" "$IDX" 2>/dev/null | head -1)
[ -z "$LINE" ] && LINE=$(rg -i "^${NAME}" "$IDX" 2>/dev/null | head -1)

if [ -n "$LINE" ]; then
  SKILL_PATH=$(echo "$LINE" | cut -f4)
  IS_VAULT=$(echo "$LINE" | cut -f5)
  [ "$IS_VAULT" = "1" ] && echo "[V] Loading from vault: $SKILL_PATH"
  echo "=== /$NAME ==="
  cat "$SKILL_PATH"
else
  echo "Not found: $NAME. Did you mean:"
  rg -i "$NAME" "$IDX" 2>/dev/null | awk -F'\t' '{
    vault = ($5=="1") ? " [V]" : ""
    printf "  /%s%s — %s\n", $1, vault, $3
  }' | head -5
fi
```

---

### `list [category]` — Browse portfolio

```bash
CAT="${ARGUMENTS#list}"
CAT="${CAT## }"
IDX="$HOME/.claude/skills.idx"

if [ -z "$CAT" ]; then
  TOTAL=$(wc -l < "$IDX" | tr -d ' ')
  HOT=$(awk -F'\t' '$5=="0"' "$IDX" | wc -l | tr -d ' ')
  VAULT=$(awk -F'\t' '$5=="1"' "$IDX" | wc -l | tr -d ' ')
  echo "=== Skills Portfolio: $TOTAL total ($HOT hot + $VAULT vault) ==="
  echo ""
  echo "Hot (loaded at startup):"
  awk -F'\t' '$5=="0" {print $2}' "$IDX" | sort | uniq -c | sort -rn | \
    awk '{printf "  %-16s %3d\n", $2, $1}'
  echo ""
  echo "Vault [V] (on-demand, 0 startup cost):"
  awk -F'\t' '$5=="1" {print $2}' "$IDX" | sort | uniq -c | sort -rn | \
    awk '{printf "  %-16s %3d\n", $2, $1}'
else
  COUNT=$(rg -ic "\t${CAT}\t" "$IDX" 2>/dev/null || echo 0)
  echo "=== $CAT ($COUNT skills) ==="
  rg -i "\t${CAT}\t" "$IDX" 2>/dev/null | \
    awk -F'\t' '{
      vault = ($5=="1") ? " [V]" : ""
      printf "  /%-30s%s %s\n", $1, vault, $3
    }' | head -50
fi
```

---

### `auto <intent>` — Find best skill and invoke it

1. `rg -i` on intent (searches name + desc in idx)
2. Score: exact name > prefix > desc keyword > semantic
3. 1 clear winner → invoke via Skill tool
4. Multiple candidates → show top 5, ask
5. Vault skills can be invoked — load their content first via Read()

```bash
INTENT="${ARGUMENTS#auto }"
IDX="$HOME/.claude/skills.idx"
echo "Searching for: $INTENT"
MATCHES=$(rg -i "$INTENT" "$IDX" 2>/dev/null | head -5)
echo "$MATCHES" | awk -F'\t' '{
  vault = ($5=="1") ? " [V]" : ""
  printf "  /%s%s — %s\n", $1, vault, $3
}'
```

If MATCHES is empty → use ctx_search:
`mcp__context-mode__ctx_search` with `queries=["$INTENT"]` and `source="skills-catalog"`

Then reason about best match and invoke via Skill tool. For vault skills: Read() the path first, then follow the skill's instructions.

---

### `vault <name>` — Move hot skill to vault (saves startup tokens)

```bash
NAME="${ARGUMENTS#vault }"
IDX="$HOME/.claude/skills.idx"
LINE=$(rg "^${NAME}\t" "$IDX" 2>/dev/null | head -1)
if [ -z "$LINE" ]; then echo "Skill not found: $NAME"; exit 0; fi

IS_VAULT=$(echo "$LINE" | cut -f5)
if [ "$IS_VAULT" = "1" ]; then echo "Already in vault: $NAME"; exit 0; fi

SKILL_PATH=$(echo "$LINE" | cut -f4)
# Get the skill's top-level dir or file
SKILL_ITEM=$(echo "$SKILL_PATH" | sed "s|$HOME/.claude/skills/||" | cut -d'/' -f1)
SRC="$HOME/.claude/skills/$SKILL_ITEM"
VAULT="$HOME/.claude/skills-vault"

if [ -e "$SRC" ]; then
  mv "$SRC" "$VAULT/"
  echo "Vaulted: $NAME ($SKILL_ITEM)"
  echo "Rebuilding index..."
  python3 "$HOME/.claude/scripts/build-skills-index.py" -q
  echo "Done. $NAME is now cold-stored — use /sm load $NAME to access."
else
  echo "Cannot vault: $SRC not found (may be from ECC plugin)"
fi
```

---

### `unvault <name>` — Restore vault skill to hot (auto-loads at startup)

```bash
NAME="${ARGUMENTS#unvault }"
IDX="$HOME/.claude/skills.idx"
LINE=$(rg "^${NAME}\t" "$IDX" 2>/dev/null | head -1)
if [ -z "$LINE" ]; then echo "Skill not found: $NAME"; exit 0; fi

IS_VAULT=$(echo "$LINE" | cut -f5)
if [ "$IS_VAULT" = "0" ]; then echo "Already hot: $NAME"; exit 0; fi

SKILL_PATH=$(echo "$LINE" | cut -f4)
SKILL_ITEM=$(echo "$SKILL_PATH" | sed "s|$HOME/.claude/skills-vault/||" | cut -d'/' -f1)
SRC="$HOME/.claude/skills-vault/$SKILL_ITEM"
HOT="$HOME/.claude/skills"

if [ -e "$SRC" ]; then
  mv "$SRC" "$HOT/"
  echo "Unvaulted: $NAME ($SKILL_ITEM) — will auto-load next session"
  python3 "$HOME/.claude/scripts/build-skills-index.py" -q
else
  echo "Cannot unvault: $SRC not found"
fi
```

---

### `stats` — Portfolio + token savings overview

```bash
IDX="$HOME/.claude/skills.idx"
TOTAL=$(wc -l < "$IDX" | tr -d ' ')
HOT=$(awk -F'\t' '$5=="0"' "$IDX" | wc -l | tr -d ' ')
VAULT=$(awk -F'\t' '$5=="1"' "$IDX" | wc -l | tr -d ' ')
CATS=$(awk -F'\t' '{print $2}' "$IDX" | sort -u | wc -l | tr -d ' ')
IDX_BYTES=$(wc -c < "$IDX" | tr -d ' ')

echo "=== Skill Manager & Token Saver — Stats ==="
echo ""
printf "  %-22s %s total (%s hot + %s vault)\n" "Skills indexed:" "$TOTAL" "$HOT" "$VAULT"
printf "  %-22s %s\n" "Categories:" "$CATS"
printf "  %-22s %s bytes\n" "Index size:" "$IDX_BYTES"
echo ""
echo "Token Architecture:"
printf "  %-32s %s\n" "Hot skills startup cost:" "~$(echo "$HOT * 40 / 1000" | bc)K tokens (avg 40/skill)"
printf "  %-32s %s\n" "Vault skills startup cost:" "0 tokens (cold-stored)"
printf "  %-32s %s\n" "Search via rg (Layer 1):" "~0 tokens, <20ms"
printf "  %-32s %s\n" "Search via ctx_search (Layer 2):" "~200-500 tokens, BM25"
printf "  %-32s %s\n" "Load one skill (Layer 3):" "~500-5K tokens"
printf "  %-32s %s\n" "All skills loaded (NEVER):" "~150K+ tokens"
echo ""
echo "RTK Savings (this session):"
rtk gain 2>/dev/null | grep -E "Tokens saved|Efficiency meter" | sed 's/^/  /' || echo "  rtk gain — check savings"
```

---

### `tokens` — Token saving cheatsheet

```bash
echo "=== Token Saving Cheatsheet ==="
echo ""
echo "VAULT PATTERN (biggest win)"
echo "  Skills not used daily → /sm vault <name>  (0 startup cost)"
echo "  Still searchable, loadable on demand"
echo "  Hot→Vault saves ~40 tokens/skill at startup"
echo ""
echo "SKILL DISCOVERY (this manager)"
echo "  /sm search <q>       ~0 tokens    rg on idx"
echo "  /sm auto <intent>    ~0-500       grep + optional ctx_search"
echo "  /sm load <name>      ~500-5K      one skill on demand"
echo ""
echo "RTK — CLI COMPRESSION  (60-90% per command)"
echo "  Hooks auto-rewrite: git, grep, ls, curl, find, docker, gh..."
echo "  rtk gain             show total savings"
echo ""
echo "CONTEXT-MODE — LARGE OUTPUT VIRTUALIZATION"
echo "  ctx_batch_execute    run N queries in 1 call"
echo "  ctx_index + search   index large files, avoid loading them"
echo ""
echo "STRATEGIC COMPACT"
echo "  /compact             after milestones — reset context pressure"
echo ""
echo "MODEL ROUTING"
echo "  haiku:  search, explore, simple tasks  (\$1/\$5 per M)"
echo "  sonnet: code, planning, complex tasks  (\$3/\$15 per M)"
echo "  opus:   architecture decisions only    (\$5/\$25 per M)"
```

---

### `rebuild` — Regenerate index from hot + vault dirs

```bash
SCRIPT="$HOME/.claude/scripts/build-skills-index.py"
if [ -f "$SCRIPT" ]; then
  echo "Rebuilding skills index (hot + vault)..."
  python3 "$SCRIPT"
  echo ""
  echo "Re-indexing catalog for ctx_search..."
  # ctx_index will be called after this block
else
  echo "Build script missing. Reinstall:"
  echo "  curl -fsSL https://raw.githubusercontent.com/Supersynergy/claude-sm/main/install.sh | bash"
fi
```

After rebuild, call `mcp__context-mode__ctx_index` with:
- `path: ~/.claude/skills-catalog.md`
- `source: skills-catalog`

---

### No args → Help

```bash
IDX="$HOME/.claude/skills.idx"
[ ! -f "$IDX" ] && echo "Index not found. Run: python3 ~/.claude/scripts/build-skills-index.py" && exit 0
TOTAL=$(wc -l < "$IDX" | tr -d ' ')
HOT=$(awk -F'\t' '$5=="0"' "$IDX" | wc -l | tr -d ' ')
VAULT=$(awk -F'\t' '$5=="1"' "$IDX" | wc -l | tr -d ' ')
BYTES=$(wc -c < "$IDX" | tr -d ' ')

echo "=== Claude Skill Manager & Token Saver — $TOTAL skills ($HOT hot + $VAULT vault) ==="
echo ""
echo "  /sm search <query>    find by keyword  (~0 tokens)"
echo "  /sm list [category]   browse portfolio (hot + vault)"
echo "  /sm load <name>       read full skill  (works for vault too)"
echo "  /sm auto <intent>     find + invoke best match"
echo "  /sm vault <name>      move skill to cold storage (saves tokens)"
echo "  /sm unvault <name>    restore vault skill to hot"
echo "  /sm stats             portfolio + token savings overview"
echo "  /sm tokens            token saving tips"
echo "  /sm rebuild           refresh index"
echo ""
echo "  [V] = vault skill — searchable but not auto-loaded (0 startup cost)"
echo ""
echo "Hot categories (loaded at startup):"
awk -F'\t' '$5=="0" {print $2}' "$IDX" | sort | uniq -c | sort -rn | head -6 | \
  awk '{printf "  %-16s %3d skills\n", $2, $1}'
echo ""
echo "Index: ~/.claude/skills.idx ($BYTES bytes)"
```

---

## Token Budget Table

| Method | Tokens | When |
|--------|--------|------|
| Hot skill metadata | ~40/skill | loaded at startup automatically |
| Vault skill metadata | **0** | cold-stored, never auto-loaded |
| `rg` on idx | **~0** | exact/keyword search |
| `ctx_search` | ~200-500 | semantic/fuzzy |
| `Read` one skill | ~500-5K | loading content |
| All skills loaded | ~150K | **never do this** |
