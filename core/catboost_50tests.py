import sys
sys.path.insert(0, '/opt/homebrew/lib/python3.12/site-packages')
import re, time, json
import numpy as np
from catboost import CatBoostClassifier

np.random.seed(42)
SAMPLES = 2000

def make_paragraph(is_signal):
    if is_signal:
        words = np.random.randint(15, 80)
        text = ' '.join(['word' * np.random.randint(1,3) for _ in range(words)])
        if np.random.random() > 0.5:
            text = text[0].upper() + text[1:] + '.'
        return text
    else:
        choices = [
            'Home About Contact Privacy Terms',
            'Click here to read more...',
            'Copyright 2024. All rights reserved.',
            'Subscribe Newsletter Login Register',
            '© 2024 Company Inc. | Privacy | Terms',
            'Loading... Please wait.',
            'Share Tweet Pin Email',
        ]
        return np.random.choice(choices)

def featurize_v1(p):
    words = p.split()
    chars = max(len(p), 1)
    return [
        chars,
        len(words),
        len(re.findall(r'https?://', p)) / (chars/100),
        sum(c.isdigit() for c in p) / chars,
        sum(c.isupper() for c in p) / chars,
        len(re.findall(r'[.!?]+', p)),
        sum(len(w) for w in words) / max(len(words),1),
        int(bool(words and words[0][0].isupper())),
    ]

def featurize_v2(p):
    words = p.split()
    chars = max(len(p), 1)
    base = featurize_v1(p)
    punct_ratio = sum(c in '.,;:!?()[]{}' for c in p) / chars
    unique_ratio = len(set(words)) / max(len(words), 1)
    pipe_count = p.count('|')
    copyright = int('©' in p or 'copyright' in p.lower() or 'all rights' in p.lower())
    nav_words = int(any(w in p.lower() for w in ['home','about','contact','login','register','privacy','terms','subscribe']))
    avg_sent_len = chars / max(len(re.findall(r'[.!?]+', p)), 1)
    return base + [punct_ratio, unique_ratio, pipe_count, copyright, nav_words, avg_sent_len]

def featurize_v3(p):
    v2 = featurize_v2(p)
    words = p.split()
    chars = max(len(p), 1)
    short_words = sum(1 for w in words if len(w) <= 3) / max(len(words), 1)
    long_words = sum(1 for w in words if len(w) >= 8) / max(len(words), 1)
    starts_lower = int(bool(words and words[0][0].islower()))
    ellipsis = int('...' in p)
    return v2 + [short_words, long_words, starts_lower, ellipsis]

paras = [make_paragraph(i % 2 == 0) for i in range(SAMPLES)]
labels = [i % 2 for i in range(SAMPLES)]
idx = np.random.permutation(SAMPLES)
paras = [paras[i] for i in idx]
labels = [labels[i] for i in idx]

X1 = np.array([featurize_v1(p) for p in paras])
X2 = np.array([featurize_v2(p) for p in paras])
X3 = np.array([featurize_v3(p) for p in paras])
y  = np.array(labels)

split = int(0.8 * SAMPLES)
X1tr, X1te = X1[:split], X1[split:]
X2tr, X2te = X2[:split], X2[split:]
X3tr, X3te = X3[:split], X3[split:]
Ytr, Yte   = y[:split],  y[split:]

results = []

def bench(name, cfg, Xtr, Xte):
    cfg_full = dict(task_type='CPU', verbose=0, random_seed=42,
                    early_stopping_rounds=30, eval_metric='AUC', **cfg)
    m = CatBoostClassifier(**cfg_full)
    t0 = time.perf_counter()
    m.fit(Xtr, Ytr, eval_set=(Xte, Yte))
    ms = int((time.perf_counter()-t0)*1000)
    auc = float(m.best_score_['validation']['AUC'])
    results.append({'name': name, 'ms': ms, 'auc': round(auc,4),
                    'iters': m.best_iteration_, 'feats': Xtr.shape[1], 'params': cfg})
    print(f"  {name:<48} AUC={auc:.4f} {ms}ms")

print("GROUP 1: Depth sweep")
for d in [2,3,4,5,6,7,8,10]:
    bench(f'depth={d}', {'depth':d,'iterations':500,'learning_rate':0.05}, X1tr, X1te)

print("GROUP 2: Learning rate sweep")
for lr in [0.001, 0.005, 0.01, 0.03, 0.05, 0.1, 0.3]:
    bench(f'lr={lr}', {'depth':6,'iterations':500,'learning_rate':lr}, X1tr, X1te)

print("GROUP 3: Iterations ceiling")
for itr in [50, 100, 200, 500, 1000]:
    bench(f'iters={itr}', {'depth':6,'iterations':itr,'learning_rate':0.05}, X1tr, X1te)

print("GROUP 4: Grow policy")
for gp in ['SymmetricTree','Depthwise','Lossguide']:
    bench(f'grow={gp}', {'depth':6,'iterations':500,'learning_rate':0.05,'grow_policy':gp}, X1tr, X1te)

print("GROUP 5: L2 regularization")
for l2 in [0.5, 1, 3, 10, 30]:
    bench(f'l2={l2}', {'depth':6,'iterations':500,'learning_rate':0.05,'l2_leaf_reg':l2}, X1tr, X1te)

print("GROUP 6: Class weights")
for cw in [[1,1],[1,2],[1,3],[2,1]]:
    bench(f'cw={cw}', {'depth':6,'iterations':500,'learning_rate':0.05,'class_weights':cw}, X1tr, X1te)

print("GROUP 7: Bootstrap types")
for bt in ['Bayesian','Bernoulli','MVS','No']:
    cfg = {'depth':6,'iterations':500,'learning_rate':0.05,'bootstrap_type':bt}
    if bt == 'Bayesian': cfg['bagging_temperature'] = 0.5
    if bt in ('Bernoulli','MVS'): cfg['subsample'] = 0.8
    bench(f'bootstrap={bt}', cfg, X1tr, X1te)

print("GROUP 8: Feature sets")
bench('feats=8_v1',  {'depth':6,'iterations':500,'learning_rate':0.05}, X1tr, X1te)
bench('feats=14_v2', {'depth':6,'iterations':500,'learning_rate':0.05}, X2tr, X2te)
bench('feats=18_v3', {'depth':6,'iterations':500,'learning_rate':0.05}, X3tr, X3te)

print("GROUP 9: Best combo candidates")
bench('combo_d6_lr005_l2_3_cw12_v2',
      {'depth':6,'iterations':1000,'learning_rate':0.05,'l2_leaf_reg':3,'class_weights':[1,2]}, X2tr, X2te)
bench('combo_d8_lr003_l2_1_v3',
      {'depth':8,'iterations':1000,'learning_rate':0.03,'l2_leaf_reg':1}, X3tr, X3te)
bench('combo_d5_lr01_mvs_v2',
      {'depth':5,'iterations':1000,'learning_rate':0.1,'bootstrap_type':'MVS','subsample':0.8}, X2tr, X2te)
bench('combo_d6_bayes05_cw12_v3',
      {'depth':6,'iterations':1000,'learning_rate':0.05,'bootstrap_type':'Bayesian','bagging_temperature':0.5,'class_weights':[1,2]}, X3tr, X3te)
bench('combo_d7_lr003_l2_3_cw12_v3',
      {'depth':7,'iterations':1000,'learning_rate':0.03,'l2_leaf_reg':3,'class_weights':[1,2]}, X3tr, X3te)
bench('ultra_d8_lr002_l2_3_bayes_cw12_v3',
      {'depth':8,'iterations':2000,'learning_rate':0.02,'l2_leaf_reg':3,'bootstrap_type':'Bayesian','bagging_temperature':0.5,'class_weights':[1,2]}, X3tr, X3te)

print("GROUP 10: Border count")
for bc in [32, 64, 128, 254, 512]:
    bench(f'border={bc}', {'depth':6,'iterations':500,'learning_rate':0.05,'border_count':bc}, X1tr, X1te)

results.sort(key=lambda x: -x['auc'])
print(f"\n{'='*72}")
print(f"{'Rank':<4} {'Name':<46} {'AUC':>6} {'ms':>5} {'i':>5} {'f':>3}")
print(f"{'='*72}")
for i, r in enumerate(results, 1):
    print(f"{i:<4} {r['name']:<46} {r['auc']:>6.4f} {r['ms']:>5} {r['iters']:>5} {r['feats']:>3}")

print(f"\n── TOP 5 ──")
for r in results[:5]:
    print(f"  AUC={r['auc']} | {r['name']} | {r['ms']}ms | feats={r['feats']}")
    print(f"  params: {json.dumps(r['params'])}")

print(f"\n── WORST 5 ──")
for r in results[-5:]:
    print(f"  AUC={r['auc']} | {r['name']} | {r['ms']}ms")

print(f"\n── OPTIMAL CONFIG ──")
best = results[0]
print(json.dumps(best['params'], indent=2))
print(f"Feature set: v{'1' if best['feats']==8 else '2' if best['feats']==14 else '3'} ({best['feats']} features)")
print(f"AUC={best['auc']} | Time={best['ms']}ms | Best iter={best['iters']}")
