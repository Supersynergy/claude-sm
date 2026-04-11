#!/usr/bin/env python3
# Compare: Python-native hyperfetch.py vs bash hyperfetch wrapper.
# Measures fresh-fetch and cache-hit latency for each mode.

import json
import subprocess
import time
from pathlib import Path

HOME = Path.home()
PY = HOME / ".cts" / "venv" / "bin" / "python"
PY_FETCH = HOME / ".cts" / "bin" / "hyperfetch.py"
BASH_FETCH = HOME / ".cts" / "bin" / "hyperfetch"

URLS = [
    "https://example.com",
    "https://httpbin.org/html",
    "https://quotes.toscrape.com",
]


def run_cmd(cmd):
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    ms = (time.perf_counter() - t0) * 1000
    try:
        data = json.loads(r.stdout.strip().splitlines()[-1])
        return {"ok": True, "ms_wall": round(ms, 1),
                "tokens": data.get("tokens", 0),
                "cached": data.get("cached", False),
                "latency_reported": data.get("latency_ms", 0)}
    except Exception as e:
        return {"ok": False, "ms_wall": round(ms, 1), "error": str(e)[:100]}


def main():
    rows = []
    for url in URLS:
        row = {"url": url}
        ns = f"cmp-{hash(url) % 100000}"

        # Python native
        row["py_fresh"] = run_cmd([str(PY), str(PY_FETCH), url, "--team-ns", ns, "--no-cache"])
        row["py_cache"] = run_cmd([str(PY), str(PY_FETCH), url, "--team-ns", ns])
        row["py_cache2"] = run_cmd([str(PY), str(PY_FETCH), url, "--team-ns", ns])

        # Bash wrapper
        row["bash_fresh"] = run_cmd([str(BASH_FETCH), url, "--team-ns", ns + "-bash", "--no-cache", "--prefetch"])
        row["bash_cache"] = run_cmd([str(BASH_FETCH), url, "--team-ns", ns + "-bash", "--prefetch"])

        rows.append(row)

    print("\n## Python-native vs Bash hyperfetch\n")
    print("| URL | py_fresh | py_cache | py_cache2 | bash_fresh | bash_cache |")
    print("|-----|---------:|---------:|----------:|-----------:|-----------:|")
    for r in rows:
        print(
            f"| {r['url'].split('//')[-1][:30]} "
            f"| {r['py_fresh'].get('ms_wall', '?')}ms "
            f"| **{r['py_cache'].get('ms_wall', '?')}ms** "
            f"| **{r['py_cache2'].get('ms_wall', '?')}ms** "
            f"| {r['bash_fresh'].get('ms_wall', '?')}ms "
            f"| {r['bash_cache'].get('ms_wall', '?')}ms |"
        )

    py_cache_avg = sum(r["py_cache"].get("ms_wall", 0) for r in rows) / len(rows)
    bash_cache_avg = sum(r["bash_cache"].get("ms_wall", 0) for r in rows) / len(rows)
    print(f"\n**Cache-hit average**: Python {py_cache_avg:.0f}ms vs Bash {bash_cache_avg:.0f}ms = **{bash_cache_avg/max(py_cache_avg,1):.1f}x faster**\n")


if __name__ == "__main__":
    main()
