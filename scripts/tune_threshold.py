"""
tune_threshold.py — Find the right similarity threshold for your use case.

Prints cosine similarity scores for a set of query pairs so you can
decide what threshold makes sense for your cache.

Run:
    python tune_threshold.py
"""

import sys, io, os
# Allow running from any directory — add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def sim(a, b):
    ea = model.encode(a, normalize_embeddings=True)
    eb = model.encode(b, normalize_embeddings=True)
    return float(np.dot(ea, eb))

pairs = [
    # Should HIT (same intent, different words)
    ("best laptop under 50000 India",       "top laptops below 50k in India",          "SHOULD HIT"),
    ("SerpApi Python SDK tutorial 2026",    "SerpApi Python library guide",             "SHOULD HIT"),
    ("cheapest medicine for diabetes India","affordable diabetes drugs India",           "SHOULD HIT"),
    ("government tenders IT sector India",  "India govt IT procurement tenders",        "SHOULD HIT"),

    # Should MISS (different intent)
    ("best laptop under 50000 India",       "India GDP growth 2026 forecast",           "SHOULD MISS"),
    ("medicine price comparison India",     "SerpApi Python tutorial",                  "SHOULD MISS"),
    ("government tenders IT sector India",  "best restaurants in Bangalore",            "SHOULD MISS"),
]

THRESHOLD = 0.80   # must match SerpApiCache default_threshold in cache.py

print("\n" + "="*70)
print(f"  Similarity Threshold Tuning  (current threshold = {THRESHOLD})")
print("="*70)
print(f"  {'Score':>6}  {'Verdict':<12}  Query Pair")
print("-"*70)

for a, b, label in pairs:
    score = sim(a, b)
    verdict = "HIT " if score >= THRESHOLD else "MISS"
    flag = "✅" if (verdict == "HIT " and "HIT" in label) or (verdict == "MISS" and "MISS" in label) else "❌"
    print(f"  {score:.4f}  [{verdict}] {flag}  '{a[:30]}' <-> '{b[:30]}'")

print("="*70)
print(f"\n  Active threshold : {THRESHOLD}")
print("  Higher = fewer false hits | Lower = more aggressive caching\n")
