"""
test_hosting.py — offline checks for the hosted-demo switches in serpapi_cache (0 credits, no Redis).

    python scripts/test_hosting.py

  SERPAPI_ROTATE_KEYS   key 1 out of searches → same request on SERP_API_KEY_2; off by default
  DAILY_CREDIT_BUDGET   N calls per UTC day, then CreditBudgetExceeded; counted in Redis
  EMBEDDING_BACKEND     onnx gives the same vectors as sentence-transformers
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import serpapi

from serpapi_cache import CreditBudgetExceeded, SerpApiCache
from serpapi_cache.cache import SerpApiError

KEY1, KEY2 = "KEY_ONE_SECRET", "KEY_TWO_SECRET"
failures = []


def check(label, ok):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        failures.append(label)


class FakeRedis:
    def __init__(self):
        self.d = {}

    def incr(self, k):
        self.d[k] = self.d.get(k, 0) + 1
        return self.d[k]

    def decr(self, k):
        self.d[k] -= 1
        return self.d[k]

    def expire(self, k, s):
        return True


class FakeBackend:
    def __init__(self, r=None):
        self._r = r


def fake_client(spent, empty_keys):
    """serpapi.Client stand-in: keys in empty_keys answer like SerpApi's 429, others succeed."""
    class Client:
        def __init__(self, api_key, timeout=None):
            self.key = api_key

        def search(self, params):
            spent.append(self.key)
            if self.key in empty_keys:
                raise Exception(f"429 Client Error: Too Many Requests for url: "
                                f"https://serpapi.com/search?q=x&api_key={self.key}")
            return {"served_by": self.key}
    return Client


def make_cache(env, backend):
    for k in ("SERPAPI_ROTATE_KEYS", "SERP_API_KEY_2", "DAILY_CREDIT_BUDGET"):
        os.environ.pop(k, None)
    os.environ.update(env)
    return SerpApiCache(api_key=KEY1, backend=backend, verbose=False)


real_client = serpapi.Client
try:
    print("\nKey rotation")
    spent = []
    serpapi.Client = fake_client(spent, {KEY1})
    c = make_cache({"SERPAPI_ROTATE_KEYS": "1", "SERP_API_KEY_2": KEY2}, FakeBackend())
    out = c._call_serpapi({"q": "x"})
    check("key 1 out of searches → answered by key 2", out == {"served_by": KEY2} and spent == [KEY1, KEY2])
    spent.clear()
    c._call_serpapi({"q": "y"})
    check("later calls go straight to key 2", spent == [KEY2])

    spent.clear()
    serpapi.Client = fake_client(spent, {KEY1, KEY2})
    c = make_cache({"SERPAPI_ROTATE_KEYS": "1", "SERP_API_KEY_2": KEY2}, FakeBackend())
    try:
        c._call_serpapi({"q": "x"})
        check("both keys empty → SerpApiError", False)
    except SerpApiError as e:
        check("both keys empty → SerpApiError", True)
        check("error text has no key", KEY1 not in str(e) and KEY2 not in str(e) and "api_key=***" in str(e))

    spent.clear()
    serpapi.Client = fake_client(spent, {KEY1})
    c = make_cache({"SERP_API_KEY_2": KEY2}, FakeBackend())  # flag not set
    try:
        c._call_serpapi({"q": "x"})
        ok = False
    except SerpApiError:
        ok = True
    check("without SERPAPI_ROTATE_KEYS the second key is never used", ok and spent == [KEY1])

    print("\nDaily credit budget")
    spent.clear()
    serpapi.Client = fake_client(spent, set())
    r = FakeRedis()
    c = make_cache({"DAILY_CREDIT_BUDGET": "2"}, FakeBackend(r))
    c._call_serpapi({"q": "a"})
    c._call_serpapi({"q": "b"})
    try:
        c._call_serpapi({"q": "c"})
        check("3rd call over a budget of 2 is refused", False)
    except CreditBudgetExceeded as e:
        check("3rd call over a budget of 2 is refused", len(spent) == 2)
        check("refusal is a SerpApiError (pipeline reports it like any failed search)", isinstance(e, SerpApiError))
    check("counter lives in Redis and stays at the budget", list(r.d.values()) == [2])

    spent.clear()
    c = make_cache({"DAILY_CREDIT_BUDGET": "1"}, FakeBackend(None))  # Redis down
    c._call_serpapi({"q": "a"})
    try:
        c._call_serpapi({"q": "b"})
        ok = False
    except CreditBudgetExceeded:
        ok = True
    check("budget still enforced in memory while Redis is down", ok and len(spent) == 1)

    spent.clear()
    c = make_cache({}, FakeBackend(FakeRedis()))
    for q in "abcde":
        c._call_serpapi({"q": q})
    check("no DAILY_CREDIT_BUDGET → no limit", len(spent) == 5)
finally:
    serpapi.Client = real_client
    for k in ("SERPAPI_ROTATE_KEYS", "SERP_API_KEY_2", "DAILY_CREDIT_BUDGET"):
        os.environ.pop(k, None)

print("\nONNX embeddings")
try:
    import onnxruntime  # noqa: F401
except ImportError:
    print("  SKIP  onnxruntime not installed")
else:
    os.environ["EMBEDDING_BACKEND"] = "onnx"
    onnx_cache = make_cache({}, FakeBackend())
    os.environ.pop("EMBEDDING_BACKEND")
    pairs = [("stamlo 5 tablet price", "stamlo 5 price"), ("dolo 500 price", "dolo 650 price")]
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        torch_cache = make_cache({}, FakeBackend())
    except ImportError:
        torch_cache = None
    for a, b in pairs:
        va, vb = onnx_cache._embed(a), onnx_cache._embed(b)
        check(f"onnx vectors are unit length ({a})", abs(sum(x * x for x in va) - 1) < 1e-5)
        if torch_cache:
            ta = torch_cache._embed(a)
            same = sum(x * y for x, y in zip(va, ta))
            check(f"onnx = torch for '{a}' (cosine {same:.6f})", same > 0.99999)
            s_onnx = sum(x * y for x, y in zip(va, vb))
            s_torch = sum(x * y for x, y in zip(ta, torch_cache._embed(b)))
            check(f"similarity '{a}' vs '{b}' unchanged ({s_onnx:.4f} vs {s_torch:.4f})", abs(s_onnx - s_torch) < 1e-4)

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
