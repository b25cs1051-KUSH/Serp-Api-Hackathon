"""
build_medicine_index.py — builds pharmawatch/drug_db/medicines.sqlite.gz from the Indian Medicine Dataset.

Source: https://github.com/junioralive/Indian-Medicine-Dataset (MIT, © 2024 JuniorAlive), 253,973
medicines: name, MRP, manufacturer, pack size, up to two salts with strengths.

Every product gets a composition key: its salts with strengths, form and release type, e.g.
    gliclazide:80mg|tablet|          (Glizid 80, Diamicron 80 ...)
    gliclazide:80mg+metformin:500mg|tablet|   (Glizid-M, Reclimet: a different medicine)
    metformin:500mg|tablet|sr        (Glyciphage SR 500: not the same as plain 500)
Products with the same key are interchangeable brands. Prices are list prices (MRP); live prices
still come from SerpApi.

    python scripts/build_medicine_index.py                 # downloads the CSV (31.8 MB)
    python scripts/build_medicine_index.py path/to.csv
"""

import csv
import gzip
import io
import os
import sqlite3
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from pharmawatch.medicines import INDEX_PATH, brand_name, composition_key, name_tokens, pack_count  # noqa: E402

SOURCE_URL = "https://raw.githubusercontent.com/junioralive/Indian-Medicine-Dataset/main/DATA/indian_medicine_data.csv"

SCHEMA = """
CREATE TABLE compositions (
    id INTEGER PRIMARY KEY,
    comp_key TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,           -- 'Gliclazide 80mg tablet'
    salts TEXT NOT NULL,           -- 'Gliclazide 80mg'
    salt_words TEXT NOT NULL,      -- sorted words of the salt names: 'gliclazide'
    strengths TEXT NOT NULL,       -- '80'
    form TEXT NOT NULL,
    release TEXT NOT NULL,
    products INTEGER NOT NULL
);
CREATE TABLE manufacturers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE products (
    brand TEXT NOT NULL,           -- 'Glizid 80' (form words removed)
    brand_tokens TEXT NOT NULL,    -- sorted match tokens: '80 glizid'
    first_token TEXT NOT NULL,     -- 'glizid'
    comp_id INTEGER NOT NULL,
    mrp REAL,
    pack INTEGER,                  -- units per pack when countable (tablets, capsules)
    manufacturer_id INTEGER
);
"""
# Indexes are created when the file is unpacked (pharmawatch/medicines.py), keeping the committed file small.


def read_rows(path):
    if path:
        return list(csv.DictReader(open(path, encoding="utf-8")))
    print(f"Downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as resp:
        return list(csv.DictReader(io.StringIO(resp.read().decode("utf-8"))))


def main(path=None):
    rows = read_rows(path)
    kept = [r for r in rows if r["Is_discontinued"].strip().upper() != "TRUE"]
    print(f"{len(rows)} rows, {len(kept)} not discontinued")

    tmp = os.path.join(tempfile.gettempdir(), "medicines_build.sqlite")
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)

    comps, makers, products, skipped = {}, {}, [], 0
    for r in kept:
        comp = composition_key(r["short_composition1"], r["short_composition2"], r["pack_size_label"], r["name"])
        brand = brand_name(r["name"])
        tokens = name_tokens(brand)
        if comp is None or not tokens:
            skipped += 1
            continue
        key = comp[0]
        if key not in comps:
            comps[key] = [len(comps) + 1, *comp, 0]
        comps[key][-1] += 1
        maker = " ".join(r["manufacturer_name"].split())
        maker_id = makers.setdefault(maker, len(makers) + 1) if maker else None
        try:
            mrp = float(r["price(₹)"])
        except ValueError:
            mrp = None
        products.append((brand, " ".join(sorted(set(tokens))), tokens[0], comps[key][0], mrp,
                         pack_count(r["pack_size_label"]), maker_id))
    db.executemany("INSERT INTO compositions VALUES (?,?,?,?,?,?,?,?,?)", comps.values())
    db.executemany("INSERT INTO manufacturers VALUES (?,?)", [(i, n) for n, i in makers.items()])
    db.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?)", products)
    db.commit()
    db.execute("VACUUM")
    n_products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    db.close()

    with open(tmp, "rb") as src, gzip.open(INDEX_PATH, "wb", compresslevel=9) as dst:
        dst.write(src.read())
    os.remove(tmp)
    print(f"{n_products} products, {len(comps)} compositions, {len(makers)} manufacturers, {skipped} skipped")
    print(f"wrote {INDEX_PATH} ({os.path.getsize(INDEX_PATH) / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
