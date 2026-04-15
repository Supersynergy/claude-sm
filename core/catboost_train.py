#!/usr/bin/env python3
"""
catboost_train.py — Train HTML noise classifier for gemma-gate pre-filter.

Usage:
  python3 catboost_train.py --generate-samples   # create training data from trafilatura
  python3 catboost_train.py --train              # train model → noise_classifier.cbm
  python3 catboost_train.py --eval <url>         # evaluate on live URL

Attribution:
  catboost   https://github.com/catboost/catboost
  trafilatura https://github.com/adbar/trafilatura

Best practices applied:
  - GPU task_type on M4 Max (catboost auto-detects Metal via OpenCL)
  - Features: 8 hand-crafted (fast, interpretable, no embedding needed)
  - Positive class: trafilatura-extracted text paragraphs (signal)
  - Negative class: nav/footer/header stripped content (noise)
  - No hyperparameter tuning needed — defaults work well for this task
"""

import sys
import os
import re
import json
import argparse
import numpy as np

MODEL_PATH = os.environ.get("CTS_CATBOOST_MODEL", os.path.join(os.path.dirname(__file__), "noise_classifier.cbm"))


def featurize(paragraph: str) -> list:
    """8 features — fast, no embeddings needed for noise/signal classification."""
    words = paragraph.split()
    chars = max(len(paragraph), 1)
    links = len(re.findall(r"https?://", paragraph))
    digits = sum(c.isdigit() for c in paragraph)
    uppers = sum(c.isupper() for c in paragraph)
    sentences = len(re.findall(r"[.!?]+", paragraph))
    avg_word = sum(len(w) for w in words) / max(len(words), 1)
    starts_upper = int(bool(words and words[0][0].isupper())) if words else 0

    return [
        chars,                          # 1. length (longer = more likely signal)
        len(words),                     # 2. word count
        links / (chars / 100),          # 3. link density (high = nav noise)
        digits / chars,                 # 4. digit ratio (mixed = nav/price noise)
        uppers / chars,                 # 5. uppercase ratio (high = nav noise)
        sentences,                      # 6. sentence count (more = article signal)
        avg_word,                       # 7. avg word length (long = technical signal)
        starts_upper,                   # 8. starts with capital (article = yes)
    ]


def generate_samples(urls: list[str] | None = None) -> tuple[list, list]:
    """
    Generate training samples. Signal = trafilatura main body paragraphs.
    Noise = stripped paragraphs trafilatura discards (nav, footer, ads).
    """
    try:
        import trafilatura
        from trafilatura.core import baseline
    except ImportError:
        print("[train] trafilatura required. Install: pip install trafilatura", file=sys.stderr)
        sys.exit(1)

    if urls is None:
        # Default: diverse set of article + ecommerce + doc pages
        urls = [
            "https://example.com",
            "https://python.org",
            "https://docs.python.org/3/library/re.html",
            "https://news.ycombinator.com",
            "https://github.com/trending",
        ]

    X, y = [], []
    for url in urls:
        try:
            import urllib.request
            html = urllib.request.urlopen(url, timeout=10).read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"[train] skip {url}: {e}", file=sys.stderr)
            continue

        # Signal: what trafilatura keeps
        signal_text = trafilatura.extract(html, include_comments=False, include_tables=True, no_fallback=False) or ""
        signal_paras = [p.strip() for p in signal_text.split("\n\n") if len(p.strip()) > 30]

        # Noise: all paragraphs NOT in signal (nav, footer, etc.)
        all_text = re.sub(r"<[^>]+>", " ", html)
        all_text = re.sub(r"\s+", " ", all_text)
        all_paras = [p.strip() for p in re.split(r"[.\n]{2,}", all_text) if len(p.strip()) > 20]
        signal_set = set(signal_paras)
        noise_paras = [p for p in all_paras if p not in signal_set][:len(signal_paras)]

        for p in signal_paras[:50]:
            X.append(featurize(p))
            y.append(1)
        for p in noise_paras[:50]:
            X.append(featurize(p))
            y.append(0)

        print(f"[train] {url}: +{len(signal_paras)} signal, +{len(noise_paras)} noise", file=sys.stderr)

    return X, y


def train(X: list, y: list, output_path: str = MODEL_PATH) -> None:
    try:
        from catboost import CatBoostClassifier, Pool
    except ImportError:
        print("[train] catboost required. Install: pip install catboost", file=sys.stderr)
        sys.exit(1)

    X_arr = np.array(X, dtype=np.float32)
    y_arr = np.array(y, dtype=np.int32)

    model = CatBoostClassifier(
        iterations=500,
        depth=6,
        learning_rate=0.05,
        loss_function="Logloss",
        eval_metric="AUC",
        task_type="CPU",   # M4 Max: no CUDA/OpenCL in catboost — CPU only (160ms/2k samples, fast enough)
        verbose=50,
        random_seed=42,
        class_weights=[1.0, 2.0],  # upweight signal (we want precision > recall)
    )

    split = int(len(X_arr) * 0.8)
    train_pool = Pool(X_arr[:split], y_arr[:split])
    eval_pool  = Pool(X_arr[split:], y_arr[split:])

    model.fit(train_pool, eval_set=eval_pool, early_stopping_rounds=50)
    model.save_model(output_path)
    print(f"[train] Model saved → {output_path}", file=sys.stderr)

    # Feature importance
    feat_names = ["chars", "word_count", "link_density", "digit_ratio",
                  "upper_ratio", "sentences", "avg_word_len", "starts_upper"]
    importances = model.get_feature_importance()
    for name, imp in sorted(zip(feat_names, importances), key=lambda x: -x[1]):
        print(f"  {name:<18} {imp:.1f}%")


def eval_url(url: str) -> None:
    try:
        from catboost import CatBoostClassifier
        import urllib.request
        model = CatBoostClassifier()
        model.load_model(MODEL_PATH)
        html = urllib.request.urlopen(url, timeout=10).read().decode("utf-8", errors="ignore")
        paras = [p.strip() for p in re.split(r"\n{2,}", re.sub(r"<[^>]+>", " ", html)) if len(p.strip()) > 30]
        X = np.array([featurize(p) for p in paras])
        scores = model.predict_proba(X)[:, 1]
        kept = [(s, p) for s, p in zip(scores, paras) if s >= 0.5]
        dropped = sum(1 for s in scores if s < 0.5)
        print(f"\n[eval] {url}: kept {len(kept)}/{len(paras)} chunks ({dropped} noise filtered)")
        for score, para in sorted(kept, reverse=True)[:5]:
            print(f"  [{score:.2f}] {para[:100]}")
    except Exception as e:
        print(f"[eval] error: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="CatBoost HTML noise classifier trainer")
    parser.add_argument("--generate-samples", action="store_true")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--eval", metavar="URL")
    parser.add_argument("--samples-file", default="/tmp/cts_samples.json")
    parser.add_argument("--urls", nargs="*")
    args = parser.parse_args()

    if args.generate_samples or (args.train and not os.path.exists(args.samples_file)):
        X, y = generate_samples(args.urls)
        with open(args.samples_file, "w") as f:
            json.dump({"X": X, "y": y}, f)
        print(f"[train] Samples saved → {args.samples_file} ({len(y)} total)")

    if args.train:
        if os.path.exists(args.samples_file):
            with open(args.samples_file) as f:
                data = json.load(f)
            train(data["X"], data["y"])
        else:
            print("[train] No samples file. Run --generate-samples first.", file=sys.stderr)
            sys.exit(1)

    if args.eval:
        eval_url(args.eval)


if __name__ == "__main__":
    main()
