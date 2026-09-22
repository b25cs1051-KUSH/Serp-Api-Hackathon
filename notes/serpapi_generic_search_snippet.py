# 2. Search generic active salt formula
generic_params = get_india_shopping_params("Metformin 500mg Glimepiride 1mg strip")
generic_results = client.search(generic_params)

clean_generic_prices = parse_pharma_results(generic_results.get("shopping_results", []))
print("Generic Alternatives Found:", clean_generic_prices)