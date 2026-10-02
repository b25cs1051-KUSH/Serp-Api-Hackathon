"""
reference_check.py — is PharmaWatch's cheapest same-composition offer at least as cheap as what the
pharmacies themselves suggest? A test harness only: pharmacy pages are read here as references and
are never used by the product (which gets every price from SerpApi).

References:
  - Chemist180: read automatically. Its product sitemap maps each medicine to its page, and each
    page shows the medicine's price and a "Has The Same Composition As" cheaper alternative.
    chemist180.com/robots.txt allows Claude-User. Pages are cached in scripts/.refcache/.
  - scripts/references.json: manual references (1mg, Medplus...) read off screenshots.

Our side: the real pipeline, links off, delivered price per tablet. Costs credits for anything not
cached; stops at MAX_CREDITS (default 70). Uses SERP_API_KEY_2 if set, else needs ALLOW_MAIN_KEY=1.

    ALLOW_MAIN_KEY=1 python scripts/reference_check.py            # all medicines + prescriptions
    ALLOW_MAIN_KEY=1 python scripts/reference_check.py "Stamlo 5"  # one medicine
Writes scripts/reference_report.md.
"""

import html
import json
import os
import re
import sys
import time
import urllib.request
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
if os.getenv("SERP_API_KEY_2"):
    os.environ["SERP_API_KEY"] = os.environ["SERP_API_KEY_2"]
elif os.getenv("ALLOW_MAIN_KEY") != "1":
    sys.exit("SERP_API_KEY_2 (test key) is not set. Live checks spend real credits; "
             "set ALLOW_MAIN_KEY=1 to use SERP_API_KEY instead.")
warnings.simplefilter("ignore")

from pharmawatch.generics import _tokens, title_matches_brand  # noqa: E402
from pharmawatch.pipeline import search_medicine_stream  # noqa: E402
from pharmawatch.prescription import prescription_stream  # noqa: E402
from pharmawatch.search import _get_cache  # noqa: E402

PIN = "110001"
MAX_CREDITS = int(os.getenv("MAX_CREDITS", "70"))
CACHE_DIR = os.path.join(ROOT, "scripts", ".refcache")
UA = {"User-Agent": "Mozilla/5.0 (compatible; Claude-User; PharmaWatch reference check)"}

MEDICINES = ["Stamlo 5", "Dolo 650", "Atorbest 10", "Pan 40", "Telma 40", "Glycomet GP 2", "Thyronorm 50",
             "Azithral 500", "Augmentin 625 Duo", "Montair LC", "Ecosprin 75", "Rosuvas 10", "Pantocid DSR",
             "Amlokind AT", "Metformin 500mg"]
PRESCRIPTIONS = [
    [{"query": "Dolo 650", "tablets": 30}, {"query": "Stamlo 5", "tablets": None}],
    [{"query": "Telma 40", "tablets": 30}, {"query": "Atorbest 10", "tablets": 30}, {"query": "Ecosprin 75", "tablets": None}],
    [{"query": "Glycomet GP 2", "tablets": 60}, {"query": "Rosuvas 10", "tablets": None}, {"query": "Pan 40", "tablets": 15},
     {"query": "Thyronorm 50", "tablets": None}],
    [{"query": m, "tablets": None} for m in ["Azithral 500", "Augmentin 625 Duo", "Montair LC", "Dolo 650",
                                             "Pantocid DSR", "Amlokind AT"]],
]


# ─────────────────────────────────────────────
# Chemist180 reference
# ─────────────────────────────────────────────

def _get(url: str, name: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path):
        return open(path, encoding="utf-8").read()
    body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "ignore")
    open(path, "w", encoding="utf-8").write(body)
    time.sleep(1)  # polite
    return body


def chemist180_url(brand: str):
    """The sitemap product page whose slug reads as this brand + strength (shortest slug wins)."""
    sitemap = _get("https://chemist180.com/sitemap_product.xml", "sitemap_product.xml")
    hits = []
    for url in re.findall(r"<loc>(.*?)</loc>", sitemap):
        slug = url.rsplit("/", 1)[-1]
        title = re.sub(r"-(\d+s|\d{3,})$", "", slug).replace("-", " ")  # drop pack ('15s') / id ('980') suffix
        if title_matches_brand(title, brand):
            hits.append(url)
    return min(hits, key=len) if hits else None


def _lines(page: str):
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return [ln.strip() for ln in html.unescape(re.sub(r"<[^>]+>", "\n", text)).splitlines() if ln.strip()]


def _block(lines):
    prices = [float(ln[1:].replace(",", "")) for ln in lines if re.fullmatch(r"₹[\d,]+(\.\d+)?", ln)]
    pack = next((int(lines[i + 1]) for i, ln in enumerate(lines[:-1])
                 if ln.upper() == "PACK SIZE" and lines[i + 1].isdigit()), None)
    maker = next((lines[i + 1] for i, ln in enumerate(lines[:-1]) if ln.upper() == "MANUFACTURE"), None)
    price = prices[1] if len(prices) > 1 else (prices[0] if prices else None)   # MRP first, then selling
    return price, pack, maker


def chemist180_reference(brand: str):
    url = chemist180_url(brand)
    if not url:
        return {"brand": brand, "url": None}
    lines = _lines(_get(url, url.rsplit("/", 1)[-1] + ".html"))
    cut = next((i for i, ln in enumerate(lines) if ln.lower().startswith("has the same composition")), None)
    own = _block(lines[: cut if cut is not None else len(lines)][:60])
    out = {"brand": brand, "url": url, "name": lines[17] if len(lines) > 17 else brand,
           "price": own[0], "pack": own[1], "maker": own[2], "alt": None}
    if cut is not None:
        alt_lines = lines[cut:cut + 30]
        pct_i = next((i for i, ln in enumerate(alt_lines) if re.search(r"%\s*(LESS|COSTLIER)", ln, re.I)), None)
        if pct_i is not None and pct_i + 1 < len(alt_lines):
            a = _block(alt_lines[pct_i:])
            out["alt"] = {"name": alt_lines[pct_i + 1], "note": alt_lines[pct_i], "price": a[0], "pack": a[1], "maker": a[2]}
    return out


def per_tab(price, pack):
    return round(price / pack, 2) if price and pack else None


# ─────────────────────────────────────────────
# Our side
# ─────────────────────────────────────────────

def ours(query: str):
    result = dict(search_medicine_stream(query, PIN, resolve_links=False, use_llm=False))
    alt = result.get("alternatives") or {}
    rows = list(alt.get("cheaper_alternatives") or []) + list(alt.get("other_alternatives") or [])
    if alt.get("reference"):
        rows.append(alt["reference"])
    rows = [r for r in rows if r.get("unit_landed_cost") is not None]
    best = min(rows, key=lambda r: r["unit_landed_cost"]) if rows else None
    brands = {" ".join(sorted(set(_tokens(r["brand"])))) for r in rows}
    return best, brands, alt.get("reference")


def main(only=None):
    cache = _get_cache(verbose=False)
    manual = json.load(open(os.path.join(ROOT, "scripts", "references.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(ROOT, "scripts", "references.json")) else {}
    spent = 0
    rows, misses = [], []
    for med in (only or MEDICINES):
        if spent >= MAX_CREDITS:
            print(f"  STOP: {spent} credits spent (MAX_CREDITS={MAX_CREDITS})")
            break
        before = len(cache.call_log)
        best, brands, reference = ours(med)
        cost = sum(1 for c in cache.call_log[before:] if c["credit"])
        spent += cost
        refs = []
        try:
            c180 = chemist180_reference(reference["brand"] if reference else med)
        except Exception as e:
            c180 = {"error": f"{type(e).__name__}: {e}"}
        if c180.get("price"):
            refs.append(("Chemist180 " + (c180.get("name") or med), per_tab(c180["price"], c180["pack"]), None))
        if c180.get("alt") and c180["alt"].get("price"):
            refs.append(("Chemist180 suggests " + c180["alt"]["name"], per_tab(c180["alt"]["price"], c180["alt"]["pack"]),
                         c180["alt"]["name"]))
        for m in manual.get(med, []):
            refs.append((f"{m['site']} {m['name']}", per_tab(m["price"], m["pack"]), m["name"]))
        refs = [r for r in refs if r[1] is not None]
        target = min(refs, key=lambda r: r[1]) if refs else None
        ours_tab = best["unit_landed_cost"] if best else None
        ok = target is None or (ours_tab is not None and ours_tab <= target[1])
        why = ""
        if not ok and target and target[2]:
            key = " ".join(sorted(set(_tokens(target[2]))))
            why = ("reference brand never appeared in our searches" if not any(key in b or b in key for b in brands)
                   else "reference brand found, but our price for it is higher")
        elif not ok:
            why = "our offers cost more per tablet than the reference"
        line = (f"{'PASS' if ok else 'FAIL'}  {med:18} ours {('₹%.2f' % ours_tab) if ours_tab else '—':>7}/tab "
                f"({best['brand'] + ' @ ' + best['platform'] if best else 'nothing'})  "
                f"ref {('₹%.2f' % target[1]) if target else '—':>7} ({target[0] if target else 'no reference'})  "
                f"[{cost} cr]{('  → ' + why) if why else ''}")
        print("  " + line)
        rows.append((med, ok, ours_tab, best, target, cost, why, c180))
        if not ok:
            misses.append(med)

    rx_lines = []
    if not only and spent < MAX_CREDITS:
        for rx in PRESCRIPTIONS:
            before = len(cache.call_log)
            result = dict(prescription_stream(rx, PIN, resolve_links=False, use_llm=False))
            b = result.get("basket")
            cost = sum(1 for c in cache.call_log[before:] if c["credit"])
            spent += cost
            best, single, ap = b["with_swaps"]["best"], b["with_swaps"]["single_store"], b["as_prescribed"]["best"]
            alone = sum(p["cheapest_any"]["item_cost"] for p in b["per_line"] if p["cheapest_any"])
            inv = (best is not None and (single is None or best["total"] <= single["total"] + 1e-6)
                   and (ap is None or b["saving"] is None or b["saving"] >= -1e-6))
            desc = " + ".join(f"{x['query']}{' x' + str(x['tablets']) if x['tablets'] else ''}" for x in rx)
            msg = (f"{'PASS' if inv else 'FAIL'}  {desc}: best ₹{best['total'] if best else '—'}"
                   f" ({len(best['stores']) if best else 0} orders) | one pharmacy ₹{single['total'] if single else '—'}"
                   f" | as prescribed ₹{ap['total'] if ap else '—'} | items at cheapest alone (before delivery) ₹{round(alone, 2)}"
                   f" | saving ₹{b['saving']} [{cost} cr]")
            print("  " + msg)
            rx_lines.append(msg)

    passed = sum(1 for r in rows if r[1])
    report = ["# Reference check", "", f"PIN {PIN} · {time.strftime('%Y-%m-%d %H:%M')} · {spent} credits spent", "",
              f"**{passed} of {len(rows)} medicines at or below the cheapest pharmacy reference** (price per tablet; "
              "ours is delivered, Chemist180 ships free).", "",
              "| Medicine | Ours (per tablet, delivered) | Cheapest reference | Result |", "|---|---|---|---|"]
    for med, ok, ours_tab, best, target, cost, why, _ in rows:
        o = f"₹{ours_tab:.2f} {best['brand']} @ {best['platform']}" if best else "—"
        t = f"₹{target[1]:.2f} {target[0]}" if target else "no reference"
        report.append(f"| {med} | {o} | {t} | {'PASS' if ok else 'FAIL: ' + why} |")
    if rx_lines:
        report += ["", "## Prescriptions", ""] + [f"- {ln}" for ln in rx_lines]
    open(os.path.join(ROOT, "scripts", "reference_report.md"), "w", encoding="utf-8").write("\n".join(report) + "\n")
    print(f"\n{passed}/{len(rows)} medicines PASS · {spent} credits spent · report: scripts/reference_report.md")
    return not misses


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1:] or None) else 1)
