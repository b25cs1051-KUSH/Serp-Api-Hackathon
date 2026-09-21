`scripts/tune_threshold.py` does the following from top to bottom:

1. Documents its purpose: compare query pairs and help choose a similarity threshold.
2. Adds the project root to `sys.path`, so it can run from any directory.
3. Configures UTF-8 output.
4. Imports NumPy and Sentence Transformers.
5. Loads the `all-MiniLM-L6-v2` embedding model immediately.
6. Defines `sim(a, b)`, which:
   - Embeds both text strings.
   - Normalizes the embeddings.
   - Calculates cosine similarity using a dot product.
7. Defines example query pairs labelled `SHOULD HIT` or `SHOULD MISS`.
8. Sets `THRESHOLD = 0.80`.
9. Prints a table showing each pair’s similarity score and whether it would be considered a hit or miss.
10. Marks each result as correct or incorrect compared with the expected label.
11. Prints the active threshold and a short explanation of the tradeoff:
    - Higher threshold: fewer false hits.
    - Lower threshold: more aggressive caching.

The threshold is **not automatically synchronized**.

`tune_threshold.py` has its own separate value:

```python
THRESHOLD = 0.80
```

`cache.py` has a separate constructor default:

```python
similarity_threshold: float = 0.80
```

They currently match because both were manually set to `0.80`. Changing one will not change the other. Also, passing a custom value when creating `SerpApiCache` overrides the value in `cache.py`. The tuning script only reports results; it does not update the cache configuration.