import json
import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any

from .config import PROCESSED_CSV_PATH, DATA_DIR, normalize_product_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CATALOG_JSON_PATH = DATA_DIR / "catalog.json"

CATEGORY_MAPPINGS = [
    ("Kitchenware", "☕", ["TEACUP", "SAUCER", "MUG", "CAKE", "BAKING", "JAR", "BOWL", "PLATE", "CUTLERY", "TIN", "PANTRY", "KITCHEN", "COFFEE", "TEA", "SPOON"]),
    ("Home Decor", "🏠", ["HEART", "FRAME", "CLOCK", "SIGN", "MIRROR", "DOORMAT", "CUSHION", "PLAQUE", "HANGING", "WICKER", "CHALKBOARD"]),
    ("Storage & Bags", "👜", ["BAG", "STORAGE", "BOX", "BASKET", "CASE", "DRAWER", "CONTAINER"]),
    ("Gift & Party", "🎉", ["BUNTING", "PARTY", "GIFT", "BALLOON", "WRAPPING", "RIBBON", "CONFETTI", "TAGS"]),
    ("Garden", "🌿", ["GARDEN", "PLANT", "FLOWER", "WATERING", "POT", "BIRD", "HERB"]),
    ("Lighting", "💡", ["LIGHT", "LANTERN", "CANDLE", "LAMP", "T-LIGHT"]),
    ("Stationery", "✏️", ["PEN", "PENCIL", "NOTEBOOK", "RULER", "ERASER", "STATIONERY", "TAPE", "STICKER"]),
    ("Seasonal/Christmas", "🎄", ["CHRISTMAS", "XMAS", "TREE", "NOEL", "ADVENT", "SNOWFLAKE", "SANTA", "HOLLY"])
]

def map_category(name: str):
    name_upper = name.upper()
    for cat, emoji, kws in CATEGORY_MAPPINGS:
        if any(k in name_upper for k in kws):
            return cat, emoji
    return "Home Decor", "🏠"

def build_curated_catalog() -> List[Dict[str, Any]]:
    if not PROCESSED_CSV_PATH.exists():
        raise FileNotFoundError(f"Cleaned CSV not found at {PROCESSED_CSV_PATH}")

    logging.info(f"Loading transaction dataset from {PROCESSED_CSV_PATH}...")
    df = pd.read_csv(PROCESSED_CSV_PATH, low_memory=False)
    
    # Normalize product descriptions
    df["NormDesc"] = df["Description"].apply(normalize_product_name)

    # Exclude system/noise codes and anomalous strings
    excluded = ["POSTAGE", "MANUAL", "BANK CHARGES", "AMAZON FEE", "SAMPLES", "ADJUST", "CRUK COMMISSION", "DOTCOM POSTAGE"]
    bad_mask = df["NormDesc"].apply(lambda s: any(e in s for e in excluded) or len(s) < 5 or len(s) > 42 or "?" in s or "*" in s)
    clean_df = df[~bad_mask]

    # Calculate item frequencies, median prices, and primary stock code
    grouped = clean_df.groupby("NormDesc").agg(
        frequency=("InvoiceNo", "count"),
        stock_code=("StockCode", lambda x: str(x.mode()[0]) if not x.empty else "N/A"),
        median_price=("UnitPrice", "median")
    ).reset_index()

    # Sort by frequency descending
    grouped = grouped.sort_values(by="frequency", ascending=False)

    # Assign category and emoji
    cats = []
    emojis = []
    for desc in grouped["NormDesc"]:
        c, e = map_category(desc)
        cats.append(c)
        emojis.append(e)
    grouped["Category"] = cats
    grouped["Emoji"] = emojis

    catalog_products = []
    target_per_category = 8

    for cat, emoji, _ in CATEGORY_MAPPINGS:
        cat_items = grouped[grouped["Category"] == cat].head(target_per_category)
        for _, row in cat_items.iterrows():
            price = round(float(row["median_price"]), 2)
            if price < 0.99:
                price = 2.99
            
            p_name = row["NormDesc"]
            short_desc = f"{cat} Collection - {p_name.title()}. Popular marketplace essential with verified co-purchase affinity."
            
            catalog_products.append({
                "stock_code": str(row["stock_code"]),
                "product": p_name,
                "category": cat,
                "emoji": emoji,
                "price": price,
                "description": short_desc
            })

    logging.info(f"Generated curated catalog with {len(catalog_products)} products across {len(CATEGORY_MAPPINGS)} categories.")

    # Save to catalog.json
    CATALOG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog_products, f, indent=2, ensure_ascii=False)
    logging.info(f"Saved catalog to {CATALOG_JSON_PATH}")

    return catalog_products

if __name__ == "__main__":
    catalog = build_curated_catalog()
    print(f"Built catalog with {len(catalog)} products.")
    df_cat = pd.DataFrame(catalog)
    print(df_cat["category"].value_counts())
