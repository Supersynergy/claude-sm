#!/usr/bin/env python3
# Zero-cost prefetch extractor: title, h1, meta description, first paragraph.
# Reads HTML from stdin, writes plain-text extract to stdout. No LLM call.

import sys
import re


def pick(html: str, pattern: str) -> str:
    m = re.search(pattern, html, re.I | re.S)
    return m.group(1).strip() if m else ""


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def extract(html: str) -> str:
    title = strip_tags(pick(html, r"<title[^>]*>(.*?)</title>"))
    meta = pick(html, r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']')
    if not meta:
        meta = pick(html, r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']')
    h1 = strip_tags(pick(html, r"<h1[^>]*>(.*?)</h1>"))
    first_p = strip_tags(pick(html, r"<p[^>]*>(.*?)</p>"))

    lines = []
    if title:
        lines.append(f"title: {title[:200]}")
    if h1 and h1 != title:
        lines.append(f"h1: {h1[:200]}")
    if meta:
        lines.append(f"desc: {meta[:300]}")
    if first_p and first_p not in (title, meta):
        lines.append(f"p1: {first_p[:300]}")
    if not lines:
        lines.append(html[:500].replace("\n", " "))
    return "\n".join(lines)


if __name__ == "__main__":
    html = sys.stdin.read()
    sys.stdout.write(extract(html))
