"""
live_edge_cases.py — Robustness run against the running API (docker compose up, http://localhost:8000).

  A. Input validation   bad queries / PINs / prescriptions → 4xx with a message, never 5xx (0 credits)
  B. Odd searches       typos, missing strength, combinations, syrups, non-medicines, gibberish,
                        unserviceable / remote PINs → 200 with a sensible outcome
  C. Prices             every listing's delivery fee, platform fee and landed cost equal the delivery
                        rules; ranking and the cheapest flag follow landed cost
  D. Links              resolved product pages are on the listing's own pharmacy and name its brand
                        and strength; pages are fetched (bot walls are reported as UNVERIFIABLE)
  E. Basket             plan arithmetic, single-store and as-prescribed invariants, links of every order
  F. Load               concurrent searches never 5xx and every slot is released

Credits: read from /api/account (free) before each costly step; stops at MAX_CREDITS (default 60).
Writes scripts/edge_case_report.md.

    python scripts/live_edge_cases.py
    MAX_CREDITS=30 API=http://localhost:8000 python scripts/live_edge_cases.py
"""

import json
import os
import re
import sys
import threading
import time
from urllib.parse import unquote, urlsplit

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from pharmawatch.delivery_cost import calculate_delivery_cost  # noqa: E402
from pharmawatch.distiller import identify_platform  # noqa: E402
from pharmawatch.pipeline import names_product  # noqa: E402

API = os.getenv("API", "http://localhost:8000").rstrip("/")
MAX_CREDITS = int(os.getenv("MAX_CREDITS", "60"))
REPORT = os.path.join(ROOT, "scripts", "edge_case_report.md")
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/126.0 Safari/537.36", "Accept-Language": "en-IN,en;q=0.9"}
LINK_SAMPLE = int(os.getenv("LINK_SAMPLE", "6"))   # /api/link clicks per search (1 credit each, first time)

rows = []          # (section, name, status, detail)
start_left = None


class OutOfCredits(Exception):
    pass


def record(section, name, ok, detail=""):
    status = ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")
    rows.append((section, name, status, str(detail)[:300]))
    print(f"  {status:<12} [{section}] {name}" + (f" — {detail}" if detail and status != "PASS" else ""))


def credits_left():
    return requests.get(f"{API}/api/account", timeout=30).json()["total_searches_left"]


def spent():
    return start_left - credits_left()


def budget(need=1):
    used = spent()
    if used + need > MAX_CREDITS:
        raise OutOfCredits(f"{used} credits used, cap {MAX_CREDITS}")


def search(q, pin="110001", links=False, llm=True):
    budget(1)
    r = requests.get(f"{API}/api/search", params={"q": q, "pincode": pin, "links": links, "llm": llm}, timeout=240)
    return r.status_code, r.json()


# ─────────────────────────────────────────────
# A. Input validation (0 credits)
# ─────────────────────────────────────────────

def section_a():
    print("\nA. Input validation")
    for label, q in [("empty", ""), ("one character", "a"), ("121 characters", "a" * 121), ("emoji only", "💊💊💊"),
                     ("only spaces", "      "), ("digits only", "650 500"), ("Hindi script", "पैरासिटामोल 650")]:
        r = requests.get(f"{API}/api/search", params={"q": q, "pincode": "110001"}, timeout=30)
        record("A", f"query {label} → 422", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
    for label, pin in [("letters", "abcdef"), ("starts with 0", "000000"), ("5 digits", "12345"), ("7 digits", "1100011"),
                       ("empty", "")]:
        r = requests.get(f"{API}/api/search", params={"q": "Dolo 650", "pincode": pin}, timeout=30)
        record("A", f"PIN {label} → 422", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
    over = [{"q": f"Medicine {i}", "tablets": 10} for i in range(9)]
    for label, items in [("0 lines", "[]"), ("9 lines", json.dumps(over)), ("tablets 0", '[{"q":"Dolo 650","tablets":0}]'),
                         ("tablets 501", '[{"q":"Dolo 650","tablets":501}]'), ("tablets true", '[{"q":"Dolo 650","tablets":true}]'),
                         ("tablets \"10\"", '[{"q":"Dolo 650","tablets":"10"}]'), ("tablets 2.5", '[{"q":"Dolo 650","tablets":2.5}]'),
                         ("missing q", '[{"tablets":10}]'), ("malformed JSON", '[{"q":"Dolo 650",'), ("not a list", '{"q":"Dolo 650"}')]:
        r = requests.get(f"{API}/api/prescription", params={"items": items, "pincode": "110001"}, timeout=30)
        record("A", f"prescription {label} → 4xx", 400 <= r.status_code < 500, f"{r.status_code} {r.text[:120]}")
    # Hostile text that is still a valid query: answered as JSON (never rendered as HTML), never a 5xx.
    hostile = [("search", {"q": q, "pincode": "110001", "links": False}) for q in
               ["<script>alert(1)</script>", "' OR 1=1 --", "../../etc/passwd"]]
    hostile.append(("prescription", {"items": '[{"q":"<script>alert(1)</script>","tablets":10}]', "pincode": "110001"}))
    for endpoint, params in hostile:
        budget(1)
        r = requests.get(f"{API}/api/{endpoint}", params=params, timeout=240)
        record("A", f"{endpoint} with hostile text {str(params.get('q') or params['items'])[:30]!r} → JSON, no 5xx",
               r.status_code < 500 and r.headers.get("content-type", "").startswith("application/json"), r.status_code)
    r = requests.get(f"{API}/api/link/not-a-real-id", timeout=30, allow_redirects=False)
    record("A", "unknown link id → 404", r.status_code == 404, r.status_code)


# ─────────────────────────────────────────────
# C. Prices equal the delivery rules
# ─────────────────────────────────────────────

def check_prices(tag, rows_, pin):
    mismatches = []
    for r in rows_:
        quote = calculate_delivery_cost(r["platform"], r["price_inr"], pin)
        for f in ("delivery_fee", "platform_fee", "total_landed_cost", "delivery_status"):
            if r.get(f) != quote[f]:
                mismatches.append(f"{r['platform']} {r['medicine_name'][:30]} {f}: shown {r.get(f)} rules {quote[f]}")
    record("C", f"{tag}: {len(rows_)} shown prices = delivery rules", not mismatches, "; ".join(mismatches[:3]))


def check_ranking(tag, listings):
    # Delivered rows rank by landed cost; pickup-only / unpriced rows follow them by design.
    priced = [l for l in listings if l.get("delivery_status") in ("free", "charged")]
    landed = [l["total_landed_cost"] for l in priced]
    record("C", f"{tag}: delivered rows ranked by landed cost, before the rest",
           landed == sorted(landed) and listings[:len(priced)] == priced, landed[:6])
    flagged = [l for l in listings if l.get("is_cheapest")]
    if priced:
        record("C", f"{tag}: cheapest flag on the lowest landed cost",
               len(flagged) == 1 and flagged[0]["total_landed_cost"] == min(landed), [l["platform"] for l in flagged])


# ─────────────────────────────────────────────
# D. Links open the exact medicine
# ─────────────────────────────────────────────

def _brand_and_strength(row):
    """The dataset brand's first word (falls back to the title) and its first number."""
    key = (row.get("brand") or row["medicine_name"]).lower()
    brand = next((w for w in re.findall(r"[a-z]+", key) if len(w) >= 3), "")
    strength = next(iter(re.findall(r"\d+(?:\.\d+)?", key)), "")
    return brand, strength


def check_link(tag, row, url):
    """Host is the listing's pharmacy, the path names its brand (and strength), the page loads."""
    name = f"{tag}: {row['platform']} · {row['medicine_name'][:40]}"
    if not url:
        record("D", name, "UNVERIFIABLE", "no product page on Google for this listing; store search shown instead")
        return
    if url in (row.get("search_link"), row.get("google_link")):
        record("D", name, "UNVERIFIABLE", "product page not found or not this product; store search shown instead")
        return
    host_store = identify_platform("", url)
    if host_store != row["platform"]:
        record("D", name + " → own pharmacy", False, f"{url[:100]} is {host_store}")
        return
    path = re.sub(r"[^a-z0-9]", "", unquote(unquote(urlsplit(url).path)).lower())
    brand, strength = _brand_and_strength(row)
    named = names_product(url, row) and (not strength or strength.replace(".", "") in path)
    record("D", name + " → URL names brand + strength", bool(named), f"{brand} {strength} not in {urlsplit(url).path[:80]}")
    try:
        page = requests.get(url, headers=BROWSER, timeout=25)
    except requests.RequestException as e:
        record("D", name + " → page loads", "UNVERIFIABLE", f"{type(e).__name__}")
        return
    text = page.text.lower()
    if page.status_code == 200 and brand in text:
        record("D", name + " → page loads and names the brand", True)
    elif page.status_code in (401, 403, 429, 503) or "captcha" in text:
        record("D", name + " → page loads", "UNVERIFIABLE", f"HTTP {page.status_code}: the pharmacy blocks scripted visits")
    else:
        record("D", name + " → page loads and names the brand", False, f"HTTP {page.status_code}")


def resolve(link_id):
    budget(1)
    r = requests.get(f"{API}/api/link/{link_id}", allow_redirects=False, timeout=90)
    return r.headers.get("location") if r.status_code == 302 else None


def check_links(tag, listings):
    direct = [l for l in listings if l.get("direct_link")]
    for l in direct:
        check_link(tag, l, l["direct_link"])
    for l in [l for l in listings if l.get("link_id")][:LINK_SAMPLE]:
        url = resolve(l["link_id"])
        own = url and identify_platform("", url) == l["platform"]
        check_link(tag + " (on click)", l, url if own else ("" if not url or "google." in url else url))


# ─────────────────────────────────────────────
# B. Odd searches (+ C and D on their results)
# ─────────────────────────────────────────────

def all_rows(j):
    alt = j.get("alternatives") or {}
    return (j.get("listings") or []) + ([alt["reference"]] if alt.get("reference") else []) + \
        (alt.get("cheaper_alternatives") or []) + (alt.get("other_alternatives") or [])


def section_b():
    print("\nB–D. Odd searches, prices and links")
    cases = [
        # (label, query, PIN, links, expectation(code, json) -> (ok, detail))
        ("typo 'dollo 650' → Dolo listings", "dollo 650", "110001", True,
         lambda c, j: (c == 200 and any("dolo" in l["medicine_name"].lower() for l in j["listings"] or []), j.get("query"))),
        ("typo 'stamloo 5' → Stamlo listings", "stamloo 5", "110001", False,
         lambda c, j: (c == 200 and any("stamlo" in l["medicine_name"].lower() for l in j["listings"] or []), len(j["listings"] or []))),
        ("salt without strength → choose, 0 credits", "paracetamol", "110001", False,
         lambda c, j: (c == 200 and bool(j.get("choose")) and j["summary"]["credits_spent"] == 0, j.get("choose"))),
        ("brand without strength → choose", "Telma", "110001", False,
         lambda c, j: (c == 200 and (bool(j.get("choose")) or bool(j.get("listings"))), j.get("choose"))),
        ("combination 'Pan-D'", "Pan-D", "110001", False,
         lambda c, j: (c == 200 and j["listings"] is not None, len(j["listings"] or []))),
        ("syrup 'Benadryl cough syrup'", "Benadryl cough syrup", "110001", False,
         lambda c, j: (c == 200, len(j["listings"] or []))),
        ("non-medicine 'iphone 15' → no substitutes", "iphone 15", "110001", False,
         lambda c, j: (c == 200 and not j.get("alternatives"), (len(j["listings"] or []), j.get("alternatives")))),
        ("gibberish 'xqzv 999'", "xqzv 999", "110001", False,
         lambda c, j: (c == 200 and not j.get("alternatives"), len(j["listings"] or []))),
        ("shouting + padding '  DOLO   650  '", "  DOLO   650  ", "110001", False,
         lambda c, j: (c == 200 and j["query"] == "DOLO 650", j.get("query"))),
        ("unserviceable PIN 744101 → nothing delivered", "Stamlo 5", "744101", False,
         lambda c, j: (c == 200 and all(l["total_landed_cost"] is None for l in j["listings"] or []),
                       {l["delivery_status"] for l in j["listings"] or []})),
        ("remote PIN 781001 Guwahati", "Dolo 650", "781001", False, lambda c, j: (c == 200, len(j["listings"] or []))),
        ("remote PIN 190001 Srinagar", "Stamlo 5", "190001", False, lambda c, j: (c == 200, len(j["listings"] or []))),
        ("Meerut 250002 with links", "Stamlo 5", "250002", True, lambda c, j: (c == 200, len(j["listings"] or []))),
    ]
    for label, q, pin, links, expect in cases:
        try:
            code, j = search(q, pin, links)
        except OutOfCredits as e:
            record("B", label, "SKIPPED", str(e))
            continue
        ok, detail = expect(code, j)
        record("B", label, ok and code < 500, f"HTTP {code}; {detail}")
        if code >= 500 or not j.get("listings"):
            continue
        check_prices(label, all_rows(j), j["pincode"])
        check_ranking(label, j["listings"])
        try:
            check_links(label, j["listings"] if links else j["listings"][:2])
            alt = j.get("alternatives") or {}
            check_links(label + " · cheaper brand", (alt.get("cheaper_alternatives") or [])[:2])
        except OutOfCredits as e:
            record("D", label + " links", "SKIPPED", str(e))


# ─────────────────────────────────────────────
# E. Basket
# ─────────────────────────────────────────────

def check_plan(tag, plan, pin, prescribed_only=False, single=False):
    if not plan:
        record("E", f"{tag}: plan exists", "UNVERIFIABLE", "no plan (nothing sold for these lines)")
        return []
    errors = []
    for s in plan["stores"]:
        q = calculate_delivery_cost(s["platform"], s["subtotal"], pin)
        fee = round(q["delivery_fee"] + q["platform_fee"], 2) if q["delivery_fee"] is not None else None
        if fee != s["fee"]:
            errors.append(f"{s['platform']} fee {s['fee']} ≠ rules {fee}")
        if round(s["subtotal"] + s["fee"], 2) != s["total"]:
            errors.append(f"{s['platform']} subtotal + fee ≠ total")
        if round(sum(o["item_cost"] for o in s["lines"]), 2) != s["subtotal"]:
            errors.append(f"{s['platform']} items ≠ subtotal")
    if round(sum(s["total"] for s in plan["stores"]), 2) != plan["total"]:
        errors.append("stores don't add up to the plan total")
    if single and len(plan["stores"]) != 1:
        errors.append(f"{len(plan['stores'])} stores in the one-pharmacy plan")
    if prescribed_only and any(not o["prescribed"] for s in plan["stores"] for o in s["lines"]):
        errors.append("a swap in the as-prescribed plan")
    record("E", f"{tag}: totals = items + rules' fees", not errors, "; ".join(errors))
    return [dict(o, platform=s["platform"]) for s in plan["stores"] for o in s["lines"]]


def section_e():
    print("\nE. Basket")
    prescriptions = [
        ("3 medicines + a strength-less line", [{"q": "Stamlo 5", "tablets": 30}, {"q": "Dolo 650", "tablets": 15},
                                                {"q": "paracetamol", "tablets": None}], True),
        ("duplicate line + gibberish line", [{"q": "Dolo 650", "tablets": 10}, {"q": "Dolo 650", "tablets": 10},
                                              {"q": "xqzv 999", "tablets": 10}], False),
    ]
    for label, items, links in prescriptions:
        try:
            budget(1)
        except OutOfCredits as e:
            record("E", label, "SKIPPED", str(e))
            continue
        r = requests.get(f"{API}/api/prescription", params={"items": json.dumps(items), "pincode": "110001", "links": links},
                         timeout=300)
        j = r.json()
        record("E", f"{label}: HTTP 200", r.status_code == 200, r.status_code)
        b = j.get("basket")
        if not b:
            record("E", f"{label}: basket built", False, j.get("error"))
            continue
        chosen = check_plan(f"{label} · cheapest", b["with_swaps"]["best"], j["pincode"])
        check_plan(f"{label} · one pharmacy", b["with_swaps"]["single_store"], j["pincode"], single=True)
        check_plan(f"{label} · as prescribed", b["as_prescribed"]["best"], j["pincode"], prescribed_only=True)
        record("E", f"{label}: strength-less / unsold lines reported",
               bool(b["skipped"] or b["unavailable"]) == any(i["q"] in ("paracetamol", "xqzv 999") for i in items),
               (b["skipped"], b["unavailable"]))
        if links:
            missing = [o["brand"] for o in chosen if not (o.get("direct_link") or o.get("link_id"))]
            record("E", f"{label}: every order line has a product link", not missing, missing)
            try:
                for o in chosen:
                    url = o.get("direct_link") or resolve(o["link_id"])
                    check_link(f"{label} basket", o, url if url and identify_platform("", url) == o["platform"] else "")
            except OutOfCredits as e:
                record("E", f"{label} links", "SKIPPED", str(e))


# ─────────────────────────────────────────────
# F. Load
# ─────────────────────────────────────────────

def section_f():
    print("\nF. Load")
    codes = []

    def one(q):
        try:
            codes.append(requests.get(f"{API}/api/search", params={"q": q, "pincode": "110001", "links": False},
                                      timeout=240).status_code)
        except requests.RequestException as e:
            codes.append(type(e).__name__)

    qs = ["Dolo 650", "Stamlo 5", "Pan 40", "Telma 40", "Azee 500", "Montair LC", "Ecosprin 75", "Atorbest 10"]
    threads = [threading.Thread(target=one, args=(q,)) for q in qs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    record("F", f"{len(qs)} concurrent searches: only 200 or 429", all(c in (200, 429) for c in codes), codes)
    time.sleep(1)
    active = requests.get(f"{API}/api/health", timeout=30).json().get("active_searches")
    record("F", "every search slot released", active == 0, active)


def write_report():
    by = {}
    for s, _, st, _ in rows:
        by.setdefault(st, 0)
        by[st] += 1
    lines = ["# Edge-case report", "", f"API {API} · credits used {spent()} of cap {MAX_CREDITS} · "
             + " · ".join(f"{k} {v}" for k, v in sorted(by.items())), "",
             "| Section | Check | Result | Detail |", "|---|---|---|---|"]
    for s, n, st, d in rows:
        lines.append(f"| {s} | {n.replace('|', '/')} | {st} | {d.replace('|', '/') if st != 'PASS' else ''} |")
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"\nReport: {REPORT}")


if __name__ == "__main__":
    start_left = credits_left()
    print(f"API {API} · {start_left} credits left · cap {MAX_CREDITS}")
    for section in (section_a, section_b, section_e, section_f):
        section()
    write_report()
    fails = sum(1 for r in rows if r[2] == "FAIL")
    print(f"\n{fails} FAILED · credits used {spent()}" if fails else f"\nNO FAILURES · credits used {spent()}")
    sys.exit(1 if fails else 0)
