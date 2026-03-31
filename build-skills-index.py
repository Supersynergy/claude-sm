#!/usr/bin/env python3
"""
Build skills.idx (TSV) and skills-catalog.md from ~/.claude/skills/
Run: python3 ~/.claude/scripts/build-skills-index.py
Called by: /sm rebuild
"""
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
    'orchestrat': 'Agents', 'autonomous': 'Agents', 'devfleet': 'Agents',
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
    'sm': 'Meta', 'skill': 'Meta',
}

# Directories to skip entirely
SKIP_DIRS = {'.github', 'documentation', 'docs', '.git', '__pycache__', 'node_modules'}

def get_cat(name):
    n = name.lower()
    for k, v in CATS.items():
        if k in n:
            return v
    return 'Other'

def is_valid_skill(fm: dict) -> bool:
    """A valid Claude Code skill must have name + description."""
    return bool(fm.get('name') and fm.get('description'))

def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter fields (simple key:value only)."""
    fm = {}
    lines = content.split('\n')
    if not lines or lines[0].strip() != '---':
        return fm
    in_fm = False
    for line in lines[:40]:
        s = line.strip()
        if s == '---':
            if not in_fm:
                in_fm = True
                continue
            else:
                break  # end of frontmatter
        if in_fm and ':' in s:
            key, _, val = s.partition(':')
            fm[key.strip()] = val.strip()
    return fm

entries = defaultdict(list)
seen = set()

for f in sorted(skills_dir.rglob("*.md")):
    # Skip files in excluded directories
    parts = set(f.parts)
    if any(d in parts for d in SKIP_DIRS):
        continue
    # Skip files that look like GitHub templates
    if '.github' in str(f):
        continue

    try:
        content = f.read_text(errors='ignore')
        fm = parse_frontmatter(content)

        if not is_valid_skill(fm):
            continue

        name = fm['name']
        if name in seen:
            continue

        desc = fm['description'][:90]
        seen.add(name)
        cat = get_cat(name)
        entries[cat].append((name, desc, str(f)))
    except Exception:
        pass

# Write TSV index: name TAB category TAB description TAB path
idx_lines = []
for cat, skills in entries.items():
    for name, desc, path in skills:
        idx_lines.append(f"{name}\t{cat}\t{desc.replace(chr(9), ' ')}\t{path}")

with open(idx_path, 'w') as fh:
    fh.write('\n'.join(sorted(idx_lines)) + '\n')

# Write markdown catalog (chunked by category — good for ctx_index BM25)
md_lines = ["# Skills Catalog\n"]
for cat in sorted(entries.keys()):
    skills = sorted(entries[cat])
    md_lines.append(f"\n## {cat} ({len(skills)} skills)\n")
    for name, desc, path in skills:
        md_lines.append(f"- `/{name}` — {desc}")

with open(md_path, 'w') as fh:
    fh.write('\n'.join(md_lines))

total = sum(len(v) for v in entries.values())
print(f"Rebuilt: {total} skills → {idx_path}")
print(f"Catalog: {md_path} ({len(md_lines)} lines)")
# Category summary
for cat, skills in sorted(entries.items(), key=lambda x: -len(x[1])):
    print(f"  {cat:<14} {len(skills):3} skills")
