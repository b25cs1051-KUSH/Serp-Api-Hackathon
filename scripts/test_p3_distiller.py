import sys
import json
from pharmawatch.search import search_prices, warm_up
from pharmawatch.distiller import distill_shopping_results
from pharmawatch.comparator import rank_by_landed_price
from pharmawatch.delivery_cost import lookup_zone, normalize_pincode

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
    print("Tip: Run 'docker compose up -d' to enable Redis caching.\n")
    print(f"Warm-up (Redis + embedding model): {warm_up(verbose=False):.0f} ms\n")

    while True:
        try:
            pincode = normalize_pincode(input("Delivery PIN code [default: 110001]: ").strip() or "110001")
            break
        except ValueError as e:
            print(e)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            return
    zone, assumed = lookup_zone(pincode)
    print(f"PIN {pincode} → zone: {zone}{' (prefix not listed, default zone)' if assumed else ''}")

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
        
        distilled = rank_by_landed_price(
            distill_shopping_results(raw_result, filter_known_platforms=filter_known), pincode
        )

        # Exact 'Visit Site' URLs (enrich_direct_merchant_links) cost 1 SerpApi call per
        # listing — they will be resolved only when the user clicks a link in the UI.

        print("\n" + "=" * 70)
        print(f" DISTILLED PHARMA RESULTS ({len(distilled)} items extracted):")
        print("=" * 70)

        if not distilled:
            print("No items matched the criteria.")
        else:
            for idx, item in enumerate(distilled, 1):
                landed = item["total_landed_cost"]
                print(f"[{idx:02d}] Platform          : {item['platform']} ({item['platform_domain']})"
                      f"{'  🏆 CHEAPEST' if item['is_cheapest'] else ''}")
                print(f"     Medicine          : {item['medicine_name']}")
                print(f"     Price (INR)       : ₹{item['price_inr']:.2f} (Raw: '{item['raw_price_str']}')")
                print(f"     Delivery to {pincode}: {item['delivery_label']}"
                      f"{' [' + item['estimated_days'] + ']' if item['estimated_days'] else ''}")
                print(f"     FINAL PRICE       : {f'₹{landed:.2f}' if landed is not None else 'not available'}")
                print(f"     Listing says      : {item['availability']}")
                print(f"     Thumbnail URL     : {item['thumbnail']}")
                print(f"     Direct Visit Site : {'resolved on click (page_token ready)' if item['page_token'] else 'n/a (no page_token)'}")
                print(f"     Google Shopping   : {item['google_link']}")
                print(f"     Store Search      : {item['search_link']}")
                print("-" * 70)


if __name__ == "__main__":
    main()

