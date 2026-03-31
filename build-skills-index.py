#!/usr/bin/env python3
"""
Claude Skill Manager & Token Saver — Index Builder
Builds skills.idx (TSV) and skills-catalog.md from hot + vault dirs.

Usage:
  python3 build-skills-index.py [--skills-dir PATH] [--vault-dir PATH] [--output-dir PATH] [--quiet]

The vault dir is NOT auto-loaded by Claude Code — skills there are cold-stored
and only loaded on demand via /sm load <name>. Search still finds them (marked [V]).
"""
import argparse, sys
from pathlib import Path
from collections import defaultdict

# ── Category keyword map (longer/specific keys checked first) ────────────────
CATS = {
    # Browser / Scraping
    'agent-browser':'Browser', 'ghostbrowser':'Browser', 'scrapedeep':'Browser',
    'scrape':'Browser', 'crawl':'Browser', 'browserautomation':'Browser',
    'browser-qa':'Browser',

    # GSD / OpenSpec
    'gsd':'GSD', 'opsx':'OpenSpec', 'openspec':'OpenSpec', 'spec-build':'OpenSpec',

    # Languages & Frameworks (many in vault)
    'rust-':'Lang', 'rust_':'Lang', 'python-':'Lang', 'kotlin-':'Lang',
    'swift-':'Lang', 'java-':'Lang', 'golang-':'Lang', 'go-':'Lang',
    'go_':'Lang', 'cpp-':'Lang', 'perl-':'Lang', 'django-':'Lang',
    'laravel-':'Lang', 'spring':'Lang', 'typescript':'Lang', 'android-':'Lang',
    'compose-multiplatform':'Lang', 'kotlin-ktor':'Lang', 'swiftui':'Lang',
    'jpa-':'Lang', 'gradle-':'Lang', 'bun-':'Lang',

    # Agents / Orchestration
    'devfleet':'Agents', 'orchestrat':'Agents', 'autonomous':'Agents',
    'claude-devfleet':'Agents', 'jarvis':'Agents', 'dmux':'Agents',
    'nanoclaw':'Agents', 'claw':'Agents', 'agent':'Agents',
    'multi-':'Agents', 'team-':'Agents',

    # Business / Revenue / Intel
    'thinkrich':'Biz', 'revshare':'Biz', 'outreach':'Biz', 'intel':'Biz',
    'revenue':'Biz', 'market-':'Biz', 'cold-email':'Biz', 'lead-':'Biz',
    'investor':'Biz', 'trade-':'Biz', 'crisis':'Biz', 'predictive':'Biz',
    'supply-demand':'Biz', 'time-arbitrage':'Biz', 'daily-briefing':'Biz',
    'daily-intel':'Biz', 'hn-intel':'Biz', 'reddit-intel':'Biz',
    'profit-':'Biz', 'monetize':'Biz', 'gumroad':'Biz', 'partner-':'Biz',
    'sprint-':'Biz', 'proposal':'Biz',

    # Data / DB / Knowledge
    'knowledge':'Data', 'postgres':'Data', 'clickhouse':'Data', 'database':'Data',
    'surrealdb':'Data', 'sdb-':'Data', 'kb-':'Data', 'chats':'Data',
    'shopdb':'Data', 'videodb':'Data',
    'db':'Data',

    # DevOps / Infra
    'docker':'DevOps', 'deploy':'DevOps', 'commit':'DevOps',
    'git-':'DevOps', 'github':'DevOps', 'pm2':'DevOps', 'stacks':'DevOps',
    'canary':'DevOps',

    # Project Management / Quality
    'plane':'PM', 'plan':'PM', 'verify':'PM', 'debug':'PM',
    'tdd-':'PM', 'tdd':'PM', 'test':'PM', 'review':'PM', 'audit':'PM',
    'blueprint':'PM', 'checkpoint':'PM', 'eval':'PM', 'refactor':'PM',
    'quality':'PM', 'verification':'PM', 'spec':'PM', 'diet':'PM',

    # Media / Content
    'video':'Media', 'fal-ai':'Media', 'youtube':'Media',
    'article':'Content', 'content-engine':'Content', 'crosspost':'Content',
    'liquid-glass':'Content',

    # Security / Privacy
    'security':'Security', 'dsgvo':'Security', 'privacy':'Security',
    'visa-doc':'Security', 'secret':'Security',

    # AI / LLM Tools
    'claude-api':'AI', 'mcp-server':'AI', 'cost-aware-llm':'AI',
    'token-budget':'AI', 'prompt':'AI', 'foundation-models':'AI',
    'exa-search':'AI', 'ai-first':'AI', 'ai-regression':'AI',
    'iterative-retrieval':'AI', 'regex-vs-llm':'AI',

    # Meta / Skill System
    'skill':'Meta', 'continuous-learning':'Meta', 'strategic-compact':'Meta',
    'context-budget':'Meta', 'configure-ecc':'Meta', 'instinct':'Meta',
    'benchmark':'Meta', 'eval-harness':'Meta', 'harness':'Meta',
    'session':'Meta', 'search-':'Meta',

    # Research
    'deep-research':'Research', 'grep-app':'Research',
    'github-trending':'Research', 'research':'Research',
    'search-first':'Research',

    # Frontend / UI
    'frontend':'Frontend', 'newwebsite':'Frontend', 'newshop':'Frontend',
    'frontend-slides':'Frontend',

    # Logistics / Supply Chain (usually vaulted)
    'logistics':'Ops', 'carrier':'Ops', 'customs':'Ops', 'returns':'Ops',
    'inventory':'Ops', 'production-sched':'Ops', 'energy-':'Ops',
    'quality-nonconformance':'Ops', 'supply-chain':'Ops',
}

SKIP_DIRS  = {'.github','documentation','docs','.git','__pycache__',
              'node_modules','.venv','venv','dist','build','target',
              'ISSUE_TEMPLATE','workflows','ecc2','examples','assets',
              'contexts','commands'}
SKIP_FILES = {'README.md','CHANGELOG.md','CODE_OF_CONDUCT.md','CONTRIBUTING.md',
              'LICENSE.md','INSTALL.md','ARCHITECTURE.md','QUICK_REFERENCE.md',
              'SECURITY.md','AGENTS.md','INSTALLATION_GUIDE.md',
              'RALPHLOOP-SKILLS-README.md','PROJECT_STACK_QUICKREF.md',
              'KPI_ALERTS_QUICK_START.txt'}


def get_cat(name: str) -> str:
    n = name.lower()
    for k, v in sorted(CATS.items(), key=lambda x: -len(x[0])):
        if n.startswith(k) or (len(k) > 3 and k in n):
            return v
    return 'Other'


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter, handling multi-line block scalars (>- and |-)."""
    fm: dict = {}
    lines = content.split('\n')
    if not lines or lines[0].strip() != '---':
        return fm
    in_fm = False
    current_key = None
    current_val_lines = []
    block_scalar = False

    for line in lines[1:51]:  # skip first ---, read up to 50 lines
        s = line.strip()
        if s == '---':
            if current_key and block_scalar:
                fm[current_key] = ' '.join(current_val_lines).strip()
            break

        if not in_fm:
            in_fm = True

        if block_scalar:
            if line.startswith('  ') or line.startswith('\t') or not line.strip():
                current_val_lines.append(s)
                continue
            else:
                fm[current_key] = ' '.join(current_val_lines).strip()
                current_key = None
                block_scalar = False
                current_val_lines = []

        if ':' in s and not s.startswith('-'):
            key, _, val = s.partition(':')
            key = key.strip()
            val = val.strip()
            if val in ('>-', '|-', '>', '|', '>+', '|+'):
                current_key = key
                block_scalar = True
                current_val_lines = []
            elif val:
                fm[key] = val
                current_key = key

    if current_key and block_scalar and current_val_lines:
        fm[current_key] = ' '.join(current_val_lines).strip()

    return fm


def is_valid(fm: dict) -> bool:
    return bool(fm.get('name') and fm.get('description'))


def should_skip(f: Path) -> bool:
    for part in f.parts:
        if part in SKIP_DIRS:
            return True
    if '.github' in str(f):
        return True
    if f.name in SKIP_FILES:
        return True
    return False


def scan_dir(skills_dir: Path, entries: defaultdict, seen: set, vault: bool) -> int:
    """Scan a directory and add skills to entries. Returns skipped count."""
    skipped = 0
    for f in sorted(skills_dir.rglob('*.md')):
        if should_skip(f):
            skipped += 1
            continue
        try:
            content = f.read_text(errors='ignore')
            fm = parse_frontmatter(content)
            if not is_valid(fm):
                skipped += 1
                continue
            name = fm['name']
            if name in seen:
                continue
            # Trim description to 90 chars for compact index
            desc = fm['description'].replace('\n', ' ').replace('\r', '').strip()[:90]
            seen.add(name)
            # Tag vault skills with [V] in category column
            cat = get_cat(name) + ('/V' if vault else '')
            entries[get_cat(name)].append((name, desc, str(f), vault))
        except Exception:
            skipped += 1
    return skipped


def build(skills_dir: Path, vault_dir: Path | None, out_dir: Path):
    entries = defaultdict(list)
    seen: set = set()
    skipped = 0

    # 1. Scan hot skills (auto-loaded by CC)
    skipped += scan_dir(skills_dir, entries, seen, vault=False)

    # 2. Scan vault skills (cold-stored, NOT auto-loaded by CC)
    if vault_dir and vault_dir.exists():
        skipped += scan_dir(vault_dir, entries, seen, vault=True)

    # TSV index: name TAB cat TAB desc TAB path TAB vault(0/1)
    idx_lines = []
    for cat, skills in entries.items():
        for name, desc, path, is_vault in skills:
            v_flag = '1' if is_vault else '0'
            idx_lines.append(f"{name}\t{cat}\t{desc.replace(chr(9),' ')}\t{path}\t{v_flag}")
    idx_lines.sort()
    (out_dir / 'skills.idx').write_text('\n'.join(idx_lines) + '\n')

    # Markdown catalog with ## Category headers
    md = ['# Claude Skills Catalog\n',
          '> Hot skills load at startup. [V] = Vault (on-demand only, saves tokens).\n']
    for cat in sorted(entries.keys()):
        skills = sorted(entries[cat])
        hot = [s for s in skills if not s[3]]
        cold = [s for s in skills if s[3]]
        md.append(f'\n## {cat} ({len(hot)} hot + {len(cold)} vault = {len(skills)} total)\n')
        for name, desc, _, is_vault in hot:
            md.append(f'- `/{name}` — {desc}')
        for name, desc, _, is_vault in cold:
            md.append(f'- `/{name}` [V] — {desc}')
    (out_dir / 'skills-catalog.md').write_text('\n'.join(md))

    return sum(len(v) for v in entries.values()), skipped, entries


def main():
    p = argparse.ArgumentParser(description='Build Claude skills index (hot + vault)')
    p.add_argument('--skills-dir', default=str(Path.home()/'.claude/skills'),
                   help='Hot skills dir (auto-loaded by Claude Code)')
    p.add_argument('--vault-dir', default=str(Path.home()/'.claude/skills-vault'),
                   help='Vault dir (cold storage, NOT auto-loaded — saves tokens)')
    p.add_argument('--output-dir', default=str(Path.home()/'.claude'))
    p.add_argument('--quiet', '-q', action='store_true')
    p.add_argument('--no-vault', action='store_true', help='Skip vault dir scan')
    args = p.parse_args()

    skills_dir = Path(args.skills_dir)
    vault_dir  = None if args.no_vault else Path(args.vault_dir)
    out_dir    = Path(args.output_dir)

    if not skills_dir.exists():
        print(f'ERROR: Skills dir not found: {skills_dir}', file=sys.stderr)
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)

    total, skipped, entries = build(skills_dir, vault_dir, out_dir)

    if not args.quiet:
        hot_total  = sum(1 for skills in entries.values() for *_, v in skills if not v)
        vault_total = sum(1 for skills in entries.values() for *_, v in skills if v)
        print(f'Built: {total} skills indexed ({hot_total} hot + {vault_total} vault) | {skipped} skipped')
        print(f'  Hot dir:   {skills_dir}')
        if vault_dir and vault_dir.exists():
            print(f'  Vault dir: {vault_dir}')
        print(f'  Output:    {out_dir}/skills.idx + skills-catalog.md')
        print()
        for cat, skills in sorted(entries.items(), key=lambda x: -len(x[1])):
            hot  = sum(1 for *_, v in skills if not v)
            cold = sum(1 for *_, v in skills if v)
            if cat != 'Other':
                print(f'  {cat:<16} {hot:3} hot  {cold:3} vault')
        other = entries.get('Other', [])
        hot  = sum(1 for *_, v in other if not v)
        cold = sum(1 for *_, v in other if v)
        print(f'  {"Other":<16} {hot:3} hot  {cold:3} vault')

if __name__ == '__main__':
    sys.exit(main())
