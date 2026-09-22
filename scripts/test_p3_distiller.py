import sys
import json
from pharmawatch.search import search_prices, _get_cache
from pharmawatch.distiller import distill_shopping_results

# Set UTF-8 encoding for Windows console output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    print("============================================================")
    print("  PharmaWatch Phase 3 Distiller Inspector")
    print("============================================================")
    print("Commands:")
    print("  - Type any medicine name (e.g. 'Metformin 500mg', 'Atorvastatin 10mg')")
    print("  - Type 'all' after medicine to show unfiltered stores as well")
    print("  - Type 'q' or 'exit' to quit\n")

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

        filter_known = True
        if " all" in query.lower():
            query = query.lower().replace(" all", "").strip()
            filter_known = False

        print(f"\nSearching & Distilling for: '{query}' (Filter known pharma platforms: {filter_known})...")
        raw_result = search_prices(query, verbose=False)
        
        distilled = distill_shopping_results(raw_result, filter_known_platforms=filter_known)

        print("\n" + "=" * 70)
        print(f" DISTILLED PHARMA RESULTS ({len(distilled)} items extracted):")
        print("=" * 70)

        if not distilled:
            print("No items matched the criteria.")
        else:
            for idx, item in enumerate(distilled, 1):
                print(f"[{idx:02d}] Platform       : {item['platform']} ({item['platform_domain']})")
                print(f"     Platform Logo  : {item['platform_logo']}")
                print(f"     Medicine       : {item['medicine_name']}")
                print(f"     Price (INR)    : ₹{item['price_inr']:.2f} (Raw: '{item['raw_price_str']}')")
                print(f"     Delivery       : {item['availability']}")
                print(f"     Thumbnail URL  : {item['thumbnail']}")
                print(f"     Direct Link    : {item['direct_link']}")
                print(f"     Google Link    : {item['google_link']}")
                print("-" * 70)



if __name__ == "__main__":
    main()
