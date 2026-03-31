---
name: sm
description: Skill Manager — find and load any of the 320 skills on demand. Auto-invokes when user asks "what skill", "which command", "can you", "do you have a skill for", or mentions needing a specific capability. Token-efficient: skills load lazily via index, never all at once.
argument-hint: "[search <query> | load <name> | list [cat] | rebuild | auto <intent>]"
allowed-tools: [Bash, Read, mcp__context-mode__ctx_search, mcp__context-mode__ctx_index]
model: haiku
---

# Skill Manager (sm) — On-Demand Skill Discovery

**Index**: `~/.claude/skills.idx` (320 skills, one line each — grep-able, 54KB)
**Catalog**: `~/.claude/skills-catalog.md` (markdown, ctx_indexed by category)
**Token cost of this lookup**: ~0 (index never enters context, only matches returned)

## Dispatch on $ARGUMENTS

Parse the first word of `$ARGUMENTS` to decide action:

---

### `search <query>` — Fast grep lookup

```bash
QUERY="${ARGUMENTS#search }"
echo "=== Skills matching: $QUERY ==="
rg -i "$QUERY" ~/.claude/skills.idx | awk -F'\t' '{
    printf "  /%s\n    [%s] %s\n\n", $1, $2, $3
}' | head -60
```

If grep returns 0 results, fall back to ctx_search (semantic).

---

### `load <name>` — Read full skill content

```bash
NAME="${ARGUMENTS#load }"
PATH=$(rg "^$NAME\t" ~/.claude/skills.idx | cut -f4)
if [ -n "$PATH" ]; then
    echo "=== Loading: /$NAME ==="
    cat "$PATH"
else
    echo "Not found: $NAME"
    echo "Try: /sm search $NAME"
fi
```

---

### `list [category]` — Show skills by category

```bash
CAT="${ARGUMENTS#list}"
CAT="${CAT## }"
if [ -z "$CAT" ]; then
    # Summary: count per category
    awk -F'\t' '{print $2}' ~/.claude/skills.idx | sort | uniq -c | sort -rn | \
        awk '{printf "  %-14s %3d skills\n", $2, $1}'
else
    # Filter by category
    rg -i "	$CAT	" ~/.claude/skills.idx | awk -F'\t' '{printf "  /%s — %s\n", $1, $3}'
fi
```

---

### `auto <intent>` — Find best skill for an intent, then invoke it

1. Run grep search on intent
2. If ≥1 match with confidence > 80%: output the skill name and say "Invoking /skill-name"
3. If multiple candidates: list top 5 and ask which one

```bash
INTENT="${ARGUMENTS#auto }"
echo "Finding best skill for: $INTENT"
MATCHES=$(rg -i "$INTENT" ~/.claude/skills.idx | head -5)
echo "$MATCHES" | awk -F'\t' '{printf "  /%s — %s\n", $1, $3}'
```

Then reason about which skill best matches the intent and invoke it via the Skill tool.

---

### `rebuild` — Rebuild index from scratch

```bash
python3 /tmp/build_skills_idx.py 2>/dev/null || python3 << 'PYEOF'
import os, re
from pathlib import Path
from collections import defaultdict

skills_dir = Path.home() / ".claude/skills"
idx_path = Path.home() / ".claude/skills.idx"
md_path = Path.home() / ".claude/skills-catalog.md"

CATS = {
    'gsd': 'GSD', 'opsx': 'OpenSpec', 'openspec': 'OpenSpec',
    'rust': 'Lang', 'python': 'Lang', 'kotlin': 'Lang', 'swift': 'Lang',
    'java': 'Lang', 'go-': 'Lang', 'golang': 'Lang', 'cpp': 'Lang',
    'perl': 'Lang', 'django': 'Lang', 'laravel': 'Lang', 'spring': 'Lang',
    'typescript': 'Lang', 'android': 'Lang',
    'agent': 'Agents', 'browser': 'Agents', 'devfleet': 'Agents',
    'orchestrat': 'Agents', 'autonomous': 'Agents',
    'intel': 'Biz', 'revenue': 'Biz', 'thinkrich': 'Biz', 'market': 'Biz',
    'outreach': 'Biz', 'revshare': 'Biz', 'daily': 'Biz', 'briefing': 'Biz',
    'db': 'Data', 'knowledge': 'Data', 'postgres': 'Data',
    'clickhouse': 'Data', 'database': 'Data', 'surreal': 'Data',
    'docker': 'DevOps', 'deploy': 'DevOps', 'commit': 'DevOps',
    'github': 'DevOps', 'pm2': 'DevOps',
    'plan': 'PM', 'spec': 'PM', 'review': 'PM', 'tdd': 'PM',
    'test': 'PM', 'verify': 'PM', 'plane': 'PM', 'debug': 'PM',
    'ghost': 'Browser', 'scrape': 'Browser', 'crawl': 'Browser',
    'video': 'Media', 'fal': 'Media', 'security': 'Security',
}

def get_cat(name):
    n = name.lower()
    for k, v in CATS.items():
        if k in n:
            return v
    return 'Other'

entries = defaultdict(list)
seen = set()

for f in sorted(skills_dir.rglob("*.md")):
    try:
        content = f.read_text(errors='ignore')
        name, desc, model = None, "", "sonnet"
        in_fm = False
        for line in content.split('\n')[:30]:
            s = line.strip()
            if s == '---':
                in_fm = not in_fm
                continue
            if in_fm:
                if s.startswith('name:'):
                    name = s.split(':', 1)[1].strip()
                elif s.startswith('description:'):
                    desc = s.split(':', 1)[1].strip()[:90]
                elif s.startswith('model:'):
                    model = s.split(':', 1)[1].strip()
        if not name or name in seen:
            continue
        seen.add(name)
        cat = get_cat(name)
        entries[cat].append((name, desc, str(f)))
    except:
        pass

# Write TSV index
idx_lines = []
for cat, skills in entries.items():
    for name, desc, path in skills:
        idx_lines.append(f"{name}\t{cat}\t{desc.replace(chr(9), ' ')}\t{path}")

with open(idx_path, 'w') as fh:
    fh.write('\n'.join(sorted(idx_lines)) + '\n')

# Write markdown catalog
md_lines = ["# Skills Catalog\n"]
for cat in sorted(entries.keys()):
    skills = sorted(entries[cat])
    md_lines.append(f"\n## {cat} ({len(skills)} skills)\n")
    for name, desc, path in skills:
        md_lines.append(f"- `/{name}` — {desc}")

with open(md_path, 'w') as fh:
    fh.write('\n'.join(md_lines))

total = sum(len(v) for v in entries.values())
print(f"Rebuilt: {total} skills indexed")
PYEOF
echo "Done. Re-run /sm rebuild to also re-index ctx."
```

After rebuild, re-index for ctx_search:
Use `mcp__context-mode__ctx_index` with `path: ~/.claude/skills-catalog.md` and `source: skills-catalog`

---

### No args / `help` → Show summary + usage

```bash
TOTAL=$(wc -l < ~/.claude/skills.idx)
echo "=== Skill Manager — $TOTAL skills available ==="
echo ""
echo "Commands:"
echo "  /sm search <query>    — grep search (instant, 0 tokens)"
echo "  /sm list [category]   — browse by category"
echo "  /sm load <name>       — read full skill content"
echo "  /sm auto <intent>     — find + invoke best match"
echo "  /sm rebuild           — rebuild index from skills dir"
echo ""
echo "Categories:"
awk -F'\t' '{print $2}' ~/.claude/skills.idx | sort | uniq -c | sort -rn | \
    awk '{printf "  %-14s %3d\n", $2, $1}' | head -15
echo ""
echo "Index: ~/.claude/skills.idx ($(wc -c < ~/.claude/skills.idx | tr -d ' ') bytes)"
echo "Ctx:   skills-catalog (indexed, use ctx_search for semantic lookup)"
```

---

## How Claude Should Use This

When you (Claude) need to find a skill:

1. **Known name** → invoke directly via Skill tool: `Skill("agent-browser")`
2. **Unknown/fuzzy** → `rg -i "keyword" ~/.claude/skills.idx | head -10`
3. **Semantic/vague** → `ctx_search(queries=["intent"], source="skills-catalog")`
4. **Load content** → `Read(skill_path)` where path = 4th column from idx

**Never** scan all 320 skill files. Always grep the index first.

## Token Budget

| Method | Tokens consumed |
|--------|----------------|
| Grep idx | ~0 (result only) |
| ctx_search | ~200-500 (snippets only, content stays in db) |
| Read one skill | ~500-5000 (that skill only) |
| All skills loaded | ~160,000 (avoid!) |
