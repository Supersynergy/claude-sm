# claude-token-saver (cts) — Extreme Token Savings for Claude Code

> **4–5M tokens/month saved.** One command to activate the full stack.
> Vault pattern + lazy skill loading + RTK + context-mode + shellfirm safety.

[![Claude Code](https://img.shields.io/badge/Claude_Code-2.1+-blueviolet)](https://claude.ai/code)
[![Token savings](https://img.shields.io/badge/savings-4--5M_tokens%2Fmonth-brightgreen)](#token-savings)
[![Vault](https://img.shields.io/badge/startup_tokens-~40_(1_skill)-orange)](#vault-pattern)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## The Problem

Claude Code burns tokens before you even start working:

- **Skills at startup**: 300+ skills × ~40 tokens = **12,000+ tokens wasted every session**
- **Multiple Bash calls**: 5 separate commands = ~2,500 tokens overhead (vs 300 with batching)
- **Large file reads**: Full `cat file.rs` = thousands of tokens (vs 200 with summarization)
- **No safety net**: AI agents run `rm -rf` and `git push --force` without hesitation

**This repo solves all four.**

---

## The Stack (4 Layers + Safety)

```
Session cost without cts:  ~160K tokens/session startup
Session cost with cts:     ~40 tokens startup + on-demand only

Monthly savings:           4–5M tokens (~$12–75/month at Sonnet/Opus rates)
```

### Layer 0: Vault — Zero Startup Skills

```
~/.claude/skills/        = HOT  (auto-loaded, ~40 tokens — only sm.md)
~/.claude/skills-vault/  = COLD (never auto-loaded, 0 startup tokens)
```

All 300+ skills in cold storage. Fully discoverable, zero startup cost.

### Layer 1: `/sm` — On-Demand Skill Discovery (~0 tokens)

Three-layer lazy loading:

| Layer | Method | Tokens | Speed |
|-------|--------|--------|-------|
| **1. Grep** | `rg` on `skills.idx` TSV | **~0** | <20ms |
| **2. Semantic** | `ctx_search` BM25 on catalog | ~200 | fast |
| **3. Load** | `Read()` one matched file | ~500–5K | on-demand |
| ~~All skills~~ | ~~Load everything~~ | ~~160K+~~ | ~~never~~ |

### Layer 2: RTK — Bash Compression (60-90% savings)

RTK (Rust Token Killer) rewrites ALL Bash commands automatically via PreToolUse hook:

```
git status/log/diff  →  rtk git *     (80% savings)
ls / find            →  rtk ls/find   (80-96% savings)
grep / rg            →  rtk grep      (55-75% savings)
cargo test/check     →  rtk cargo *   (91-98% savings)
pytest / npm test    →  rtk pytest    (80-90% savings)
```

Add `-u` flag for ultra-compact mode (+10-20% more savings).

### Layer 3: context-mode — Batch Execution (90% savings)

**Golden rule: 2+ Bash calls → ALWAYS use `ctx_batch_execute`**

```python
# ❌ NEVER: 5 separate Bash calls = ~2,500 tokens
ls src/
grep "function" src/ -r
cat README.md
git log --oneline -10
git status

# ✅ ALWAYS: 1 ctx_batch_execute = ~300 tokens (90% savings)
ctx_batch_execute(commands=[
  {"label": "tree",      "command": "ls src/"},
  {"label": "functions", "command": "grep 'function' src/ -r"},
  {"label": "readme",    "command": "cat README.md"},
  {"label": "git log",   "command": "git log --oneline -10"},
  {"label": "status",    "command": "git status"}
], queries=["project structure", "key functions"])
```

| Tool | Situation | Savings |
|------|-----------|---------|
| `ctx_batch_execute` | 2+ Bash commands | **90%** |
| `ctx_execute_file` | Read large file | **85%** |
| `ctx_fetch_and_index` | Fetch URL / docs | **80%** |
| `ctx_search` | Search indexed content | ~200 tokens total |
| RTK hook | Single Bash command | 60-90% auto |

### Layer 4 (Safety): shellfirm — Dangerous Command Guard

> "Humans make mistakes. AI agents make them faster."

shellfirm intercepts destructive commands before execution:

```
rm -rf /important/dir  →  BLOCKED + blast radius shown + alternative suggested
git push --force       →  BLOCKED + severity: CRITICAL + math challenge required
kubectl delete ns prod →  BLOCKED + context-aware (K8s namespace protection)
```

MCP tools available to Claude: `check_command`, `suggest_alternative`, `explain_risk`, `get_policy`

---

## One Command — `/sm init`

Run once per session. Activates all layers:

```
/sm init
```

Output:
```
Token Stack Status
==================
Layer 0: Vault    1 hot / 313 vault (saves 12,520 startup tokens)
Layer 1: sm.md    skills.idx ready (320 skills, grep-able)
Layer 2: RTK      v0.33.1 active (PreToolUse hook verified)
Layer 3: ctx-mode v1.0.54 active (saved 71K tokens this session so far)
Layer 4: safety   shellfirm v0.3.9 active (PreToolUse + MCP)

Decision Matrix:
  2+ commands  → ctx_batch_execute  (90% savings)
  large file   → ctx_execute_file   (85% savings)
  URL / docs   → ctx_fetch_and_index (80% savings)
  single bash  → RTK auto           (60-90% savings)
  skill search → /sm search <query> (~0 tokens)
```

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Supersynergy/claude-token-saver/main/install.sh | bash
```

### Requirements

- Claude Code 2.1+
- Python 3.8+ with [ripgrep](https://github.com/BurntSushi/ripgrep) (`brew install ripgrep`)
- [RTK](https://rtk-ai.app) — `brew install rtk-ai/tap/rtk`
- [context-mode](https://github.com/mksglu/context-mode) — via ECC or `npm install -g context-mode`
- [shellfirm](https://github.com/kaplanelad/shellfirm) — `brew tap kaplanelad/tap && brew install shellfirm`

The install script checks and guides through all dependencies.

### Manual Install

```bash
cp sm.md ~/.claude/skills/sm.md
cp build-skills-index.py ~/.claude/scripts/
cp skills-index-session.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/skills-index-session.sh
mkdir -p ~/.claude/skills-vault

# Build index (hot + vault)
python3 ~/.claude/scripts/build-skills-index.py --vault-dir ~/.claude/skills-vault

# Move all skills to vault (zero startup)
cd ~/.claude/skills
for item in $(ls | grep -v "^sm\.md$"); do mv "$item" ../skills-vault/; done
python3 ~/.claude/scripts/build-skills-index.py --vault-dir ~/.claude/skills-vault

# Wire RTK (auto-compress all Bash)
rtk init -g

# Wire shellfirm (safety guardrails)
shellfirm connect claude-code
```

### CLAUDE.md Integration

Add this block to `~/.claude/CLAUDE.md` for persistent rules:

```markdown
## Token Stack — ALWAYS USE

### Session Start
Run `/sm init` — activates all layers, shows savings dashboard.

### Layer 1: RTK (automatic)
All Bash auto-compressed 60-90%. Ultra-compact: add `-u` flag.

### Layer 2: context-mode (83% context reduction)
ALWAYS use `ctx_batch_execute` for 2+ Bash/Read calls.

| Situation | Tool | Savings |
|-----------|------|---------|
| 2+ Bash | `ctx_batch_execute` | 90% |
| Large file | `ctx_execute_file` | 85% |
| Fetch URL | `ctx_fetch_and_index` | 80% |
| Search indexed | `ctx_search` | ~200 tokens |

### Layer 3: Skills (~0 tokens)
/sm search <query>  # instant grep on index
/sm auto <intent>   # find + invoke best skill
/sm load <name>     # load from vault on demand
```

---

## Usage

```
/sm init               — activate full token stack (run once per session)
/sm search <query>     — instant keyword search (~0 tokens)
/sm list [category]    — browse by category
/sm load <name>        — read full skill content (vault works too)
/sm auto <intent>      — find best skill and invoke it
/sm vault <name>       — move to cold storage
/sm unvault <name>     — restore from vault
/sm stats              — portfolio overview + token savings
/sm tokens             — full token-saving cheatsheet
/sm rebuild            — regenerate index after adding/moving skills
```

### Examples

```bash
/sm init                                         # activate all layers, see dashboard
/sm search browser                               # finds agent-browser, ghostbrowser, ...
/sm search plane                                 # finds /plane (PM skill)
/sm list Agents                                  # all agent skills (hot + [V]ault)
/sm auto "scrape a website with stealth"         # finds + invokes /ghostbrowser
/sm auto "create a new issue in PM"              # finds + invokes /plane
/sm load kotlin-patterns                         # loads from vault [V], still works
/sm vault laravel-tdd                            # moves to cold storage (-40 tokens/session)
/sm stats                                        # hot/vault breakdown, RTK savings, ctx savings
```

### [V] — Vault Tag

```
  /kotlin-patterns    [Lang] [V]  Idiomatic Kotlin patterns, coroutines...
  /laravel-tdd        [Lang] [V]  Laravel test-driven development...
  /agent-browser      [Agents]    Ultra-fast browser automation...
```

---

## Token Savings Architecture

```
Request arrives
    │
    ├─ 1. Vault (startup)         0 tokens    ← skills-vault/ not scanned
    │
    ├─ 2. /sm grep idx (rg)      ~0 tokens    ← 54KB TSV, instant
    │
    ├─ 3. /sm ctx_search         ~200-500     ← BM25 semantic fallback
    │
    ├─ 4. RTK hook               60-90% CLI  ← auto-rewrites all Bash
    │     (git/grep/ls/cargo/pytest → compact)
    │
    ├─ 5. context-mode           90% batch   ← ctx_batch_execute
    │     (multi-command batching + summarization)
    │
    ├─ 6. shellfirm              0 tokens    ← safety, blocks destruction
    │     (PreToolUse + MCP — no overhead on safe commands)
    │
    └─ 7. /compact at milestones 100-200K/mo ← session compaction

Combined: 4–5M tokens/month saved (active Claude Code user)
```

---

## Why shellfirm for AI Agents?

AI agents execute shell commands without hesitation. Unlike humans who pause before `rm -rf`, agents don't. shellfirm is the last line of defense:

| Command | Without shellfirm | With shellfirm |
|---------|------------------|----------------|
| `rm -rf node_modules/` | Gone | Shows blast radius, asks to confirm |
| `git push --force origin main` | Overwrites remote | BLOCKED: severity CRITICAL |
| `kubectl delete namespace production` | Production down | BLOCKED + alternative suggested |
| `DROP TABLE users;` | Data lost | Warning + explain_risk MCP tool |

**The math**: AI agents run hundreds of commands per session. One destructive mistake = hours of recovery. shellfirm overhead = near-zero (only fires on flagged patterns).

---

## Recommended Vault Candidates

Skills safe to vault (rarely needed daily):

| Category | Examples | Startup Savings |
|----------|----------|----|
| **Language-specific** | kotlin-*, laravel-*, django-*, springboot-*, swift-* | ~40/skill |
| **Heavy meta tools** | token-budget-advisor (~209 tokens!), prompt-optimizer (~183) | high |
| **Industry/ops** | logistics-*, customs-*, energy-procurement | ~40/skill |
| **Rarely-used PM** | eval-harness, wiring-checkpoint | ~40/skill |

Vault them all at once:

```bash
cd ~/.claude/skills
for item in $(ls | grep -v "^sm\.md$"); do mv "$item" ../skills-vault/; done
python3 ~/.claude/scripts/build-skills-index.py --vault-dir ~/.claude/skills-vault
```

---

## How the Index Works

`~/.claude/skills.idx` — TSV, 5 columns:

```
name          category  description (90 chars max)        path                    vault
─────────────────────────────────────────────────────────────────────────────────────────
agent-browser Agents    Ultra-fast browser automation...  /path/to/SKILL.md       0
kotlin-patt…  Lang      Idiomatic Kotlin patterns...      /path/to/vault/SKILL.md 1
```

Column 5: `0` = hot, `1` = vault. Both are fully discoverable and loadable.

---

## Files

| File | Purpose | Location |
|------|---------|----------|
| `sm.md` | `/sm` skill — the core command | `~/.claude/skills/sm.md` |
| `build-skills-index.py` | Builds `skills.idx` + catalog | `~/.claude/scripts/` |
| `skills-index-session.sh` | Auto-rebuild on SessionStart | `~/.claude/hooks/` |
| `install.sh` | One-command installer | run via curl |
| `CLAUDE_SNIPPET.md` | Copy-paste CLAUDE.md block | reference |
| `RTK.md` | RTK quick reference | reference |
| `~/.claude/skills-vault/` | Cold storage dir | auto-created |

---

## Build Script Options

```bash
python3 build-skills-index.py [options]

  --skills-dir PATH   Hot skills dir (default: ~/.claude/skills)
  --vault-dir PATH    Vault dir (default: ~/.claude/skills-vault)
  --output-dir PATH   Output for idx + catalog (default: ~/.claude)
  --no-vault          Skip vault scan
  --quiet, -q         Suppress output
```

---

## Categories

Auto-assigned from skill name:

`Agents` `AI` `Biz` `Browser` `Content` `Data` `DevOps` `Frontend` `GSD` `Lang` `Media` `Meta` `OpenSpec` `Ops` `PM` `Research` `Security` `Other`

---

## Related

- [RTK — Rust Token Killer](https://rtk-ai.app) — Bash compression layer
- [context-mode](https://github.com/mksglu/context-mode) — Batch execution + summarization
- [shellfirm](https://github.com/kaplanelad/shellfirm) — Safety guardrails
- [claude-session-restore](https://github.com/Supersynergy/claude-session-restore) — Session persistence
- [awesome-agentic-coding](https://github.com/Supersynergy/awesome-agentic-coding) — Curated resources

---

## By

[Supersynergy](https://github.com/Supersynergy) — AI agent infrastructure, open source.
