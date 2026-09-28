"""
test_p5_generics.py — Checks for generics.py.

    python scripts/test_p5_generics.py                      # offline checks (0 SerpApi credits, no Gemini)
    python scripts/test_p5_generics.py --llm "dollo 650" …  # Gemini matching only (0 SerpApi credits)
    python scripts/test_p5_generics.py "Stamlo 5" 110001 --cache-only   # replay from Redis, 0 credits;
                                                            # lists what a live run would still spend
    python scripts/test_p5_generics.py "Dolo 650" 110001    # live: searches every brand in the entry
                                                            # (1 credit per uncached brand + 1 per
                                                            # cheaper alternative's direct link)
"""

import sys
import time
import warnings
from collections import Counter

from pharmawatch import pipeline
from pharmawatch.comparator import rank_by_landed_price
from pharmawatch.search import pick_store_link
from pharmawatch.generics import (
    _prepare,
    compare_to_reference,
    estimate_pack_size,
    find_composition,
    group_matcher,
    parse_pack_size,
    pick_candidates,
    THIN_RESULT_TTL,
    thin_result_ttl,
    title_matches_brand,
)
from pharmawatch.medicines import resolve, same_composition
from serpapi_cache import SerpApiCache
from serpapi_cache.backends import BaseBackend
from serpapi_cache.cache import _params_signature

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def check(name, got, expected):
    ok = got == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" + ("" if ok else f" (expected {expected!r})"))
    return ok


class DictBackend(BaseBackend):
    """In-memory stand-in for RedisBackend."""

    def __init__(self):
        self.rows = {}

    def set(self, key, value, embedding, ttl, query_text="", params_sig=""):
        self.rows[key] = {"key": key, "value": value, "embedding": embedding, "query_text": query_text,
                          "params_sig": params_sig or None}

    def get_all(self):
        return list(self.rows.values())

    def get_by_key(self, key):
        return self.rows[key]["value"] if key in self.rows else None

    def delete(self, key):
        self.rows.pop(key, None)

    def flush(self):
        self.rows.clear()

    def size(self):
        return len(self.rows)


def check_exact_only_cache() -> list:
    """Similar names ('Dolo 650' / 'Dola 650') share a semantic hit but never an exact_only one."""
    cache = SerpApiCache(api_key="offline", backend=DictBackend(), similarity_threshold=0.5, verbose=False)
    cache._load_model = lambda: None
    cache._embed = lambda text: [1.0, 0.0]                      # every query "identical" semantically
    cache._call_serpapi = lambda params: {"q": params["q"]}     # echo instead of spending a credit
    shop = {"engine": "google_shopping", "gl": "in"}
    cache.search({**shop, "q": "Dolo 650 price"})
    return [
        check("Semantic mode reuses a similar name", cache.search({**shop, "q": "Dola 650 price"})["q"], "Dolo 650 price"),
        check("exact_only never does", cache.search({**shop, "q": "Dola 650 price"}, exact_only=True)["q"], "Dola 650 price"),
        check("exact_only hits its own name", cache.search({**shop, "q": "dola  650 PRICE"}, exact_only=True)["q"], "Dola 650 price"),
    ]


def check_params_signature() -> list:
    """A semantic hit needs the same non-query params: page, filter, language, json_restrictor."""
    backend = DictBackend()
    cache = SerpApiCache(api_key="offline", backend=backend, similarity_threshold=0.5, verbose=False)
    cache._load_model = lambda: None
    cache._embed = lambda text: [1.0, 0.0]                      # every query "identical" semantically
    cache._call_serpapi = lambda params: {"q": params["q"], "p": {k: v for k, v in params.items() if k != "q"}}
    shop = {"engine": "google_shopping", "gl": "in", "json_restrictor": "shopping_results[].{title,price}"}
    cache.search({**shop, "q": "Dolo 650 price"})

    def served(extra, q="Dola 650 price"):
        return cache.search({**shop, **extra, "q": q})["q"]

    legacy = DictBackend()   # an entry stored before signatures existed
    legacy.set("old", {"q": "Dolo 650 price"}, [1.0, 0.0], 0, "dolo 650 price | engine:google_shopping")
    old = SerpApiCache(api_key="offline", backend=legacy, similarity_threshold=0.5, verbose=False)
    old._load_model = lambda: None
    old._embed = lambda text: [1.0, 0.0]
    old._call_serpapi = lambda params: {"q": params["q"]}
    return [
        check("Same params, reworded query: semantic hit", served({}), "Dolo 650 price"),
        check("Different json_restrictor: no reuse", served({"json_restrictor": "shopping_results[].{title}"}), "Dola 650 price"),
        check("No json_restrictor: no reuse", cache.search({"engine": "google_shopping", "gl": "in", "q": "Dolx 650 price"})["q"], "Dolx 650 price"),
        check("Page 2 (start=10): no reuse", served({"start": 10}, "Dolz 650 price"), "Dolz 650 price"),
        check("Other language (hl=hi): no reuse", served({"hl": "hi"}, "Dolq 650 price"), "Dolq 650 price"),
        check("Signature stored with the entry", all(r["params_sig"] for r in backend.get_all()), True),
        check("api_key never changes the signature", _params_signature({**shop, "api_key": "a"}) == _params_signature(shop), True),
        check("Entry without a signature: no semantic reuse", old.search({"engine": "google_shopping", "gl": "in", "q": "Dola 650 price"})["q"], "Dola 650 price"),
    ]


def check_thin_result_ttl() -> list:
    """A main search that found (almost) none of the medicine is kept 1 h, not 24 h."""
    backend = DictBackend()
    stored_ttl = {}
    real_set = backend.set

    def set_(key, value, embedding, ttl, query_text="", params_sig=""):
        stored_ttl[query_text.split(" | ")[0]] = ttl
        real_set(key, value, embedding, ttl, query_text, params_sig)
    backend.set = set_

    cache = SerpApiCache(api_key="offline", backend=backend, verbose=False)
    cache._load_model = lambda: None
    cache._embed = lambda text: [1.0, 0.0]

    def item(title, source="1mg", price="₹66.02"):
        return {"title": title, "source": source, "price": price, "extracted_price": float(price[1:]),
                "product_link": "https://www.google.co.in/shopping/product/1"}
    good = {"shopping_results": [item("Stamlo 5MG Tablet", "Chemist180"), item("Stamlo 5 Tablet"),
                                 item("Stamlo-5 Tablet 30's", "Apollo247", "₹80.00")]}
    bad = {"shopping_results": [item("Amlopres 5 mg Tablet"), item("Stamlo Beta Tablet 15's", "Apollo247"),
                                item("Stamlo D Tab", "MedPlusMart"), item("Stamlo 5MG Tablet", "Chemist180")]}
    shop = {"engine": "google_shopping", "gl": "in"}
    ttl_for = thin_result_ttl("Stamlo 5")
    cache._call_serpapi = lambda params: good
    cache.search({**shop, "q": "stamlo 5 price"}, ttl=86_400, exact_only=True, ttl_for=ttl_for)
    cache._call_serpapi = lambda params: bad
    cache.search({**shop, "q": "stamlo 5 mg price"}, ttl=86_400, exact_only=True, ttl_for=ttl_for)
    cache._call_serpapi = lambda params: bad
    cache.search({**shop, "q": "no check price"}, ttl=86_400, exact_only=True)

    def boom(result):
        raise ValueError("bad check")
    cache.search({**shop, "q": "broken check price"}, ttl=86_400, exact_only=True, ttl_for=boom)
    cache.wait_for_writes()
    return [
        check("3 real listings: full 24 h TTL", stored_ttl["stamlo 5 price"], 86_400),
        check("1 real listing among look-alikes: 1 h TTL", stored_ttl["stamlo 5mg price"], THIN_RESULT_TTL),
        check("No ttl_for: TTL unchanged", stored_ttl["no check price"], 86_400),
        check("Failing ttl_for: result still cached, normal TTL", stored_ttl["broken check price"], 86_400),
    ]


def check_async_store() -> list:
    """A miss returns before its (slow) Redis write finishes; the next identical search still hits."""
    class SlowBackend(DictBackend):
        def set(self, *args, **kwargs):
            time.sleep(0.5)
            super().set(*args, **kwargs)

    cache = SerpApiCache(api_key="offline", backend=SlowBackend(), verbose=False)
    cache._load_model = lambda: None
    cache._embed = lambda text: [1.0, 0.0]
    calls = []
    cache._call_serpapi = lambda params: calls.append(1) or {"q": params["q"]}
    params = {"engine": "google_shopping", "q": "Dolo 650 price"}
    t0 = time.perf_counter()
    cache.search(params, exact_only=True)
    miss_s = time.perf_counter() - t0
    cache.search(params, exact_only=True)
    return [
        check("Miss doesn't wait for Redis write", miss_s < 0.25, True),
        check("Repeat search hits (1 API call)", len(calls), 1),
    ]


def check_parallel_pipeline() -> list:
    """Main search first; the 3 substitute searches start as soon as it lands and run side by side."""
    started = {}
    t0 = time.perf_counter()

    def fake_ranked(name, pin, exact_only, verbose):
        started[name] = time.perf_counter() - t0
        time.sleep(0.4)
        return [{"platform": "1mg", "medicine_name": f"{name} Strip Of 10 Tablets", "price_inr": 50.0,
                 "delivery_status": "free", "total_landed_cost": 50.0}]

    real = pipeline.ranked_listings
    pipeline.ranked_listings = fake_ranked
    try:
        events = []
        for kind, payload in pipeline.search_medicine_stream("Dolo 650", "110001", resolve_links=False, use_llm=False):
            events.append((kind, round(time.perf_counter() - t0, 1)))
            if kind == "alternatives":
                searched = payload["suggested_alternatives"]
    finally:
        pipeline.ranked_listings = real
    alt_starts = [started[b] for b in searched]
    return [
        check("Main streamed first (~0.4s)", events[0], ("main", 0.4)),
        check("Extra searches: generic salt + Cipla brand", searched, ["Paracetamol 650mg tablet generic", "Paracip 650"]),
        check("Substitutes start right after main", all(0.35 < s < 0.55 for s in alt_starts), True),
        check("All done in ~0.8s", events[-1], ("alternatives", 0.8)),
        check("Event order (links off)", [k for k, _ in events], ["main", "alternatives"]),
    ]


def check_stamlo_pipeline() -> list:
    """
    Fixes 1+3+4+5+6 end to end on the Stamlo 5 run's real titles/prices, with stubbed searches and links:
    look-alikes dropped, Stamlo listing found in a substitute search, Amlopres found via pooling,
    estimated packs, alternatives sent before the (slower) main links, links only where due.
    """
    def row(platform, title, price, token):
        return {"platform": platform, "medicine_name": title, "price_inr": price, "page_token": token}

    searches = {
        "Stamlo 5": [row("Chemist180", "Stamlo 5MG Tablet", 66.02, "t-stamlo-c180"),
                     row("1mg", "Esta 5 Tablet", 48.50, "t-esta"),
                     row("1mg", "Stamlo Bis 5 Tablet", 86.20, "t-bis"),
                     row("Apollo Pharmacy", "Stamlo-5 Tablet 30's", 80.0, "t-stamlo-apollo")],
        "Amlokind 5": [row("Chemist180", "Amlokind 5MG Tablet", 19.41, "t-amlokind-c180"),
                       row("Apollo Pharmacy", "Amlokind-5 Tablet 15's", 23.50, "t-amlokind-apollo"),
                       row("Apollo Pharmacy", "Amlokind-AT 5 mg/50 mg Tablet 15's", 61.0, "t-at"),
                       row("PharmEasy", "Stamlo 5Mg Strip Of 30 Tablets", 61.99, "t-stamlo-pe")],
        "Amtas 5": [row("Kogland Commerce", "Amlopres 5 mg Tablet - Strip of 30", 66.11, "t-amlopres-kog")],
        "Amlopres 5": [row("Magicine Pharma", "Amlopres 2.5 mg Tablet (15 Tab)", 25.23, "t-2.5")],
    }
    requested = []

    def run(query, in_catalogue=True, failing=None):
        def fake_ranked(name, pin, exact_only, verbose):
            time.sleep(0.2 if name not in searches or name == "Stamlo 5" else 0.3)
            if name == failing:
                raise RuntimeError("SerpApi error")
            return rank_by_landed_price([dict(r) for r in searches.get(name, searches["Stamlo 5"])], pin)

        def fake_match(q, use_llm, resolution=None):
            return find_composition("Stamlo 5", use_llm=False) if in_catalogue else None

        def fake_pick(match, found, n=3):
            return ["Amlokind 5", "Amtas 5", "Amlopres 5"]

        def fake_link(token, target_platform=None, verbose=False):
            requested.append(token)
            time.sleep(1.0 if "stamlo" in token else 0.3)   # main links slower than the alternative's
            return f"https://{target_platform}/{token}"

        real = pipeline.ranked_listings, pipeline.find_composition, pipeline.get_direct_merchant_link, pipeline.pick_candidates
        (pipeline.ranked_listings, pipeline.find_composition, pipeline.get_direct_merchant_link,
         pipeline.pick_candidates) = fake_ranked, fake_match, fake_link, fake_pick
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return list(pipeline.search_medicine_stream(query, "110001"))
        finally:
            (pipeline.ranked_listings, pipeline.find_composition, pipeline.get_direct_merchant_link,
             pipeline.pick_candidates) = real

    events = run("Stamlo 5")
    got = dict(events)
    titles = lambda rows: [r["medicine_name"] for r in rows]
    alt = got["alternatives"]
    cheaper = alt["cheaper_alternatives"][0] if alt["cheaper_alternatives"] else {}
    by_brand = {r["brand"]: r for r in alt["other_alternatives"]}
    main_links = {r["medicine_name"]: r["direct_link"] for r in got["main_links"]}
    link_calls = sorted(requested)

    typo = dict(run("Stamloo 5"))                       # spelling corrected from the medicine index
    outside = run("Stamlo 5", in_catalogue=False)       # not in the medicine index
    failed = dict(run("Stamlo 5", failing="Amtas 5"))   # one substitute search errors
    return [
        check("Typo: main list uses the corrected name at once", titles(typo["main"]),
              ["Stamlo 5MG Tablet", "Stamlo-5 Tablet 30's"]),
        check("Typo: pooled like any search", titles(typo["main_update"]),
              ["Stamlo 5MG Tablet", "Stamlo-5 Tablet 30's", "Stamlo 5Mg Strip Of 30 Tablets"]),
        check("Not in catalogue: main + links still sent, alternatives None",
              [(k, v is None) for k, v in outside], [("main", False), ("alternatives", True), ("main_links", False)]),
        # Amlopres 5 is only listed in the Amtas search here, so it goes too; the rest carries on.
        check("Failed substitute search only loses its own listings",
              (failed["alternatives"]["not_found"], len(failed["alternatives"]["cheaper_alternatives"])),
              (["Amtas 5", "Amlopres 5"], 1)),
    ] + [
        check("Event order", [k for k, _ in events], ["main", "main_update", "alternatives", "main_links"]),
        check("Main: look-alikes dropped", titles(got["main"]), ["Stamlo 5MG Tablet", "Stamlo-5 Tablet 30's"]),
        check("Main update: Stamlo from Amlokind search added", "Stamlo 5Mg Strip Of 30 Tablets" in titles(got["main_update"]), True),
        check("Reference = Chemist180, pack estimated",
              (alt["reference"]["platform"], alt["reference"]["pack_size"], alt["reference"]["pack_estimated"]),
              ("Chemist180", 30, True)),
        check("Cheaper: Amlokind @ Chemist180, estimated",
              (cheaper.get("brand"), cheaper.get("platform"), cheaper.get("estimated")), ("Amlokind 5", "Chemist180", True)),
        check("Cheaper alt has its direct link", cheaper.get("direct_link"), "https://Chemist180/t-amlokind-c180"),
        check("Amlopres found via pooling (Amtas search)", by_brand.get("Amlopres 5", {}).get("platform"), "Kogland Commerce"),
        check("Not-cheaper alt: direct_link empty", by_brand.get("Amlopres 5", {}).get("direct_link"), ""),
        check("Amtas genuinely not found", alt["not_found"], ["Amtas 5"]),
        check("Main links on all top rows", all(main_links.values()), True),
        check("No link spent on look-alikes", sorted(t for t in requested if t in ("t-esta", "t-bis", "t-at")), []),
        check("Link lookups made", link_calls,
              sorted(["t-stamlo-c180", "t-stamlo-apollo", "t-stamlo-pe", "t-amlokind-c180"])),
    ]


def run_checks() -> bool:
    def what(q):
        r = resolve(q)
        return (r["kind"], r.get("brand") or r.get("label")) if r["kind"] in ("brand", "salt") else (r["kind"], None)

    def group_brands(q):
        return {g["brand"].lower() for g in same_composition(resolve(q)["comp_key"])}

    def options(q):
        return [o["query"] for o in resolve(q).get("options", [])][:3]
    def listing(title, price, status="charged", landed=None):
        return {"medicine_name": title, "price_inr": price, "delivery_status": status,
                "total_landed_cost": landed if landed is not None else price, "platform": "x"}

    stamlo_known = [(15, 40.0), (30, 80.0), (30, 61.99), (30, 83.9)]
    stamlo_rows = [
        listing("Stamlo-5 Tablet 15's", 40.0, landed=120.0),
        listing("Stamlo-5 Tablet 30's", 80.0, landed=160.0),
        listing("Stamlo 5Mg Strip Of 30 Tablets", 61.99, landed=181.99),
        listing("Stamlo 5 Tablet (30s)", 83.9, status="unserviceable", landed=None),
        listing("Stamlo 5MG Tablet", 66.02, status="free"),
    ]

    gliclazide = group_brands("Gliclazide 80mg")
    sitagliptin = group_brands("Sitagliptin 50mg")
    sita_match = group_matcher(find_composition("Sitagliptin 50mg", use_llm=False))
    results = [
        # What the search names (medicine index built from the Indian Medicine Dataset)
        check("Brand", what("Stamlo 5"), ("brand", "Stamlo 5")),
        check("Hyphen / mg / tablet ignored", what("dolo-650mg tablet"), ("brand", "Dolo 650")),
        check("SR brand", what("Glyciphage SR 500"), ("brand", "Glyciphage SR 500mg")),
        check("Brand without strength", what("Pan-D"), ("brand", "Pan-D")),
        check("Salt + strength", what("Gliclazide 80mg"), ("salt", "Gliclazide 80mg tablet")),
        check("Salt + strength + SR", what("Metformin 500mg SR"), ("salt", "Metformin 500mg tablet SR")),
        check("Salt without strength asks", (resolve("paracetamol")["kind"], options("paracetamol")),
              ("ambiguous", ["Paracetamol 650mg", "Paracetamol 500mg", "Paracetamol 1000mg"])),
        check("Brand without strength asks", resolve("Dolo")["kind"], "ambiguous"),
        check("Spelling corrected", (what("dollo 650"), resolve("dollo 650")["matched_by"]), (("brand", "Dolo 650"), "fuzzy")),
        check("Telma 40 H is Telma-H (HCTZ), never Telma-AM H", what("Telma 40 H"), ("brand", "Telma H")),
        check("Unknown medicine", resolve("xyzqq 10")["kind"], "none"),
        # Same-composition groups: combinations are other medicines
        check("Gliclazide 80: Glizid 80 in, Glizid-M / Reclimet out",
              ("glizid 80" in gliclazide, any(b.startswith("glizid-m") or b.startswith("reclimet") for b in gliclazide)), (True, False)),
        check("Sitagliptin 50: Januvia in, Istamet (+metformin) out",
              ("januvia 50mg" in sitagliptin, any(b.startswith("istamet") for b in sitagliptin)), (True, False)),
        check("IR and SR are different groups", resolve("Metformin 500mg")["comp_key"] != resolve("Metformin 500mg SR")["comp_key"], True),
        check("Group sorted by list price per unit",
              [g["unit_mrp"] for g in same_composition(resolve("Dolo 650")["comp_key"]) if g["unit_mrp"] is not None][:5]
              == sorted(g["unit_mrp"] for g in same_composition(resolve("Dolo 650")["comp_key"]) if g["unit_mrp"] is not None)[:5], True),
        # Titles from the real Sitagliptin 50mg search
        check("Setalin 50 (sertraline) is not sitagliptin", sita_match("Setalin 50MG Tab"), None),
        check("Sitacip M 50/500 rejected", sita_match("Cipla Sitacip M 50/500mg Tablets 10s"), None),
        check("Istamet 50/500 rejected", sita_match("Istamet 50mg/500mg Tablet"), None),
        check("Januvia 50 accepted", (sita_match("Januvia 50mg Tablet") or {}).get("brand"), "Januvia 50mg"),
        check("Sitabite 50 accepted (nobody searched it)", (sita_match("Sitabite 50 mg Tablet 10's") or {}).get("brand"), "Sitabite 50mg"),
        # Substitute searches
        check("Brand search: generic salt + Cipla's biggest brand", pick_candidates(find_composition("Stamlo 5", use_llm=False), []),
              ["Amlodipine 5mg tablet generic", "Amlopres 5"]),
        check("SR brand's generic search keeps SR", pick_candidates(find_composition("Glyciphage SR 500", use_llm=False), [])[0],
              "Metformin 500mg SR tablet generic"),
        check("Cipla brand family beats thin line (Paracip, not Cipmol)",
              pick_candidates(find_composition("Dolo 650", use_llm=False), [])[1], "Paracip 650"),
        check("Salt search without a Cipla brand: widest-range maker's brand",
              pick_candidates(find_composition("Gliclazide 80mg", use_llm=False), []), ["Gliclazide 80mg tablet generic", "Nuzide 80mg"]),
        # Title filter (titles taken from cached shopping results)
        check("Exact brand title", title_matches_brand("Dolo 650mg Strip Of 15 Tablets", "Dolo 650"), True),
        check("Dolo-650 hyphen title", title_matches_brand("Dolo-650 Tablet 15's", "Dolo 650"), True),
        check("Dolopar ≠ Dolo", title_matches_brand("Dolopar 650Mg Strip Of 15 Tablets", "Dolo 650"), False),
        check("Wrong strength", title_matches_brand("Dolo 500 Tablet 10's", "Dolo 650"), False),
        check("Suspension rejected", title_matches_brand("Dolo 650 Suspension 60ml", "Dolo 650"), False),
        check("Pan D ≠ Pan 40", title_matches_brand("Pan D Capsule (30mg/40mg) (15caps)", "Pan 40"), False),
        check("Pan D matches Pan-D", title_matches_brand("Pan D Capsule (30mg/40mg) (15caps)", "Pan-D"), True),
        check("SR ≠ IR brand", title_matches_brand("Glyciphage SR 500 Tablet", "Glyciphage 500"), False),
        # Fix 2 — look-alike combinations (titles from the Stamlo 5 live run)
        check("Every Gliclazide 80 brand matches its own name",
              [b for b in gliclazide if not title_matches_brand(f"{b} Tablet 15's", b)], []),
        check("Amlokind-AT ≠ Amlokind 5", title_matches_brand("Amlokind-AT 5 mg/50 mg Tablet 15's", "Amlokind 5"), False),
        check("Amlokind At 5/50 ≠ Amlokind 5", title_matches_brand("Amlokind At 5/50Mg Strip Of 15 Tablets", "Amlokind 5"), False),
        check("Stamlo Bis ≠ Stamlo 5", title_matches_brand("Stamlo Bis 5 Tablet 10", "Stamlo 5"), False),
        check("Stamlo Beta ≠ Stamlo 5", title_matches_brand("Stamlo Beta 5/50MG", "Stamlo 5"), False),
        check("Met Stamlo ≠ Stamlo 5", title_matches_brand("Met Stamlo 5/50mg Capsule ER 10s", "Stamlo 5"), False),
        check("Stamlo T 5/40 ≠ Stamlo 5", title_matches_brand("Stamlo T 5/40mg Tablet 10s", "Stamlo 5"), False),
        check("Strength pair without brand strength ok", title_matches_brand("Augmentin 625 Tablet (500mg/125mg)", "Augmentin 625"), True),
        check("Real Stamlo 5 kept", title_matches_brand("Stamlo-5 Tablet 30's", "Stamlo 5"), True),
        check("Real Amlokind 5 kept", title_matches_brand("Amlokind 5Mg Strip Of 15 Tablets", "Amlokind 5"), True),
        # Telma 40 live run — combinations written as separate doses / short words
        check("Telma Az 40mg 8mg ≠ Telma 40", title_matches_brand("Telma Az 40Mg 8Mg Tablet", "Telma 40"), False),
        check("Telma Act ≠ Telma 40", title_matches_brand("Telma Act 40Mg 5Mg 6.25Mg Tablet", "Telma 40"), False),
        check("Telma Nb ≠ Telma 40", title_matches_brand("Telma Nb 40MG Tab", "Telma 40"), False),
        check("Telmikind Amh ≠ Telmikind 40", title_matches_brand("Telmikind Amh 40MG Tab", "Telmikind 40"), False),
        check("Real Telma 40 (maker name first) kept",
              title_matches_brand("Glenmark Telma 40mg Tablets for Blood Pressure Control", "Telma 40"), True),
        check("'(Pack-30)' is not a variant", title_matches_brand("Stamlo 5 Mg Tab (Pack-30)", "Stamlo 5"), True),
        check("Site name '| 1mg' is not a dose / 'View' after dose ignored",
              title_matches_brand("Buy Crocin 650mg Tablet Online: View Uses, Side Effects, Price, Substitutes | 1mg", "Crocin 650"), True),
        check("Met XL brand keeps its own 'met'", title_matches_brand("Met XL 25 Tablet 10's", "Met XL 25"), True),
        check("Injection allowed for insulin", title_matches_brand("Lantus Injection 3ml", "Lantus", True), True),
        # Pack size
        check("Strip of 15", parse_pack_size("Pacimol 650Mg Strip Of 15 Tablets", "Pacimol 650"), 15),
        check("15's", parse_pack_size("Dolo-650 Tablet 15's", "Dolo 650"), 15),
        check("10'S", parse_pack_size("Paracip-650 Tablet 10'S", "Paracip 650"), 10),
        check("(15tab)", parse_pack_size("Calpol Tablet (500mg) (15tab)", "Calpol 500"), 15),
        check("(Pack-20)", parse_pack_size("Glycomet Sr 500 Mg Tab (Pack-20)", "Glycomet SR 500"), 20),
        check("10s", parse_pack_size("Pantophyll D 30/40mg Capsule SR 10s", "Pantophyll D"), 10),
        check("Strength not a pack", parse_pack_size("Amaryl 2 Tablet", "Amaryl 2"), None),
        check("Decimal strength ignored", parse_pack_size("Clonotril 0.5 Tablet", "Clonotril 0.5"), None),
        check("No pack in title", parse_pack_size("Calpol 650 Tablet", "Calpol 650"), None),
        check("Truemeds 'Tablet 15'", parse_pack_size("Amlokind 5 Tablet 15", "Amlokind 5"), 15),
        check("Trailing strength not a pack", parse_pack_size("Amaryl Tablet 2", "Amaryl 2"), None),
        # Fix 3 — estimated pack sizes (Stamlo 5 known packs/prices from the live run)
        check("Most common pack (Chemist180 Stamlo ₹66.02)", estimate_pack_size(66.02, stamlo_known), 30),
        check("Tie → closest per-tablet price (₹40)", estimate_pack_size(40, [(15, 40.0), (30, 80.0)]), 15),
        check("Tie → closest per-tablet price (₹80)", estimate_pack_size(80, [(15, 40.0), (30, 80.0)]), 30),
        check("Telma 1mg ₹99.80 → 15-strip (price-consistent), not the commoner 30",
              estimate_pack_size(99.80, [(15, 108.0), (30, 216.5), (30, 193.0), (30, 177.71), (30, 166.87)]), 15),
        check("Implausible price → no estimate", estimate_pack_size(10, [(30, 80.0)]), None),
        check("Nothing known → no estimate", estimate_pack_size(66.02, []), None),
    ]
    prepared = {r["medicine_name"]: r for r in _prepare(stamlo_rows, "Stamlo 5", False)}
    results += [
        check("Stated pack not flagged", (prepared["Stamlo-5 Tablet 30's"]["pack_size"],
                                          prepared["Stamlo-5 Tablet 30's"]["pack_estimated"]), (30, False)),
        check("Missing pack estimated + flagged", (prepared["Stamlo 5MG Tablet"]["pack_size"],
                                                   prepared["Stamlo 5MG Tablet"]["pack_estimated"]), (30, True)),
        check("Estimated per-tablet landed", prepared["Stamlo 5MG Tablet"]["unit_landed_cost"], 2.2),
        check("Non-deliverable still informs estimate", "Stamlo 5 Tablet (30s)" in prepared, False),
    ]
    est = compare_to_reference({"pack_size": 15, "pack_estimated": True, "unit_landed_cost": 1.29, "total_landed_cost": 19.41},
                               prepared["Stamlo 5MG Tablet"])
    results.append(check("Saving marked estimated", (est["is_cheaper"], est["estimated"]), (True, True)))

    ref = {"pack_size": 15, "unit_landed_cost": 2.0, "total_landed_cost": 30.0}
    per_tab = compare_to_reference({"pack_size": 10, "unit_landed_cost": 1.5, "total_landed_cost": 15.0}, ref)
    total = compare_to_reference({"pack_size": None, "unit_landed_cost": None, "total_landed_cost": 33.0}, ref)
    results += [
        check("Per-tablet compare", (per_tab["price_basis"], per_tab["savings"], per_tab["is_cheaper"]),
              ("per_tablet", 0.5, True)),
        check("Falls back to total", (total["price_basis"], total["is_cheaper"]), ("total", False)),
    ]
    # Fix 6 — direct link must belong to the listing's own pharmacy
    stores = [{"name": "Tata 1mg", "link": "https://www.1mg.com/drugs/x"},
              {"name": "Apollo 247", "link": "https://www.apollopharmacy.in/medicine/x"}]
    results += [
        check("Apollo 247 matched to Apollo Pharmacy", pick_store_link(stores, "Apollo Pharmacy"),
              "https://www.apollopharmacy.in/medicine/x"),
        check("Pharmacy not among stores → None (no other store's link)", pick_store_link(stores, "PharmEasy"), None),
        check("No target → first store", pick_store_link(stores, None), "https://www.1mg.com/drugs/x"),
        check("Stores without links ignored", pick_store_link([{"name": "1mg"}], "1mg"), None),
    ]
    results += check_exact_only_cache()
    results += check_params_signature()
    results += check_thin_result_ttl()
    results += check_async_store()
    results += check_parallel_pipeline()
    results += check_stamlo_pipeline()
    return all(results)


def run_llm(queries):
    for q in queries:
        m = find_composition(q)
        if m is None:
            print(f"  {q!r:<32} → not in the medicine index")
        else:
            print(f"  {q!r:<34} searched={m['matched_brand'] or '(generic name)'} → {m['alternatives']}"
                  f"  [{m['matched_by']}: {m['reason']}]")


def _pack(row: dict) -> str:
    if not row.get("pack_size"):
        return "pack ?"
    return f"~{row['pack_size']} tabs (estimated)" if row.get("pack_estimated") else f"{row['pack_size']} tabs"


def _fmt(row: dict) -> str:
    unit = f" · {'~' if row.get('pack_estimated') else ''}₹{row['unit_landed_cost']:.2f}/tab, {_pack(row)}" \
        if row["unit_landed_cost"] else ""
    return f"{row['brand']:<20} {row['platform']:<16} ₹{row['total_landed_cost']:.2f} landed{unit}"


def run_live(query: str, pincode: str, cache_only: bool = False):
    """cache_only: serve everything from Redis; any lookup that would spend a credit is blocked and listed."""
    from pharmawatch.search import _get_cache, warm_up

    print(f"Warm-up (Redis + embedding model): {warm_up(verbose=False):.0f} ms")
    cache = _get_cache(verbose=False)
    blocked = []
    if cache_only:
        def refuse(params):
            blocked.append(params.get("q") or f"page_token …{params.get('page_token', '')[-10:]}")
            raise RuntimeError("cache-only run: this lookup would spend a SerpApi credit")
        cache._call_serpapi = refuse
    cache.pop_call_log()
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for kind, payload in pipeline.search_medicine_stream(query, pincode):
            at = f"[t+{(time.perf_counter() - t0) * 1000:>5.0f} ms]"
            if kind == "main":
                print(f"\n{at} EVENT main — {len(payload)} listings that are '{query}' (direct links pending)")
                print_main(payload, pincode)
            elif kind == "main_update":
                print(f"\n{at} EVENT main_update — {len(payload)} listings after adding matches from substitute searches")
                print_main(payload, pincode)
            elif kind == "main_links":
                print(f"\n{at} EVENT main_links — top {pipeline.MAIN_DIRECT_LINKS} direct links")
                print_main(payload, pincode)
            else:
                print(f"\n{at} EVENT alternatives")
                print_alternatives(query, payload)
    cache.wait_for_writes()
    print_call_log(cache.pop_call_log(), t0)
    if cache_only:
        print(f"\n  Blocked in cache-only mode (each would cost 1 credit live): {len(blocked)}")
        for b in blocked:
            print(f"    {b}")
    for w in caught:
        print(f"  warning: {str(w.message)[:120]}")


def print_main(rows, pincode):
    print(f"  MAIN LISTINGS (ranked by landed price to {pincode}):")
    for r in rows:
        landed = f"₹{r['total_landed_cost']:.2f}" if r["total_landed_cost"] is not None else "—"
        print(f"  #{r['rank']:<2} {r['platform']:<16} ₹{r['price_inr']:>8.2f} → {landed:>9}  {r['medicine_name'][:55]}")
        print(f"      delivery: {r['delivery_label']}")
        print(f"      direct_link: {r.get('direct_link') or '(empty)'}")


def print_call_log(log, t0):
    print("\nSERPAPI CALL LOG (times relative to search start):")
    print(f"  {'start':>6} {'end':>6} {'took':>6}  {'engine':<25} {'outcome':<22} {'credit':<6} purpose")
    for e in sorted(log, key=lambda e: e["start"]):
        s, end = (e["start"] - t0) * 1000, (e["end"] - t0) * 1000
        print(f"  {s:>6.0f} {end:>6.0f} {end - s:>6.0f}  {e['engine']:<25} {e['outcome']:<22} "
              f"{'1' if e['credit'] else '0':<6} {e['tag']}  [{e['query']}]")
    by_purpose = Counter((e["tag"] or "").split(":")[0] for e in log if e["credit"])
    print(f"\n  SerpApi credits used: {sum(e['credit'] for e in log)} of {len(log)} lookups")
    for purpose, n in by_purpose.items():
        print(f"    {n} × {purpose}")


def print_alternatives(query: str, res):
    if res is None:
        print(f"\n'{query}' is not in the medicine index — no generic alternatives.")
        return
    print(f"\nTimings: {res['timings']}")
    c = res["composition"]
    print(f"\n{c['name']} — {c['drug_class']}\nSubstitutes picked: {', '.join(res['suggested_alternatives'])}")
    ref = res["reference"]
    print(f"Matched by {res['matched_by']}: {res['match_reason']}")
    print(f"\nYou searched: {res['matched_brand'] or '(salt name)'}"
          + (f"\n  cheapest:  {_fmt(ref)}" if ref else "\n  no deliverable listing to compare against"))
    print(f"\nCheaper generic alternatives ({len(res['cheaper_alternatives'])}):")
    for r in res["cheaper_alternatives"]:
        basis = "per tablet" if r["price_basis"] == "per_tablet" else "total"
        est = " — ESTIMATED (pack size inferred)" if r.get("estimated") else ""
        print(f"  {_fmt(r)}\n      → save ₹{r['savings']:.2f} {basis} ({r['savings_pct']}%){est}\n"
              f"      {r['medicine_name']}\n      direct_link: {r['direct_link'] or '(empty)'}")
    print(f"\nOther alternatives ({len(res['other_alternatives'])}):")
    for r in res["other_alternatives"]:
        extra = ""
        if "savings" in r:
            extra = f"\n      → costs ₹{-r['savings']:.2f} more ({r['price_basis']}){' — estimated' if r.get('estimated') else ''}"
        print(f"  {_fmt(r)}{extra}\n      {r['medicine_name']}\n      direct_link: {r['direct_link'] or '(empty)'}")
    if res["not_found"]:
        print(f"\nNo deliverable listing found: {', '.join(res['not_found'])}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--llm"]:
        run_llm(sys.argv[2:])
        sys.exit(0)
    if len(sys.argv) > 1:
        args = [a for a in sys.argv[1:] if a != "--cache-only"]
        run_live(args[0], args[1] if len(args) > 1 else "110001", cache_only="--cache-only" in sys.argv)
        sys.exit(0)
    passed = run_checks()
    print("\nALL PASSED" if passed else "\nSOME CHECKS FAILED")
    sys.exit(0 if passed else 1)
