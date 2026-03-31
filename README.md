# claude-sm — Skill Manager for Claude Code

> **On-demand skill discovery with ~0 token overhead.**
> Find and load any of your Claude Code skills without polluting context.

[![Claude Code](https://img.shields.io/badge/Claude_Code-2.1+-blueviolet)](https://claude.ai/code)
[![Skills](https://img.shields.io/badge/skills-320+-blue)](https://github.com/Supersynergy/claude-sm)
[![Token cost](https://img.shields.io/badge/discovery_cost-~0_tokens-brightgreen)](https://github.com/Supersynergy/claude-sm)

## The Problem

Claude Code loads skill metadata for **every skill at startup** — with 300+ skills that's ~160K tokens just for discovery. And if you want to actually read a skill, you need to know the exact name.

## The Solution

`/sm` — a three-layer lazy loading system:

| Layer | Method | Tokens | Speed |
|-------|--------|--------|-------|
| **1. Grep** | `rg` on `skills.idx` TSV | ~0 | instant |
| **2. Semantic** | `ctx_search` on catalog | ~200-500 | fast |
| **3. Load** | `Read()` one skill file | ~500-5K | on-demand |

All 320 skills in a 54KB grep-able TSV. Semantic search via context-mode BM25. Skills are **never all loaded at once**.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Supersynergy/claude-sm/main/install.sh | bash
```

Or manually:

```bash
cp sm.md ~/.claude/skills/sm.md
cp build-skills-index.py ~/.claude/scripts/
cp skills-index-session.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/skills-index-session.sh
python3 ~/.claude/scripts/build-skills-index.py
```

## Usage

```
/sm search <query>     — grep search, instant, 0 tokens
/sm list [category]    — browse by category
/sm load <name>        — read full skill content
/sm auto <intent>      — find best skill and invoke it
/sm rebuild            — regenerate index from skills dir
```

### Examples

```
/sm search plane        → finds /plane skill instantly
/sm search browser      → finds agent-browser, ghostbrowser, ...
/sm list Agents         → all agent skills
/sm auto "I need to scrape a website"  → finds + invokes /scrape
/sm load agent-browser  → loads full agent-browser skill
```

## Auto-Trigger

`/sm` auto-invokes when you ask:
- *"what skill..."* / *"which command..."*
- *"can you..."* / *"do you have a skill for..."*
- anything mentioning a specific capability

## Files

| File | Purpose |
|------|---------|
| `sm.md` | The `/sm` skill (place in `~/.claude/skills/`) |
| `build-skills-index.py` | Builds `skills.idx` + `skills-catalog.md` |
| `skills-index-session.sh` | SessionStart hook, auto-rebuilds if missing |
| `install.sh` | One-command installer |

## How the Index Works

`~/.claude/skills.idx` — TSV format, one skill per line:
```
name    category    description (90 chars)    /absolute/path/to/skill.md
```

`~/.claude/skills-catalog.md` — Markdown by category, indexed with context-mode BM25 for semantic search.

Categories: `Agents`, `Biz`, `Browser`, `Data`, `DevOps`, `GSD`, `Lang`, `Media`, `Meta`, `OpenSpec`, `PM`, `Security`, `Other`

## Token Budget

| Operation | Tokens |
|-----------|--------|
| `/sm search query` | ~0 (grep only) |
| `/sm list` | ~0 (grep only) |
| `/sm auto intent` (semantic) | ~200-500 |
| `/sm load name` | ~500-5K (one skill) |
| All 320 skills loaded | ~160K (**avoid!**) |

## Requirements

- Claude Code 2.1+
- `ripgrep` (`rg`) — for index search
- Python 3.8+ — for index building
- `context-mode` MCP — optional, for semantic search

## By

[Supersynergy](https://github.com/Supersynergy) — AI agent infrastructure, open source.
