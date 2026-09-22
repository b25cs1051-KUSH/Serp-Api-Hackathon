import sys
import json
from pharmawatch.search import search_prices, search_platform_price, _get_cache

# Set UTF-8 encoding for Windows console output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    print("============================================================")
    print("  PharmaWatch Phase 2 Search Explorer & Inspector")
    print("============================================================")
    print("Commands:")
    print("  - Type any medicine name (e.g. 'Metformin 500mg', 'Atorvastatin 10mg')")
    print("  - Type 'flush' to clear cache")
    print("  - Type 'q' or 'exit' to quit\n")

    cache = _get_cache(verbose=False)

    while True:
        try:
            query = input("\nEnter medicine name [default: Metformin 500mg]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not query:
            query = "Metformin 500mg"

        if query.lower() in ("q", "quit", "exit"):
            print("Exiting.")
            break

        if query.lower() == "flush":
            cache.flush()
            print("Cache cleared successfully.")
            continue

        print(f"\nFetching search results for: '{query}'...")
        result = search_prices(query, verbose=True)

        if not result or not isinstance(result, dict):
            print("Error: Empty or non-dict response returned.")
            continue

        print("\n" + "=" * 60)
        print(" TOP-LEVEL RESPONSE KEYS:")
        print("=" * 60)
        print(list(result.keys()))

        shopping_results = result.get("shopping_results", [])
        print(f"\nTotal 'shopping_results' found: {len(shopping_results)}")

        if shopping_results:
            print("\n" + "=" * 60)
            print(" ITEM 1 (FULL JSON STRUCTURE EXAMPLE):")
            print("=" * 60)
            print(json.dumps(shopping_results[0], indent=2, ensure_ascii=False))

            print("\n" + "=" * 60)
            print(" ALL SHOPPING RESULTS SUMMARY:")
            print("=" * 60)
            for idx, item in enumerate(shopping_results, 1):
                source = item.get("source", "Unknown Source")
                price = item.get("price", "N/A")
                title = item.get("title", "No Title")
                link = item.get("link", "No Link")
                print(f"[{idx:02d}] {source:25s} | {price:12s} | {title}")
                print(f"     Link: {link}\n")
        else:
            print("\nNo 'shopping_results' field found in response.")
            print("Full Raw Response:")
            print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

