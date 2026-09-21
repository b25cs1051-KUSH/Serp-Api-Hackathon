"""
tune_threshold.py — Find the right similarity threshold for pharma queries.

Prints cosine similarity scores + dosage guard status for pharma query pairs
so you can decide what threshold makes sense.

Run:
    python scripts/tune_threshold.py
"""

import sys, io, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import re
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def sim(a, b):
    ea = model.encode(a, normalize_embeddings=True)
    eb = model.encode(b, normalize_embeddings=True)
    return float(np.dot(ea, eb))

def extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+\.?\d*", text))

def dosage_guard_fires(a: str, b: str) -> bool:
    na, nb = extract_numbers(a), extract_numbers(b)
    if not na or not nb:
        return False
    return na != nb

# (query_a, query_b, expected_verdict)
pairs = [
    # Should HIT — same dosage, different phrasing
    ("Metformin 500mg price India",           "Metformin 500 mg cost India",             "HIT"),
    ("Atorvastatin 10mg tablet price",        "Atorvastatin 10 mg cost India",           "HIT"),
    # Should HIT — no numbers in one query, cosine decides
    ("cheap Paracetamol 500mg India",         "affordable Paracetamol tablet India",     "HIT"),
    ("generic substitute for Januvia India",  "Januvia generic alternative India",       "HIT"),
    # Should MISS — dosage guard fires
    ("Metformin 20mg price India",            "Metformin 200mg price India",             "MISS"),
    ("Atorvastatin 10mg price India",         "Atorvastatin 20mg price India",           "MISS"),
    # Should MISS — different drug
    ("Metformin 500mg price India",           "Amlodipine 5mg price India",              "MISS"),
    ("Levothyroxine 50mcg price India",       "Atorvastatin 10mg tablet price",          "MISS"),
]

THRESHOLD = 0.80

print("\n" + "=" * 90)
print(f"  Pharma Similarity Threshold Tuning  (threshold = {THRESHOLD})")
print("=" * 90)
print(f"  {'Score':>6}  {'Guard':^7}  {'Verdict':<6}  {'Expected':<6}  {'':^4}  Query Pair")
print("-" * 90)

all_pass = True
for a, b, expected in pairs:
    score = sim(a, b)
    guard = dosage_guard_fires(a, b)
    # Final verdict: MISS if guard fires OR score below threshold
    verdict = "MISS" if (guard or score < THRESHOLD) else "HIT"
    passed = verdict == expected
    if not passed:
        all_pass = False
    flag = "✅" if passed else "❌"
    guard_str = "FIRED" if guard else "ok   "
    print(f"  {score:.4f}  [{guard_str}]  {verdict:<6}  {expected:<6}  {flag}   '{a[:35]}' <-> '{b[:35]}'")

print("=" * 90)
print(f"\n  Active threshold : {THRESHOLD}")
print(f"  All pairs pass   : {'✅ YES' if all_pass else '❌ NO — adjust THRESHOLD or review pairs'}")
print("  Higher = fewer false hits | Lower = more aggressive caching\n")
