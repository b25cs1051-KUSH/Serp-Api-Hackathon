from pharmawatch.search import search_prices, _get_cache
import json

# Flush stale cached result
cache = _get_cache(verbose=False)
cache.flush()
print("Cache flushed.")

result = search_prices("Metformin 500mg")
sr = result.get("shopping_results", [])
print(f"\nshopping_results count: {len(sr)}")
if sr:
    for item in sr[:3]:
        print(f"  {item.get('source', 'N/A'):25s} | {item.get('price', 'N/A'):10s} | {item.get('title', '')[:50]}")
else:
    err = result.get("error", "no error field")
    print(f"Error: {err}")
    print(f"Keys: {list(result.keys())}")
