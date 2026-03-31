# Claude Token-Saver — Best Practices

> Synthesized from RTK, context-mode, claude-hud, shellfirm, and vault pattern.
> Goal: maximum token efficiency + safety + developer experience.

---

## The 5 Laws

**1. Never load what you don't need right now.**
Skills in vault = 0 tokens. Skills in hot = loaded every session. Only `sm.md` earns the hot seat.

**2. Never make N calls when 1 batch call does the job.**
`ctx_batch_execute` for 2+ Bash/Read ops. 5 calls → 1 call = 90% savings. No exceptions.

**3. Never trust RTK to not exist.**
Always write code assuming RTK is active. Add `-u` to grep/ls for ultra-compact. It's transparent — you lose nothing if RTK is absent.

**4. Never skip shellfirm confirmation on destructive commands.**
AI agents don't hesitate. shellfirm does. If shellfirm flags a command, read the blast radius before proceeding.

**5. Always run `/sm init` at session start.**
Indexes docs, activates all layers, shows savings dashboard. 30 seconds → 4M tokens saved.

---

## Token Hierarchy (cheapest to most expensive)

| Rank | Operation | Cost | When |
|------|-----------|------|------|
| 1 | Vault cold storage | **0** | All rarely-used skills |
| 2 | `rg` on skills.idx | **~0** | Finding skills by keyword |
| 3 | `ctx_search` | ~200 | Fuzzy/semantic skill search |
| 4 | RTK Bash command | 60-90% less | Any CLI operation |
| 5 | `ctx_batch_execute` | ~300 total | 2+ commands/reads |
| 6 | `ctx_execute_file` | ~200 | Large file summarization |
| 7 | `ctx_fetch_and_index` | ~300 | URL → indexed source |
| 8 | `Read` (small files) | ~500-2K | Targeted file reads |
| 9 | Explore agent (haiku) | ~5-15K | Multi-file codebase search |
| 10 | General agent (sonnet) | ~50-200K | Complex multi-source research |

**Rule**: Always use the cheapest option that solves the problem.

---

## Vault Strategy

### What belongs in vault (cold storage)
Move skills you use less than once per day:

```bash
# Language-specific (only need when actively coding in that lang)
/sm vault kotlin-patterns
/sm vault laravel-tdd
/sm vault django-patterns
/sm vault swift-actor-persistence
/sm vault springboot-tdd

# Heavy meta skills (high token cost, rarely used)
/sm vault token-budget-advisor     # ~209 tokens! Move it.
/sm vault prompt-optimizer         # ~183 tokens

# Industry/ops (situational)
/sm vault logistics-exception-management
/sm vault customs-trade-compliance
/sm vault energy-procurement

# Batch move everything except sm.md
cd ~/.claude/skills
for f in $(ls | grep -v "^sm\.md$"); do /sm vault $f; done
/sm rebuild
```

### What stays hot
Only skills you invoke literally every session:
- `sm.md` — the skill manager itself (always hot)
- A handful of daily-driver skills (max 5)

### Rule of thumb
If you haven't used a skill in 3 days → vault it. `/sm load` brings it back instantly.

---

## ctx_batch_execute Patterns

### Standard codebase scan (use at start of every task)
```python
ctx_batch_execute(commands=[
  {"label": "structure",  "command": "find src/ -type f | head -30"},
  {"label": "git",        "command": "git log --oneline -10"},
  {"label": "status",     "command": "git status --short"},
  {"label": "readme",     "command": "cat README.md"},
  {"label": "deps",       "command": "cat package.json | python3 -c 'import json,sys; p=json.load(sys.stdin); [print(k) for k in p.get(\"dependencies\",{})]'"}
], queries=["project structure", "recent changes", "dependencies"])
```

### Before fixing a bug
```python
ctx_batch_execute(commands=[
  {"label": "error",    "command": "grep -r 'ERROR\\|Error\\|error' logs/ | tail -20"},
  {"label": "relevant", "command": "rg 'function_name' src/ -n"},
  {"label": "tests",    "command": "ls tests/"},
  {"label": "git_blame","command": "git log --oneline --follow src/broken_file.py | head -5"}
], queries=["error pattern", "function definition", "test coverage"])
```

### Multi-file analysis (replaces 10+ Read calls)
```python
ctx_batch_execute(commands=[
  {"label": "main",    "command": "cat src/main.rs"},
  {"label": "config",  "command": "cat src/config.rs"},
  {"label": "types",   "command": "cat src/types.rs"},
  {"label": "tests",   "command": "cat tests/integration.rs"}
], queries=["main entry point", "config structure", "type definitions"])
```

### When NOT to use ctx_batch_execute
- Single targeted read of a small known file → use `Read` directly
- One-liner Bash check → let RTK handle it automatically
- Searching for a specific function in a known file → `Grep` tool

---

## RTK Best Practices

RTK runs automatically — you don't need to think about it. But these maximize savings:

```bash
# Ultra-compact flag: +10-20% savings on output-heavy commands
rg "pattern" src/ -u          # ultra-compact grep
ls -la -u                     # ultra-compact dir listing
git log --oneline -20 -u      # ultra-compact git log

# Check your savings at any time
rtk gain                      # current session savings
rtk gain --graph              # 30-day trend
rtk discover -a               # find missed opportunities

# If RTK hook breaks
rtk init -g                   # refresh hook to latest
rtk verify                    # validate hook integrity
```

---

## shellfirm Best Practices

### Commands that should ALWAYS trigger shellfirm review:
- `rm -rf` anything (especially outside of node_modules)
- `git push --force` or `git push --force-with-lease`
- `git reset --hard`
- `kubectl delete` any resource
- `DROP TABLE` or `TRUNCATE`
- `chmod -R 777`
- `> file` (truncate) on important files

### When shellfirm blocks a command:
1. **Read the blast radius** — how many files/bytes affected?
2. **Read the alternative** — shellfirm usually suggests a safer option
3. **Confirm only if intentional** — solve the math challenge to proceed

### Adjust policy for your workflow:
```bash
shellfirm check "rm -rf node_modules"   # manual check
shellfirm explain-risk "git push -f"    # get MCP explanation
shellfirm get-policy                    # view current rules
```

### In CI/CD (no shellfirm needed):
```bash
SHELLFIRM_SKIP=1 ./deploy.sh            # env var to skip in automation
```

---

## Model Routing (cost optimization)

| Task | Model | Cost (in/out per M) |
|------|-------|---------------------|
| Search, explore, list skills | **Haiku 4.5** | $1/$5 |
| Code, plan, complex analysis | **Sonnet 4.6** | $3/$15 |
| Architecture decisions only | **Opus 4.6** | $5/$25 |

**Savings with routing**: Using Haiku for exploration = 3x cheaper than Sonnet, 5x cheaper than Opus.

```yaml
# In skill frontmatter:
model: haiku    # /sm, exploration, simple lookups
model: sonnet   # code generation, multi-step plans (default)
# Omit for Opus — only explicitly route to it
```

---

## HUD Configuration

The claude-hud shows 5 key panels:

```
[Project line]       workspace/dir  model  duration  speed
[Context bar]        ████████░░ 72%  3.2K tokens
[Usage windows]      5h: ████░ 45%  7d: ██░ 28%        ← the "2 usage windows"
[Environment]        CLAUDE.md:1  rules:8  hooks:12
[Extra label]        ⚡28K|ctx:83%|V:250|sf              ← CTS savings
```

### Customize HUD (`~/.claude/plugins/claude-hud/config.json`):
```json
{
  "lineLayout": "expanded",
  "display": {
    "showUsage": true,
    "usageBarEnabled": true,
    "showContextBar": true,
    "contextValue": "percent",
    "showSpeed": true,
    "showTokenBreakdown": true
  },
  "usage": {
    "cacheTtlSeconds": 60
  }
}
```

### HUD Extra Label key:
- `⚡28K` = RTK saved 28K tokens this session
- `ctx:83%` = context-mode achieved 83% reduction
- `V:250` = 250 skills in vault (0 startup tokens)
- `sf` = shellfirm active

---

## Session Workflow (optimal daily routine)

```
1. Start session:   /sm init
                    → indexes RTK.md, skills-catalog, toolstack
                    → shows all layers active + savings dashboard

2. Start task:      ctx_batch_execute([...], queries=[...])
                    → understand codebase in 1 call

3. Find skill:      /sm search <keyword>   or   /sm auto <intent>
                    → ~0 tokens, instant

4. Load skill:      /sm load <name>
                    → loads from vault on demand

5. Execute work:    Bash (RTK auto-compresses)
                    Read (small files only)
                    ctx_execute_file (large files)

6. At milestones:   /compact [focus area]
                    → compresses conversation, saves 100-200K/month

7. Session end:     rtk gain
                    → see how much you saved this session
```

---

## Anti-Patterns (what NOT to do)

```python
# ❌ Never: spawn an agent just to check local files
Agent(prompt="find all TypeScript files in src/")
# ✅ Instead: one ctx_batch_execute call (~300 tokens vs ~50K tokens)

# ❌ Never: 5 separate Bash calls
Bash("ls src/")
Bash("grep 'function' src/ -r")
Bash("cat README.md")
Bash("git log --oneline -5")
Bash("git status")
# ✅ Always: 1 ctx_batch_execute = 90% savings

# ❌ Never: load all skills at startup
# (this happens automatically if you don't use vault)
# ✅ Always: keep only sm.md hot, vault everything else

# ❌ Never: use Read for large files
Read("path/to/large/file.md")   # full content = thousands of tokens
# ✅ Always: ctx_execute_file
ctx_execute_file(path="...", intent="understand structure")  # ~200 tokens

# ❌ Never: bypass shellfirm for "speed"
# The 2 seconds you save aren't worth the 2 hours of recovery
# ✅ Always: read the blast radius, then confirm or cancel
```

---

## Estimated Monthly Savings

| Layer | Sessions/month | Savings/session | Monthly total |
|-------|----------------|-----------------|---------------|
| Vault (0 startup tokens) | 300 | ~10K | **3M tokens** |
| RTK Bash compression | 300 | ~5K | **1.5M tokens** |
| ctx_batch_execute | 300 | ~8K | **2.4M tokens** |
| ctx_execute_file/fetch | 300 | ~3K | **0.9M tokens** |
| /compact at milestones | 300 | ~500 | **150K tokens** |
| **Total** | | | **~8M tokens/month** |

**Cost saved at Sonnet rates ($3/M input):** ~$24/month
**Cost saved at Opus rates ($5/M input):** ~$40/month

These are conservative estimates. Power users report 10M+ tokens/month saved.
