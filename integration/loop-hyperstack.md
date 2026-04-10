# Hyperstack Autonomous Loop

You are running in `/loop` self-paced mode with the **Hyperstack team**. Each tick processes the `bd` research queue using the cheapest viable agent, with full team-cache deduplication.

## Per-Iteration Playbook

1. **Read Beads queue**: `bd ready --label=research,scrape | head -10`
2. **Pick one ticket.** Start with the highest-priority unblocked item. If none match research/scrape labels, fall back to general `bd ready | head -5`.
3. **Set mission namespace** from the ticket ID:
   ```bash
   export CTS_TEAM_NS="bd-$(echo "$TICKET_ID" | tr ':' '-')"
   ```
4. **Check team cache first**:
   ```bash
   cts-team lookup "$URL"
   ```
   If fresh (<1h), skip the fetch and go straight to extraction.
5. **Dispatch via cheapest agent**:
   - 1 URL, static → call `hyperfetch` inline
   - 2-10 URLs, static → spawn `hyperstack-scraper` subagent
   - JS-heavy → spawn `hyperstack-researcher`
   - Hard-blocked or synthesis → `hyperstack-heavy`
6. **Broadcast progress**: `cts-team broadcast loop-runner tick "{\"ticket\":\"$TICKET_ID\"}"`
7. **Close or advance the ticket**:
   - If complete → `bd close $TICKET_ID`
   - If multi-step → `bd update $TICKET_ID --status in_progress` and note next step in the ticket description
8. **Tick cost report**: Print `cts-team stats` at the end of each iteration.
9. **Schedule next wake**:
   - If `bd ready` has more tickets → 60s (cache-warm)
   - If queue empty → 1800s (30min) — checks back later
   - If Opus budget exceeded → 3600s (1h) — cool-down

## Safety Rails

- **NEVER call WebFetch.** Blocked by PreToolUse hook anyway.
- **NEVER fetch the same URL twice** in one loop session — trust the cache.
- **Stop the loop** if `cts-team stats` shows >$5 spent in the last hour. Broadcast `budget-exceeded` and wait.
- **Skip tickets** that require human decision (labeled `needs-review`).
- **Don't touch shared infra** (database, CI, deploys) — research/extraction only.

## Token Budget per Tick

| Tier | Max Tokens | Use |
|------|-----------|-----|
| Haiku (frontliner) | 2,000 | Default tier, >90% of ticks |
| Sonnet (deep-diver) | 10,000 | Only when JS/auth required |
| Opus (heavy-lifter) | 30,000 | Last resort, 1 invocation per hour max |

Track cumulative spend via `cts-team stats` and refuse to escalate if budget is blown.

## Example Tick

```bash
# 1. Pick ticket
TICKET=$(bd ready --label=research | head -1 | awk '{print $1}')
bd update "$TICKET" --claim

# 2. Get URL from ticket
URL=$(bd show "$TICKET" | grep -oE 'https?://\S+' | head -1)

# 3. Set mission NS
export CTS_TEAM_NS="bd-${TICKET//:/ -}"

# 4. Check cache
CACHED=$(cts-team lookup "$URL")
if [[ -z "$CACHED" || "$CACHED" == "[]" ]]; then
  # 5. Fetch via frontliner
  RESULT=$(hyperfetch "$URL" --stage curl_cffi)
else
  RESULT="$CACHED"
fi

# 6. Extract + close
FIELDS=$(echo "$RESULT" | jq -c '{preview, stage, tokens}')
bd update "$TICKET" --add-note "Extracted: $FIELDS"
bd close "$TICKET"

# 7. Broadcast + stats
cts-team broadcast loop-runner done "{\"ticket\":\"$TICKET\",\"tokens\":$(echo "$RESULT" | jq .tokens)}"
cts-team stats
```

## End-of-Loop Report

Every 10 ticks, emit:
- Tickets closed
- Total tokens used (Hyperstack)
- Tokens avoided vs WebFetch baseline (team savings)
- Cache hit rate
- Any hard-blocked URLs that need manual attention
