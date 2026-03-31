# Claude Skill Manager & Token Saver

> **Discover and load 300+ Claude Code skills with ~0 token overhead.**
> Three-layer lazy loading: grep index → semantic search → on-demand file read.
> Vault pattern: cold-store rarely-used skills for 0 startup cost.
> Never loads all skills at once. Saves 100K–160K tokens per session.

[![Claude Code](https://img.shields.io/badge/Claude_Code-2.1+-blueviolet)](https://claude.ai/code)
[![Token savings](https://img.shields.io/badge/token_savings-up_to_160K_per_session-brightgreen)](#token-savings)
[![ripgrep](https://img.shields.io/badge/powered_by-ripgrep_15+-orange)](https://github.com/BurntSushi/ripgrep)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## The Problem

Claude Code loads skill **metadata for every skill at startup**. With 300+ skills that's ~160K tokens burned before you even start working. And finding the right skill means either remembering exact names or loading all files.

## The Solution

Two complementary systems:

### 1. Vault Pattern — Startup Token Elimination

```
~/.claude/skills/        = HOT  (auto-loaded at startup, ~40 tokens/skill)
~/.claude/skills-vault/  = COLD (never auto-loaded, 0 startup tokens)
```

Move skills you don't use daily to the vault. They stay **fully discoverable and loadable** — just no startup cost.

```bash
/sm vault kotlin-patterns    # → cold storage (saves ~40 tokens/session)
/sm vault laravel-tdd        # → cold storage
/sm unvault kotlin-patterns  # → restore to hot when needed
```

### 2. Three-Layer Lazy Loading — Discovery for Free

`/sm` — instant search without loading any skill content:

| Layer | Method | Tokens | Speed |
|-------|--------|--------|-------|
| **1. Grep** | `rg` on 54KB `skills.idx` TSV | **~0** | <20ms |
| **2. Semantic** | `ctx_search` BM25 on catalog | ~200–500 | fast |
| **3. Load** | `Read()` one matched skill file | ~500–5K | on-demand |
| ~~All skills~~ | ~~Load everything~~ | ~~160K+~~ | ~~never~~ |

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Supersynergy/claude-sm/main/install.sh | bash
```

Or manually:
```bash
cp sm.md ~/.claude/skills/sm.md
cp build-skills-index.py ~/.claude/scripts/
cp skills-index-session.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/skills-index-session.sh ~/.claude/scripts/build-skills-index.py
mkdir -p ~/.claude/skills-vault
python3 ~/.claude/scripts/build-skills-index.py
```

**Requirements:** Claude Code 2.1+, Python 3.8+, [ripgrep](https://github.com/BurntSushi/ripgrep) (`brew install ripgrep`)

---

## Usage

```
/sm search <query>     — instant keyword search (~0 tokens)
/sm list [category]    — browse by category (shows hot + vault)
/sm load <name>        — read full skill content (works for vault too)
/sm auto <intent>      — find best skill and invoke it
/sm vault <name>       — move skill to cold storage (0 startup cost)
/sm unvault <name>     — restore vault skill to hot
/sm stats              — portfolio overview + token savings
/sm tokens             — token saving cheatsheet
/sm rebuild            — regenerate index after adding/moving skills
```

### Examples

```bash
/sm search plane           # → finds /plane (Plane.so PM skill)
/sm search browser         # → finds agent-browser, ghostbrowser, ...
/sm list Agents            # → all agent skills (hot + vault [V])
/sm list Lang              # → all language skills (many in vault)
/sm auto "scrape a website with stealth"  # → finds + invokes /ghostbrowser
/sm auto "create a new issue in PM"       # → finds + invokes /plane
/sm load agent-browser     # → loads full 200-line skill content
/sm load kotlin-patterns   # → loads from vault [V], still works!
/sm vault laravel-tdd      # → moves to cold storage, saves ~40 tokens/session
/sm stats                  # → shows hot/vault breakdown, RTK savings
```

### [V] Tag

Vault skills are shown with `[V]` in all search and list output:

```
  /kotlin-patterns         [Lang] [V]  Idiomatic Kotlin patterns, coroutines...
  /laravel-tdd             [Lang] [V]  Laravel test-driven development...
  /agent-browser           [Agents]    Ultra-fast browser automation...
```

---

## Auto-Invocation

`/sm` auto-triggers when you say:

- *"what skill can..."* / *"which command..."*
- *"can you scrape / deploy / test..."*
- *"do you have a skill for..."*
- *"I need to..."* + any capability keyword
- *"show me skills"* / *"list skills"*

---

## Token Savings Architecture

```
Request arrives
    │
    ├─ 1. Vault (startup)      0 tokens    ← cold skills never load
    │     (skills-vault/ not scanned)
    │
    ├─ 2. /sm grep idx (rg)   ~0 tokens    ← this tool
    │
    ├─ 3. /sm ctx_search      ~200-500      ← this tool (semantic fallback)
    │
    ├─ 4. RTK hook            60-90% CLI    ← if rtk installed
    │     (rewrites git/grep/ls/curl → compact)
    │
    ├─ 5. context-mode        virtualize    ← large output management
    │     (ctx_index + ctx_search)
    │
    └─ 6. strategic compact   100-200K/mo   ← /compact at milestones
```

**Combined potential: 4–5M tokens/month saved** (active Claude Code user)

---

## How the Index Works

`~/.claude/skills.idx` — TSV, 5 columns, one skill per line, grep-able:
```
name          category  description (90 chars max)        path                    vault
─────────────────────────────────────────────────────────────────────────────────────────
agent-browser Agents    Ultra-fast browser automation...  /path/to/SKILL.md       0
kotlin-patt…  Lang      Idiomatic Kotlin patterns...      /path/to/vault/SKILL.md 1
plane         PM        Plane.so project management...    /path/to/plane.md       0
```

Column 5: `0` = hot (in `~/.claude/skills/`), `1` = vault (in `~/.claude/skills-vault/`)

`~/.claude/skills-catalog.md` — Markdown by category, indexed with context-mode BM25:
```markdown
## Agents (16 hot + 3 vault = 19 total)
- `/agent-browser` — Ultra-fast browser automation...
- `/kotlin-patterns` [V] — Idiomatic Kotlin patterns...
```

---

## Recommended Vault Candidates

Skills that are safe to vault (rarely needed daily, high token cost at startup):

| Category | Examples | Savings |
|----------|----------|---------|
| **Language-specific** | kotlin-*, laravel-*, django-*, springboot-*, swift-*, android-* | ~40/skill |
| **Heavy meta tools** | token-budget-advisor (~209 tokens!), prompt-optimizer (~183) | high |
| **Industry/ops** | logistics-*, customs-*, energy-procurement, quality-nonconformance | ~40/skill |
| **Rarely-used PM** | eval-harness, benchmark, wiring-checkpoint | ~40/skill |

Move them all at once:
```bash
/sm vault kotlin-patterns
/sm vault laravel-tdd
/sm vault django-patterns
/sm vault swift-actor-persistence
# etc. — /sm rebuild when done
```

---

## Files

| File | Purpose | Install Location |
|------|---------|--------------------|
| `sm.md` | `/sm` skill (slash command) | `~/.claude/skills/sm.md` |
| `build-skills-index.py` | Builds `skills.idx` + catalog (hot + vault) | `~/.claude/scripts/` |
| `skills-index-session.sh` | Auto-rebuild SessionStart hook | `~/.claude/hooks/` |
| `install.sh` | One-command installer | run via curl |
| `~/.claude/skills-vault/` | Cold storage dir (created by installer) | auto-created |

---

## Build Script Options

```bash
python3 build-skills-index.py [options]

Options:
  --skills-dir PATH   Hot skills directory (default: ~/.claude/skills)
  --vault-dir PATH    Vault directory (default: ~/.claude/skills-vault)
  --output-dir PATH   Output dir for idx + catalog (default: ~/.claude)
  --no-vault          Skip vault directory scan
  --quiet, -q         Suppress output
```

Supports any skills directory layout — not just `~/.claude/skills`. Works with custom skill repositories.

---

## Categories

Auto-assigned from skill name. Expand `CATS` dict in `build-skills-index.py` for custom mappings:

`Agents` `AI` `Biz` `Browser` `Content` `Data` `DevOps` `Frontend` `GSD` `Lang` `Media` `Meta` `OpenSpec` `Ops` `PM` `Research` `Security` `Other`

---

## Contributing

- Add new skills: place `.md` files with `name:` + `description:` frontmatter in `~/.claude/skills/`
- Run `/sm rebuild` to re-index
- Move cold skills: `/sm vault <name>` then `/sm rebuild`
- Improve categories: extend `CATS` dict in `build-skills-index.py`

---

## By

[Supersynergy](https://github.com/Supersynergy) — AI agent infrastructure, open source.

Related: [claude-session-restore](https://github.com/Supersynergy/claude-session-restore) · [awesome-agentic-coding](https://github.com/Supersynergy/awesome-agentic-coding)
