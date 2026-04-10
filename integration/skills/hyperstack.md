---
name: hyperstack
description: Extreme token savings via 4-stage fetch chain (curl_cffi→camoufox→domshell→browser) + catboost pre-filter + gemma local summarizer + SurrealDB team cache. Auto-use for ALL web fetches, DOM navigation, and multi-dev scraping. Targets 10,000x effective Claude Code sessions per dollar.
effort: low
---

# Hyperstack — Always-On Token Savings

You have access to the **Hyperstack** — a 4-stage escalation chain that makes web fetching ~75x to ~10,000x cheaper than raw WebFetch. **You must use it.**

## Hard Rules

1. **NEVER call `WebFetch` directly.** Always use `hyperfetch` via Bash.
2. **NEVER run `curl`/`wget`/`playwright`/`chrome-devtools` for scraping.** Route through `hyperfetch`.
3. **Always check the team cache first** via `cts-team lookup <url>`.
4. **DOM navigation:** use `dsh` (DOMShell REPL), never `playwright` snapshots.
5. **Bulk fetches (>5 urls):** delegate to the `hyperstack-scraper` subagent.
6. **JS-heavy research:** delegate to `hyperstack-researcher`.
7. **Unknown/complex targets:** delegate to `hyperstack-heavy` (Opus 4.6).

## Primary Commands

```bash
# Single URL, full chain, team-cached, summarized
hyperfetch https://example.com

# Force specific stage cap
hyperfetch https://monday.com --stage camoufox

# Custom team namespace (multi-dev dedupe)
hyperfetch https://example.com --team-ns research-q2

# Skip cache (forced refresh)
hyperfetch https://example.com --no-cache

# Skip gemma summarizer (raw body)
hyperfetch https://example.com --no-summary
```

Output is ALWAYS single-line JSON:
```json
{"stage":"curl_cffi","status":200,"url":"...","bytes":45234,"tokens":120,"team_ns":"default","preview":"..."}
```

The `preview` is a gemma-summarized 5-bullet version. The full body lives in the SurrealDB team cache — retrieve details via `ctx_search` on the indexed content.

## DOM Navigation (Stateful)

```bash
dsh --session <name> goto https://monday.com/boards
dsh --session <name> ls "main"                       # list children of selector
dsh --session <name> read "h1.board-title"           # single element text
dsh --session <name> click "button.new-item"         # interact
dsh --session <name> eval "document.querySelectorAll('.row').length"
```

Each command returns 1 JSON line. **Never** dump full HTML.

## Team Cache Management

```bash
cts-team lookup <url>              # check if team already fetched
cts-team stats                     # session savings
cts-team broadcast <agent> <event> # push to team bus
cts-team tail 1h                   # recent events
```

## Subagents (April 2026 Roles)

Delegate with `Task`:

| Subagent | Model | Stage Cap | Use For |
|----------|-------|-----------|---------|
| `hyperstack-scraper` | Haiku 4.5 | curl_cffi | Bulk static fetches (>5 urls) |
| `hyperstack-researcher` | Sonnet 4.6 | camoufox | JS-heavy sites, login flows |
| `hyperstack-heavy` | Opus 4.6 | browser | Unknown targets, complex DOM reasoning |

Example:
```
Task({
  subagent_type: "hyperstack-scraper",
  description: "Bulk fetch 20 product pages",
  prompt: "Fetch these 20 URLs via hyperfetch, return a compact JSON array with {url,title,price} for each. Use --team-ns product-scan.\n\nURLs:\n- https://..."
})
```

## Local ML Layer

- `cts-ml --classify` — catboost filter, drops noise/boilerplate (5ms, 0 tokens)
- `cts-gemma --summarize` — Ollama gemma3:4b, 5-bullet extraction (200ms, 0 tokens)

These run automatically inside `hyperfetch`. You don't call them directly unless you have raw output from another tool that needs filtering.

## Cost Math (Why This Matters)

| Scenario | Without Hyperstack | With Hyperstack | Factor |
|----------|--------------------|-----------------| -------|
| Single scrape | 15,000 tok | 200 tok | 75x |
| 10-dev team | 150,000 tok | 200 tok | 750x |
| + catboost filter | — | 40 tok | 3,666x |
| + gemma gate | — | 2 tok | ~73,333x |

**Target**: 10,000x effective Claude Code experience per dollar. Hit it by:
- Always caching into the team namespace
- Delegating bulk work to subagents (smaller models, parallel)
- Using `dsh` instead of `WebFetch`/`playwright`
- Trusting `cts-ml` + `cts-gemma` to drop noise before it hits your context

## Failure Modes

- `hyperfetch` returns `{"stage":"failed"}` → the target is hard-blocked. Escalate to `hyperstack-heavy` subagent with `--stage browser` and stealth patches.
- Team cache returns stale data → use `--no-cache` to force refresh.
- Ollama not running → gemma falls back to extractive summarization (still saves tokens).
- curl_cffi patches missing → chain auto-escalates to camoufox.

**Anti-pattern**: Calling `WebFetch` "just for this one URL". The fixed cost of the Hyperstack call is <100ms. The fixed token cost of WebFetch is 5k-20k. Always hyperfetch.
