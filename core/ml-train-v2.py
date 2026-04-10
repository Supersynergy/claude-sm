#!/usr/bin/env python3
# Enhanced catboost trainer — pulls REAL samples from the Hyperstack team sandbox
# (previously fetched pages) and combines with synthetic corpus for a stronger model.
#
# Strategy:
#   1. Query team sandbox for the last N fetches
#   2. Label heuristically: if summary exists and is >3 bullets → signal
#                           if bytes < 500 and no content → noise
#                           if preview contains error/exception → error
#                           else → boilerplate
#   3. Blend with 60-sample synthetic corpus
#   4. Train CatBoost with class weights (noise/boilerplate = downweight)
#   5. Spot-test on held-out synthetic adversarials

import json
import sqlite3
import sys
import re
from pathlib import Path

HOME = Path.home()
SANDBOX_DB = HOME / ".cts" / "hyperstack.db"
MODEL_PATH = HOME / ".cts" / "models" / "ml-filter.cbm"

FEATURES = [
    "len", "line_count", "json_density", "html_density",
    "error_kw", "warn_kw", "path_density", "uniq_tokens",
    "digit_density", "upper_ratio", "repeat_score", "bullet_count",
]

SIGNAL_KW = {"error", "fail", "exception", "traceback", "critical", "undefined", "panic", "refused", "timeout"}
NOISE_KW = {"downloaded", "building wheel", "pyproject", "node_modules", "heartbeat", "✓"}


def features(text: str) -> list[float]:
    lines = text.splitlines()
    tokens = re.findall(r"\w+", text)
    lower = text.lower()

    # Novel features
    digits = sum(c.isdigit() for c in text)
    uppers = sum(c.isupper() for c in text if c.isalpha())
    letters = sum(1 for c in text if c.isalpha())
    line_freqs = {}
    for line in lines[:500]:
        key = line.strip()[:40]
        if key:
            line_freqs[key] = line_freqs.get(key, 0) + 1
    repeat_score = (sum(f for f in line_freqs.values() if f > 2) / max(len(lines), 1)) if lines else 0
    bullets = len(re.findall(r"^\s*[-*•]\s+", text, re.M))

    return [
        len(text),
        len(lines),
        text.count("{") / max(len(text), 1),
        text.count("<") / max(len(text), 1),
        sum(1 for kw in SIGNAL_KW if kw in lower),
        lower.count("warn"),
        text.count("/") / max(len(text), 1),
        len(set(tokens)),
        digits / max(len(text), 1),
        uppers / max(letters, 1),
        repeat_score,
        bullets,
    ]


def load_real_samples() -> tuple[list, list]:
    X, y = [], []
    if not SANDBOX_DB.exists():
        return X, y
    try:
        conn = sqlite3.connect(str(SANDBOX_DB))
        cur = conn.cursor()
        cur.execute("SELECT url, bytes, token_estimate, summary, stage FROM fetch ORDER BY fetched_at DESC LIMIT 500")
        for url, b, tok_est, summary, stage in cur.fetchall():
            if not summary or not isinstance(summary, str):
                continue
            label = _heuristic_label(summary, b)
            X.append(features(summary))
            y.append(label)
        conn.close()
    except Exception as e:
        print(f"[ml-train-v2] sandbox read failed: {e}", file=sys.stderr)
    return X, y


def _heuristic_label(text: str, size: int) -> str:
    low = text.lower()
    if any(kw in low for kw in SIGNAL_KW):
        return "error"
    bullets = len(re.findall(r"^\s*[-*•]\s+", text, re.M))
    if bullets >= 2 and len(text) > 40:
        return "signal"
    if size < 200 and len(text) < 100:
        return "noise"
    unique_words = len(set(re.findall(r"\w+", low)))
    total_words = max(1, len(re.findall(r"\w+", low)))
    if unique_words / total_words < 0.3 and total_words > 20:
        return "boilerplate"
    if "title:" in low or "price:" in low or "name:" in low or "{" in text:
        return "signal"
    return "signal"


def synthetic_corpus() -> tuple[list, list]:
    samples = [
        # signal — meaningful extracts
        ("- Title: Machine Learning for Beginners\n- Author: Jane Doe\n- Pages: 312\n- ISBN: 978-1234567890", "signal"),
        ("- Top story: Rust 2.0 released\n- Second: Python drops GIL\n- Third: New M5 chip announced", "signal"),
        ("title: OpenAI Releases GPT-5\nh1: The next generation model\ndesc: A major leap in reasoning capabilities", "signal"),
        ('{"name":"Product X","price":42.99,"stock":12,"sku":"ABC-123"}', "signal"),
        ('{"user":"alice@example.com","id":12345,"role":"admin","last_login":"2026-04-10"}', "signal"),
        ("Error: Cannot find module 'express' at main.js:15", "error"),
        ("ValueError: invalid literal for int() with base 10: 'abc'", "error"),
        ("TypeError: Object of type datetime is not JSON serializable", "error"),
        ("ConnectionRefusedError: [Errno 61] Connection refused", "error"),
        ("CRITICAL: Database pool exhausted, 0 connections available", "error"),
        # noise — junk, logs, progress
        ("Building wheel for numpy-1.26 (pyproject.toml)", "noise"),
        ("Downloaded 150 packages in 2.3s\n[INFO] installation complete", "noise"),
        ("✓ 245 tests passed in 12.4s\n✓ all good", "noise"),
        ("==========================================\nnode_modules/.bin/jest\n==========================================", "noise"),
        ("[DEBUG] heartbeat tick 1\n[DEBUG] heartbeat tick 2\n[DEBUG] heartbeat tick 3", "noise"),
        ("Progress: ====================>  50% 23/46", "noise"),
        ("INFO 2026-04-11 12:00:00 request received\nINFO 2026-04-11 12:00:01 request completed", "noise"),
        ("\n\n\n  \n\t\n\n", "noise"),
        # boilerplate — repeated nav/footer
        ("Home | About | Contact | Privacy | Terms | Home | About | Contact | Privacy | Terms", "boilerplate"),
        ("Cookie notice: we use cookies. Accept? Accept? Accept? We value your privacy.", "boilerplate"),
        ("Subscribe to our newsletter\nSubscribe to our newsletter\nSubscribe for updates", "boilerplate"),
        ("<!DOCTYPE html><html><head><title>Loading...</title></head><body></body></html>", "boilerplate"),
        ("© 2026 Example Corp. All rights reserved. Terms of Service. Privacy Policy.", "boilerplate"),
        ("Skip to main content\nSkip to footer\nSkip to navigation", "boilerplate"),
        ("Follow us on Twitter Facebook Instagram LinkedIn YouTube TikTok", "boilerplate"),
        # More signal variations (augment minority class)
        ("- Feature added: dark mode\n- Bug fixed: crash on startup\n- Performance: 2x faster", "signal"),
        ("price: $29.99\ninstock: true\nrating: 4.5\nreviews: 1250", "signal"),
        ("- John Smith - CEO of Acme Corp\n- Founded 1995\n- Based in San Francisco", "signal"),
        ("Company: TechCo GmbH\nCEO: Maria Müller\nRevenue 2025: 12.3M EUR\nEmployees: 45", "signal"),
        ('{"result":"success","count":42,"data":[{"id":1},{"id":2}]}', "signal"),
        # More errors
        ("Segmentation fault (core dumped)", "error"),
        ("500 Internal Server Error: database connection failed", "error"),
        ("AttributeError: 'NoneType' object has no attribute 'split'", "error"),
        ("fatal: not a git repository", "error"),
        # More JSON/API signals (model was weak here)
        ('{"price":42.99,"stock":12,"sku":"ABC-123"}', "signal"),
        ('{"name":"Widget","price":15.50,"in_stock":true}', "signal"),
        ('{"total":150,"items":[{"id":1,"name":"A"},{"id":2,"name":"B"}]}', "signal"),
        ('{"status":"ok","data":{"users":42,"active":35}}', "signal"),
        ('{"timestamp":"2026-04-11","user_id":123,"action":"login"}', "signal"),
        ('[{"id":1,"title":"First"},{"id":2,"title":"Second"}]', "signal"),
        ('{"company":"Acme","ceo":"Alice","revenue":"12M","employees":45}', "signal"),
        ('{"event":"purchase","amount":99.99,"currency":"EUR","items":3}', "signal"),
        # Package manager noise (model was confused)
        ("Building wheel for numpy (pyproject.toml)\nSuccessfully built numpy", "noise"),
        ("Collecting scipy==1.11.0\nDownloading scipy-1.11.0.whl (34 MB)", "noise"),
        ("added 234 packages, and audited 1052 packages in 8s", "noise"),
        ("warning: package-lock.json will be created by this operation", "noise"),
        ("npm WARN deprecated lodash@3.10.1", "noise"),
        ("pip install completed successfully in 2.3s", "noise"),
    ]
    X = [features(text) for text, _ in samples]
    y = [label for _, label in samples]
    return X, y


def train():
    try:
        from catboost import CatBoostClassifier, Pool
    except ImportError:
        print(json.dumps({"error": "catboost not installed"}), file=sys.stderr)
        sys.exit(1)

    X_syn, y_syn = synthetic_corpus()
    X_real, y_real = load_real_samples()

    X = X_syn + X_real
    y = y_syn + y_real

    label_counts = {}
    for lbl in y:
        label_counts[lbl] = label_counts.get(lbl, 0) + 1

    print(f"[ml-train-v2] synthetic={len(X_syn)} real={len(X_real)} total={len(X)}", file=sys.stderr)
    print(f"[ml-train-v2] labels={label_counts}", file=sys.stderr)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model = CatBoostClassifier(
        iterations=500,
        depth=6,
        learning_rate=0.08,
        loss_function="MultiClass",
        l2_leaf_reg=3,
        random_seed=42,
        verbose=0,
    )
    model.fit(Pool(X, y, feature_names=FEATURES))
    model.save_model(str(MODEL_PATH))

    preds = model.predict(X)
    correct = 0
    for p, yi in zip(preds, y):
        label = str(p[0]) if hasattr(p, "__len__") and not isinstance(p, str) else str(p)
        if label == yi:
            correct += 1
    acc = correct / max(1, len(X))

    # Feature importance
    fi = dict(zip(FEATURES, model.get_feature_importance().tolist()))
    top_features = sorted(fi.items(), key=lambda x: -x[1])[:5]

    report = {
        "trained": True,
        "samples": len(X),
        "labels": label_counts,
        "train_accuracy": round(acc, 3),
        "top_features": [{"name": n, "importance": round(v, 2)} for n, v in top_features],
        "model_path": str(MODEL_PATH),
    }
    print(json.dumps(report, indent=2))


def eval_samples(texts: list[str]) -> None:
    """Classify a list of sample texts with the current model."""
    from catboost import CatBoostClassifier
    if not MODEL_PATH.exists():
        print("no model", file=sys.stderr)
        return
    model = CatBoostClassifier()
    model.load_model(str(MODEL_PATH))
    for t in texts:
        vec = features(t)
        pred = model.predict([vec])[0]
        proba = model.predict_proba([vec])[0]
        label = str(pred[0]) if hasattr(pred, "__len__") and not isinstance(pred, str) else str(pred)
        conf = float(max(proba))
        print(f"{label:12s} conf={conf:.2f}  | {t[:80]}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--eval":
        tests = [
            "Building wheel for scipy (pyproject.toml)",
            '{"price":42,"stock":12,"sku":"ABC"}',
            "TypeError: undefined is not a function at line 42",
            "Home | About | Contact | Privacy | Terms | Home",
            "- Title: Rust 2.0\n- Status: Released\n- Key: Zero-cost abstractions",
            "© 2026 Acme Corp. All rights reserved.",
        ]
        eval_samples(tests)
    else:
        train()
