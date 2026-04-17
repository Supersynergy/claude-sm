#!/usr/bin/env python3
"""
agent_token_guard.py — Token safety for agent teams
────────────────────────────────────────────────────
CatBoost-based query router: classifies each agent task →
optimal tool (grep/fetch/ctx/read) to minimize tokens.

Usage (agent team):
    from agent_token_guard import TokenGuard
    guard = TokenGuard()
    tool, reason = guard.route("find all import statements in src/")
    # → ('grep', 'code search pattern')

    # Per-agent budget tracking
    guard.record_usage(agent_id="search-agent", tokens_in=500, tokens_out=40, tool="grep")
    guard.report()
"""

import sys, re, json, time
sys.path.insert(0, '/opt/homebrew/lib/python3.12/site-packages')

# ── Tool categories (what an agent team uses) ──────────────────────────
TOOLS = ['grep', 'read', 'web_fetch', 'bash', 'ctx_batch', 'agent_spawn']
# Estimated token cost per tool (out tokens, typical)
TOOL_COST = {
    'grep':        15,    # Grep tool → file list
    'read':        80,    # Read tool → file contents
    'web_fetch':   35,    # smart-fetch → trafilatura
    'bash':       150,    # raw bash → verbose output
    'ctx_batch':   50,    # ctx_batch_execute → indexed
    'agent_spawn': 30000, # spawn Agent → full context copy
}

# ── Feature extraction for query classification ────────────────────────
def featurize_query(query: str) -> list:
    q = query.lower().strip()
    words = q.split()
    return [
        len(q),                                          # 1. length
        len(words),                                      # 2. word count
        int(any(w in q for w in ['find','search','grep','pattern','match','import','function','class','def '])),  # 3. code search intent
        int(any(w in q for w in ['http','url','fetch','scrape','page','website','download'])),  # 4. web fetch intent
        int(any(w in q for w in ['read','open','file','content','show','cat','display'])),      # 5. file read intent
        int(any(w in q for w in ['run','execute','install','build','compile','test','check'])), # 6. bash intent
        int(any(w in q for w in ['research','investigate','explore','summarize','analyze'])),   # 7. agent-level intent
        int(any(w in q for w in ['2+','multiple','batch','many','all','every','across'])),      # 8. batch intent
        int('?' in q),                                   # 9. question
        int(re.search(r'\*|regex|\.\*|\[', q) is not None),  # 10. pattern/glob
        sum(c.isupper() for c in query) / max(len(query), 1), # 11. caps ratio
        int(any(w in q for w in ['list','ls','dir','tree','files'])),  # 12. listing intent
    ]

# ── Rule-based router (no model needed for obvious cases) ─────────────
RULES = [
    # (pattern, tool, reason)  — ordered by specificity, first match wins
    # ctx_batch first: catches research/multi/agent before cheaper rules fire
    (r'(research|investigate|analyz.+ multiple|summariz.+ pages|compare \d+|5\+|across .+ sources|multi.source)',
                                                                                    'ctx_batch', 'multi-source research'),
    (r'(spawn.{0,10}agent|create.{0,10}agent|delegate|subagent|agent.{0,5}team|hand.{0,5}off to)',
                                                                                    'ctx_batch', 'agent→ctx_batch (30k→500t)'),
    # web fetch: URL patterns or explicit fetch words
    (r'(https?://|\.com|\.io|\.org|fetch|scrape|download|webpage|website|page from|competitor|pricing page|pdf report)',
                                                                                    'web_fetch', 'web content'),
    # bash: explicit shell operations
    (r'\b(run |execute|build|compile|install|git |cargo|npm|pnpm|pytest|make |docker)\b',
                                                                                    'bash', 'shell command'),
    # grep: code search — before read to catch "list all *.py files"
    (r'(grep|find all|list all|search for|pattern|import|function|class |def |endpoint|todo|fixme|rg |matching \*)',
                                                                                    'grep', 'code search'),
    # read: file content access (specific file by name, not listing)
    (r'(read the|open the|show the|display the|cat the|content of|config file|current .+file|\.md file|\.json file)',
                                                                                    'read', 'file content'),
]

def route_query(query: str) -> tuple:
    """Returns (tool, reason, estimated_tokens)."""
    q = query.lower()
    for pattern, tool, reason in RULES:
        if re.search(pattern, q):
            # agent_spawn always remapped to ctx_batch (30,000t → 500t)
            if tool == 'agent_spawn':
                tool = 'ctx_batch'
                reason = 'agent→ctx_batch (30k→500t saved)'
            return tool, reason, TOOL_COST[tool]
    # Default: grep is cheapest for unknown
    return 'grep', 'default: cheapest unknown', TOOL_COST['grep']

# ── CatBoost router (optional, trained on real session logs) ──────────
class CatBoostRouter:
    """Optional ML router. Falls back to rule-based if model not found."""
    def __init__(self, model_path: str = None):
        self.model = None
        if model_path:
            try:
                from catboost import CatBoostClassifier
                m = CatBoostClassifier()
                m.load_model(model_path)
                self.model = m
            except Exception:
                pass

    def predict(self, query: str) -> tuple:
        if self.model is None:
            return route_query(query)
        feats = featurize_query(query)
        pred = int(self.model.predict([feats])[0])
        tool = TOOLS[pred]
        return tool, 'ml_router', TOOL_COST[tool]

# ── Per-agent budget tracker ───────────────────────────────────────────
class TokenBudget:
    def __init__(self, budget: int = 50_000):
        self.budget = budget
        self.used = 0
        self.log = []

    def record(self, agent_id: str, tool: str, tokens_in: int, tokens_out: int, ms: int = 0):
        total = tokens_in + tokens_out
        self.used += total
        self.log.append({
            'agent': agent_id, 'tool': tool,
            'in': tokens_in, 'out': tokens_out,
            'total': total, 'ms': ms,
            'ts': time.time()
        })

    @property
    def remaining(self) -> int:
        return self.budget - self.used

    @property
    def pct_used(self) -> float:
        return self.used / self.budget * 100

    def should_block(self, tool: str) -> bool:
        """Block expensive tools based on budget thresholds."""
        # agent_spawn ALWAYS blocked — remapped at route() level, but guard as safety net
        if tool == 'agent_spawn':
            return True
        # >80% used: block bash
        if self.pct_used >= 80 and tool == 'bash':
            return True
        # >95% used: block everything except grep
        if self.pct_used >= 95 and tool not in ('grep',):
            return True
        return False

    def report(self) -> dict:
        by_tool = {}
        for e in self.log:
            t = e['tool']
            by_tool.setdefault(t, {'calls': 0, 'tokens': 0, 'ms': 0})
            by_tool[t]['calls'] += 1
            by_tool[t]['tokens'] += e['total']
            by_tool[t]['ms'] += e['ms']
        return {
            'budget': self.budget,
            'used': self.used,
            'remaining': self.remaining,
            'pct_used': round(self.pct_used, 1),
            'by_tool': by_tool,
        }

# ── Main guard: combines router + budget ─────────────────────────────
class TokenGuard:
    """
    Drop-in guard for agent teams.

    Example:
        guard = TokenGuard(budget=100_000)
        tool, reason, cost = guard.route("find all TODO comments")
        if guard.budget.should_block(tool):
            tool = 'grep'  # force cheap alternative
        # ... run tool ...
        guard.record('agent-1', tool, tokens_in=200, tokens_out=15, ms=9)
        print(guard.report_summary())
    """
    def __init__(self, budget: int = 100_000, model_path: str = None):
        self.router = CatBoostRouter(model_path)
        self.budget = TokenBudget(budget)

    def route(self, query: str) -> tuple:
        """Returns (tool, reason, estimated_tokens)."""
        tool, reason, est = self.router.predict(query)
        if self.budget.should_block(tool):
            tool, reason, est = 'grep', 'budget_guard: forced cheap', TOOL_COST['grep']
        return tool, reason, est

    def record(self, agent_id: str, tool: str, tokens_in: int, tokens_out: int, ms: int = 0):
        self.budget.record(agent_id, tool, tokens_in, tokens_out, ms)

    def report_summary(self) -> str:
        r = self.budget.report()
        lines = [
            f"Budget: {r['used']:,}/{r['budget']:,} tokens ({r['pct_used']}% used)",
            f"Remaining: {r['remaining']:,}",
            "By tool:"
        ]
        for tool, stats in sorted(r['by_tool'].items(), key=lambda x: -x[1]['tokens']):
            lines.append(f"  {tool:<14} {stats['calls']} calls  {stats['tokens']:>6} tokens  {stats['ms']}ms")
        return '\n'.join(lines)

# ── CLAUDE.md injection helper ────────────────────────────────────────
ROUTING_TABLE = """
## Agent Team Token-Safety Routing

| Query type          | Correct tool      | Est. tokens | BLOCKED when budget <20% |
|---------------------|-------------------|-------------|--------------------------|
| Code search/pattern | Grep tool         | 15t         | never                    |
| File content        | Read tool         | 80t         | never                    |
| Web HTML/JSON       | smart-fetch       | 35t         | never                    |
| Shell command       | Bash (<20 lines)  | 150t        | yes → Grep               |
| 2+ commands/URLs    | ctx_batch_execute | 50t         | no (saves tokens)        |
| Research/delegate   | ctx_batch_execute | 500t        | yes → ctx_search         |
| Spawn subagent      | BLOCKED           | 30,000t     | always                   |

Budget guard activates at 80% usage: blocks bash + agent_spawn, forces Grep/Read/ctx.
"""

if __name__ == '__main__':
    print("── TokenGuard demo ──")
    guard = TokenGuard(budget=10_000)

    queries = [
        "find all import statements in src/",
        "fetch https://example.com and summarize",
        "read the config file",
        "run npm install and check for errors",
        "research 5 competitor websites and compare pricing",
        "spawn agent to handle database migration",
        "grep for TODO comments across all files",
        "show me the content of README.md",
    ]

    print(f"\n{'Query':<50} {'Tool':<14} {'Reason':<25} {'Est.tokens':>10}")
    print("-"*100)
    for q in queries:
        tool, reason, est = guard.route(q)
        guard.record('demo-agent', tool, tokens_in=est//2, tokens_out=est//2, ms=10)
        print(f"{q[:49]:<50} {tool:<14} {reason:<25} {est:>10}")

    print(f"\n{guard.report_summary()}")
    print(ROUTING_TABLE)
