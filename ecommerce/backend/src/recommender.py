import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any, Union, Optional

from .config import PROCESSED_CSV_PATH
from .association_rules import AssociationRuleMiner
from .analysis import EDAAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class RecommendationEngine:
    def __init__(self, miner: Optional[AssociationRuleMiner] = None):
        self.miner = miner or AssociationRuleMiner()
        self.rules = self.miner.mine_rules()
        self.analyzer = EDAAnalyzer()
        self._top_fallback_products = None

    @property
    def fallback_products(self) -> List[Dict[str, Any]]:
        """Returns top popular products to serve as graceful fallbacks when no rules match."""
        if self._top_fallback_products is None:
            top_freq = self.analyzer.get_top_products_by_frequency(top_n=10)
            self._top_fallback_products = [
                {
                    "product": item["product"],
                    "confidence": 0.25,
                    "lift": 1.0,
                    "support": round(item["count"] / 18266.0, 4),
                    "score": 0.30,
                    "is_fallback": True,
                    "rule_description": "Popular Storefront Product"
                }
                for item in top_freq
            ]
        return self._top_fallback_products

    def get_recommendations(self, product: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """Convenience single-product recommendation function."""
        return self.get_cart_recommendations([product], top_n=top_n)

    def get_cart_recommendations(
        self,
        cart_products: List[str],
        top_n: int = 5,
        min_confidence: float = 0.10,
        min_lift: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Generates product recommendations for a list of items in the user's cart.
        - Matches cart items against antecedent itemsets in mined association rules.
        - Excludes items already present in the cart.
        - Combines and deduplicates candidate consequents.
        - Ranks recommendations by composite score.
        - Falls back gracefully to top popular items if no rules are triggered.
        """
        if not cart_products or self.rules.empty:
            return self._get_filtered_fallbacks(cart_products, top_n)

        # Normalize cart product names (uppercase, stripped)
        cart_set = set(p.strip().upper() for p in cart_products if isinstance(p, str) and p.strip())

        if not cart_set:
            return self._get_filtered_fallbacks(cart_products, top_n)

        recommendations_dict: Dict[str, Dict[str, Any]] = {}

        # Iterate over mined association rules
        for _, row in self.rules.iterrows():
            antecedents = set(row["antecedents"])
            consequents = set(row["consequents"])

            # Check if all or part of antecedents match items in user's cart
            # Complete match or partial match
            match_overlap = antecedents.intersection(cart_set)

            if match_overlap:
                # Calculate match strength (ratio of matched antecedents)
                match_ratio = len(match_overlap) / len(antecedents)

                for target_product in consequents:
                    # Never recommend a product already in the user's cart
                    if target_product in cart_set:
                        continue

                    # Filter by minimum bounds
                    if row["confidence"] < min_confidence or row["lift"] < min_lift:
                        continue

                    # Weighted composite score based on antecedent match ratio
                    adj_score = round(float(row["score"]) * (0.7 + 0.3 * match_ratio), 4)

                    rec_entry = {
                        "product": target_product,
                        "confidence": round(float(row["confidence"]), 4),
                        "lift": round(float(row["lift"]), 2),
                        "support": round(float(row["support"]), 4),
                        "score": adj_score,
                        "is_fallback": False,
                        "matched_antecedents": list(match_overlap),
                        "rule_description": f"Frequently bought with {', '.join(match_overlap)}"
                    }

                    # If candidate already encountered, keep the one with higher composite score
                    if target_product not in recommendations_dict or rec_entry["score"] > recommendations_dict[target_product]["score"]:
                        recommendations_dict[target_product] = rec_entry

        sorted_recs = sorted(recommendations_dict.values(), key=lambda x: x["score"], reverse=True)

        # If matching rules produced fewer than top_n recommendations, supplement with popular items
        if len(sorted_recs) < top_n:
            existing_products = set(r["product"] for r in sorted_recs).union(cart_set)
            for fb in self.fallback_products:
                if fb["product"] not in existing_products:
                    sorted_recs.append(fb)
                    existing_products.add(fb["product"])
                if len(sorted_recs) >= top_n:
                    break

        return sorted_recs[:top_n]

    def _get_filtered_fallbacks(self, cart_products: List[str], top_n: int) -> List[Dict[str, Any]]:
        cart_set = set(p.strip().upper() for p in cart_products if isinstance(p, str))
        results = [fb for fb in self.fallback_products if fb["product"] not in cart_set]
        return results[:top_n]


if __name__ == "__main__":
    recommender = RecommendationEngine()

    # Test Single Product Recommendation
    test_prod = "WHITE HANGING HEART T-LIGHT HOLDER"
    print(f"\n--- Recommendations for '{test_prod}' ---")
    single_recs = recommender.get_recommendations(test_prod, top_n=5)
    for r in single_recs:
        print(r)

    # Test Multi-Product Cart Recommendation
    test_cart = ["GREEN REGENCY TEACUP AND SAUCER", "ROSES REGENCY TEACUP AND SAUCER"]
    print(f"\n--- Recommendations for Cart {test_cart} ---")
    cart_recs = recommender.get_cart_recommendations(test_cart, top_n=5)
    for r in cart_recs:
        print(r)

    # Test Unknown Product Recommendation
    unknown_prod = "SUPER DOOPER UNKNOWN GADGET 9999"
    print(f"\n--- Recommendations for Unknown Product '{unknown_prod}' ---")
    unknown_recs = recommender.get_recommendations(unknown_prod, top_n=5)
    for r in unknown_recs:
        print(r)
