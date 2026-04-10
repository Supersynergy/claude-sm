#!/usr/bin/env python3
# Apples-to-apples: hyperfetch vs crawl4ai vs raw curl_cffi baseline.
# Same URLs, same machine, same moment. Measures bytes, tokens, latency, quality.

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

HOME = Path.home()
C4A_PY = HOME / "projects" / "scraper-benchmark" / ".venv" / "bin" / "python"
HYPERFETCH = HOME / ".cts" / "bin" / "hyperfetch"
STAGE_HELPER = HOME / ".cts" / "bin" / "hyperfetch-stage.py"
VENV_PY = HOME / ".cts" / "venv" / "bin" / "python"

URLS = [
    ("tiny-static",     "https://example.com"),
    ("medium-html",     "https://httpbin.org/html"),
    ("quotes-static",   "https://quotes.toscrape.com"),
    ("news-dynamic",    "https://news.ycombinator.com"),
    ("wiki-large",      "https://en.wikipedia.org/wiki/Token"),
]


def tok(n_bytes: int) -> int:
    return max(1, n_bytes // 4)


def measure(label, fn):
    t0 = time.perf_counter()
    try:
        result = fn()
        ms = (time.perf_counter() - t0) * 1000
        return {"label": label, "ok": True, "latency_ms": round(ms, 1), **result}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return {"label": label, "ok": False, "latency_ms": round(ms, 1), "error": str(e)[:200]}


def run_baseline(url: str) -> dict:
    """Raw curl_cffi — simulates WebFetch (full HTML into context)."""
    def inner():
        r = subprocess.run(
            [str(VENV_PY), str(STAGE_HELPER), "--stage", "curl_cffi", "--url", url],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(r.stdout)
        body = data.get("body", "")
        b = len(body.encode("utf-8"))
        return {"bytes": b, "tokens": tok(b), "preview": body[:80]}
    return measure("baseline_raw", inner)


def run_hyperfetch_summary(url: str) -> dict:
    """hyperfetch default = gemma summary."""
    def inner():
        r = subprocess.run(
            [str(HYPERFETCH), url, "--team-ns", "c4a-cmp", "--no-cache"],
            capture_output=True, text=True, timeout=120,
            env={**__import__("os").environ, "CTS_GEMMA_THRESHOLD": "100"},
        )
        data = json.loads(r.stdout.strip().splitlines()[-1])
        return {"bytes": data.get("bytes", 0), "tokens": data.get("tokens", 0), "preview": data.get("preview", "")[:120], "stage": data.get("stage")}
    return measure("hyperfetch_summary", inner)


def run_hyperfetch_extract(url: str, prompt: str) -> dict:
    """hyperfetch --extract with targeted prompt."""
    def inner():
        r = subprocess.run(
            [str(HYPERFETCH), url, "--team-ns", "c4a-ext", "--no-cache", "--extract", prompt],
            capture_output=True, text=True, timeout=120,
            env={**__import__("os").environ, "CTS_GEMMA_THRESHOLD": "50"},
        )
        data = json.loads(r.stdout.strip().splitlines()[-1])
        return {"bytes": data.get("bytes", 0), "tokens": data.get("tokens", 0), "preview": data.get("preview", "")[:120]}
    return measure("hyperfetch_extract", inner)


def run_hyperfetch_prefetch(url: str) -> dict:
    """hyperfetch --prefetch — just title + h1 + meta description, no gemma call."""
    def inner():
        r = subprocess.run(
            [str(HYPERFETCH), url, "--team-ns", "c4a-pre", "--no-cache", "--prefetch"],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(r.stdout.strip().splitlines()[-1])
        return {"bytes": data.get("bytes", 0), "tokens": data.get("tokens", 0), "preview": data.get("preview", "")[:120]}
    return measure("hyperfetch_prefetch", inner)


def run_crawl4ai(url: str) -> dict:
    """crawl4ai default — LLM-ready markdown output."""
    script = f"""
import asyncio, json, sys, warnings
warnings.filterwarnings("ignore")
async def main():
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler(verbose=False) as c:
        r = await c.arun(url={url!r})
        md = (r.markdown or "")[:50000]
        print(json.dumps({{"bytes": len(md.encode()), "tokens": max(1, len(md.encode())//4), "preview": md[:120]}}))
asyncio.run(main())
"""
    def inner():
        r = subprocess.run(
            [str(C4A_PY), "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr[:200])
        line = [l for l in r.stdout.splitlines() if l.strip().startswith("{")][-1]
        return json.loads(line)
    return measure("crawl4ai", inner)


EXTRACT_PROMPTS = {
    "tiny-static":   "website title and main purpose in 1 sentence",
    "medium-html":   "main title and author of the document",
    "quotes-static": "list top 3 quotes with author as JSON",
    "news-dynamic":  "top 3 story titles as a numbered list",
    "wiki-large":    "top 5 definitions of the term 'token'",
}


def main():
    all_rows = []
    for label, url in URLS:
        print(f"\n=== {label}: {url}", file=sys.stderr)
        row = {"label": label, "url": url, "runs": {}}

        print("  [1/5] baseline raw curl_cffi", file=sys.stderr)
        row["runs"]["baseline"] = run_baseline(url)

        print("  [2/5] hyperfetch prefetch (title/h1/meta only)", file=sys.stderr)
        row["runs"]["hf_prefetch"] = run_hyperfetch_prefetch(url)

        print("  [3/5] hyperfetch summary (gemma bullets)", file=sys.stderr)
        row["runs"]["hf_summary"] = run_hyperfetch_summary(url)

        print("  [4/5] hyperfetch extract (targeted prompt)", file=sys.stderr)
        row["runs"]["hf_extract"] = run_hyperfetch_extract(url, EXTRACT_PROMPTS[label])

        print("  [5/5] crawl4ai markdown", file=sys.stderr)
        row["runs"]["crawl4ai"] = run_crawl4ai(url)

        all_rows.append(row)

    out_dir = Path(__file__).parent
    (out_dir / "vs_crawl4ai.json").write_text(json.dumps(all_rows, indent=2))

    print("\n\n# hyperfetch vs crawl4ai vs baseline\n")
    print("| URL | Baseline | hf prefetch | hf summary | hf extract | crawl4ai | Best factor |")
    print("|-----|---------:|------------:|-----------:|-----------:|---------:|------------:|")
    for r in all_rows:
        b = r["runs"]["baseline"].get("tokens", 0)
        p = r["runs"]["hf_prefetch"].get("tokens", 0) if r["runs"]["hf_prefetch"]["ok"] else 0
        s = r["runs"]["hf_summary"].get("tokens", 0) if r["runs"]["hf_summary"]["ok"] else 0
        e = r["runs"]["hf_extract"].get("tokens", 0) if r["runs"]["hf_extract"]["ok"] else 0
        c = r["runs"]["crawl4ai"].get("tokens", 0) if r["runs"]["crawl4ai"]["ok"] else 0
        nums = [x for x in (p, s, e, c) if x > 0]
        factor = b / min(nums) if nums else 0
        print(f"| {r['label']} | {b} | {p} | {s} | {e} | {c} | **{factor:.0f}x** |")

    print("\n## Latency profile (ms)\n")
    print("| URL | baseline | hf prefetch | hf summary | hf extract | crawl4ai |")
    print("|-----|---------:|------------:|-----------:|-----------:|---------:|")
    for r in all_rows:
        bt = r["runs"]["baseline"].get("latency_ms", 0)
        p = r["runs"]["hf_prefetch"].get("latency_ms", 0)
        s = r["runs"]["hf_summary"].get("latency_ms", 0)
        e = r["runs"]["hf_extract"].get("latency_ms", 0)
        c = r["runs"]["crawl4ai"].get("latency_ms", 0)
        print(f"| {r['label']} | {bt:.0f} | {p:.0f} | {s:.0f} | {e:.0f} | {c:.0f} |")

    print("\n## Sample outputs (quality spot-check)\n")
    for r in all_rows:
        print(f"### {r['label']}")
        for mode in ("hf_extract", "hf_summary", "crawl4ai"):
            preview = r["runs"][mode].get("preview", "")
            print(f"- **{mode}**: `{preview[:120]}`")
        print()


if __name__ == "__main__":
    main()
