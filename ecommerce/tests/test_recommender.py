import sys
import json
from pathlib import Path

# Ensure repository root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.src.config import DATA_DIR, normalize_product_name
from backend.src.recommender import RecommendationEngine

CATALOG_PATH = DATA_DIR / "catalog.json"

def test_recommender_produces_diverse_and_valid_recommendations():
    engine = RecommendationEngine()

    # Load catalog products
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    assert len(catalog) >= 50, f"Catalog should have at least 50 products, got {len(catalog)}"

    # Select 8 diverse products from distinct categories
    tested_products = []
    seen_categories = set()
    for item in catalog:
        cat = item["category"]
        if cat not in seen_categories:
            seen_categories.add(cat)
            tested_products.append(item["product"])
        if len(tested_products) == 8:
            break

    assert len(tested_products) == 8, f"Expected 8 diverse products, got {len(tested_products)}"

    recommendation_sets = []

    for product in tested_products:
        norm_product = normalize_product_name(product)
        recs = engine.get_cart_recommendations([product], top_n=3)

        assert len(recs) == 3, f"Expected 3 recommendations for '{product}', got {len(recs)}"

        rec_products = [normalize_product_name(r["product"]) for r in recs]

        # 1. Assert no recommended product is in the cart
        assert norm_product not in rec_products, f"Cart item '{norm_product}' was recommended: {rec_products}"

        # 2. Assert recommendations only come from the catalog
        for r_name in rec_products:
            assert r_name in engine.catalog_products, f"Recommendation '{r_name}' is not in catalog"

        # 3. Collect top-3 tuple to verify uniqueness
        top3_tuple = tuple(rec_products)
        recommendation_sets.append(top3_tuple)

    # 4. Assert that at least 8 different catalog products produce DIFFERENT top-3 lists
    unique_top3_lists = set(recommendation_sets)
    assert len(unique_top3_lists) == 8, (
        f"Expected 8 distinct recommendation lists for 8 distinct products, but only {len(unique_top3_lists)} were distinct: {recommendation_sets}"
    )

def test_recommender_multi_item_blend():
    engine = RecommendationEngine()

    prod_a = "GREEN REGENCY TEACUP AND SAUCER"
    prod_b = "JUMBO BAG RED RETROSPOT"

    recs_a = engine.get_cart_recommendations([prod_a], top_n=3)
    recs_b = engine.get_cart_recommendations([prod_b], top_n=3)
    recs_ab = engine.get_cart_recommendations([prod_a, prod_b], top_n=5)

    names_a = [normalize_product_name(r["product"]) for r in recs_a]
    names_b = [normalize_product_name(r["product"]) for r in recs_b]
    names_ab = [normalize_product_name(r["product"]) for r in recs_ab]

    # Neither prod_a nor prod_b should be in recs_ab
    assert normalize_product_name(prod_a) not in names_ab
    assert normalize_product_name(prod_b) not in names_ab

    # Recs for A and B alone should be different
    assert names_a != names_b, "Product A and Product B must have different recommendations"

    # Multi-item cart should have non-empty recommendations
    assert len(names_ab) >= 3

def test_recommender_empty_cart():
    engine = RecommendationEngine()
    recs_empty = engine.get_cart_recommendations([], top_n=5)
    assert recs_empty == [], "Empty cart must return empty list"

if __name__ == "__main__":
    print("Running test_recommender_produces_diverse_and_valid_recommendations...")
    test_recommender_produces_diverse_and_valid_recommendations()
    print("Running test_recommender_multi_item_blend...")
    test_recommender_multi_item_blend()
    print("Running test_recommender_empty_cart...")
    test_recommender_empty_cart()
    print("ALL RECOMMENDER TESTS PASSED SUCCESSFULLY!")
