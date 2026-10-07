import json
import logging
import random
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from .config import PROCESSED_CSV_PATH, DATA_DIR, MODELS_DIR, normalize_product_name
from .association_rules import AssociationRuleMiner
from .analysis import EDAAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CATALOG_JSON_PATH = DATA_DIR / "catalog.json"

class RecommendationEngine:
    def __init__(self, miner: Optional[AssociationRuleMiner] = None):
        self.miner = miner or AssociationRuleMiner()
        # Warm rules cache
        self.miner.load_cache()
        # Load catalog items set
        self.catalog_products = self._load_catalog_products()
        # Precompute item-to-item co-occurrence similarity matrix
        self.similarity_matrix: Dict[str, Dict[str, float]] = {}
        self._build_item_similarity_matrix()
        # Inverted index for rules by antecedent
        self._rules_by_antecedent: Dict[str, List[tuple]] = {}
        self._build_rules_index()
        # Cache top popular catalog items
        self.popular_catalog_items: List[Dict[str, Any]] = self._build_popular_catalog_items()

    def _build_rules_index(self):
        """Indexes rules by individual antecedent products for O(1) cart candidate retrieval."""
        self._rules_by_antecedent = {}
        rules = self.miner.mine_rules(min_confidence=0.05, min_lift=1.0)
        if rules is not None and not rules.empty:
            for _, row in rules.iterrows():
                ants = tuple(normalize_product_name(a) for a in row["antecedents"])
                conqs = tuple(normalize_product_name(c) for c in row["consequents"])
                conf = float(row["confidence"])
                lift = float(row["lift"])
                supp = float(row["support"])
                score = float(row["score"])
                rule_item = (ants, conqs, conf, lift, supp, score)
                for a in ants:
                    if a not in self._rules_by_antecedent:
                        self._rules_by_antecedent[a] = []
                    self._rules_by_antecedent[a].append(rule_item)

    def _load_catalog_products(self) -> Dict[str, Dict[str, Any]]:
        """Loads available catalog products mapping."""
        catalog_map = {}
        if CATALOG_JSON_PATH.exists():
            try:
                with open(CATALOG_JSON_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        p_norm = normalize_product_name(item["product"])
                        catalog_map[p_norm] = item
            except Exception as e:
                logging.warning(f"Failed to read catalog.json: {e}")
        return catalog_map

    def refresh_catalog(self):
        """Refreshes catalog products from catalog.json or database."""
        self.catalog_products = self._load_catalog_products()
        self._build_item_similarity_matrix(force=True)
        self._build_rules_index()
        self.popular_catalog_items = self._build_popular_catalog_items()

    def _build_item_similarity_matrix(self, force: bool = False):
        """
        Precomputes Item-to-Item Jaccard / Cosine co-occurrence similarity on the basket matrix.
        Optimized specifically for available catalog products and cached to disk.
        """
        sim_cache_path = MODELS_DIR / "item_similarity.pkl"
        if not force and sim_cache_path.exists():
            try:
                import pickle
                with open(sim_cache_path, "rb") as f:
                    self.similarity_matrix = pickle.load(f)
                logging.info(f"Loaded item similarity matrix from cache ({len(self.similarity_matrix)} items).")
                return
            except Exception as e:
                logging.warning(f"Could not load similarity cache: {e}. Recomputing...")

        logging.info("Precomputing item-to-item co-occurrence matrix for catalog products...")
        try:
            basket_matrix = self.miner.create_basket_matrix()
            
            # Filter basket matrix columns to items that are in the catalog and appear in the dataset
            valid_cols = [c for c in basket_matrix.columns if normalize_product_name(c) in self.catalog_products]
            if not valid_cols:
                valid_cols = list(basket_matrix.columns[:100])

            sub_matrix = basket_matrix[valid_cols].astype(bool)

            # Column dot product: Co-occurrence counts
            # (valid_cols x valid_cols)
            co_occur = sub_matrix.T.dot(sub_matrix).astype(float)
            col_sums = sub_matrix.sum(axis=0).values

            # Jaccard similarity: co_occur[i, j] / (sum_i + sum_j - co_occur[i, j])
            sim_dict = {}
            col_names = [normalize_product_name(c) for c in valid_cols]

            for i, name_i in enumerate(col_names):
                sim_dict[name_i] = {}
                sum_i = col_sums[i]
                if sum_i == 0:
                    continue
                for j, name_j in enumerate(col_names):
                    if i == j:
                        continue
                    co = co_occur.iloc[i, j]
                    if co > 0:
                        union_count = sum_i + col_sums[j] - co
                        jaccard = round(float(co / union_count), 4) if union_count > 0 else 0.0
                        if jaccard > 0:
                            sim_dict[name_i][name_j] = jaccard

            self.similarity_matrix = sim_dict
            try:
                import pickle
                with open(sim_cache_path, "wb") as f:
                    pickle.dump(sim_dict, f)
            except Exception as e:
                logging.warning(f"Could not save similarity matrix to cache: {e}")
            logging.info(f"Item similarity matrix computed and cached for {len(self.similarity_matrix)} catalog products.")
        except Exception as e:
            logging.warning(f"Could not build co-occurrence matrix: {e}")
            self.similarity_matrix = {}

    def _build_popular_catalog_items(self) -> List[Dict[str, Any]]:
        """Precomputes ranked list of catalog products by popularity."""
        if self.miner.df is None:
            self.miner.load_cleaned_data()
        df = self.miner.df

        if df is not None and not df.empty:
            raw_vc = df["Description"].value_counts().to_dict()
            vc = {normalize_product_name(k): v for k, v in raw_vc.items()}
        else:
            vc = {}

        popular = []
        for p_name, item in self.catalog_products.items():
            freq = int(vc.get(p_name, 10))
            popular.append({
                "product": p_name,
                "confidence": 0.20,
                "lift": 1.0,
                "support": round(freq / 18266.0, 4),
                "score": 0.25,
                "is_fallback": True,
                "rule_description": f"Trending in {item.get('category', 'Storefront')}",
                "matched_antecedents": []
            })

        popular.sort(key=lambda x: x["support"], reverse=True)
        return popular

    def get_recommendations(self, product: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """Convenience single-product recommendation function."""
        return self.get_cart_recommendations([product], top_n=top_n)

    def get_cart_recommendations(
        self,
        cart_products: List[str],
        top_n: int = 6,
        min_confidence: float = 0.05,
        min_lift: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Generates product recommendations for a list of items in the user's cart:
        - If cart is empty: returns [] (frontend will display 'Add products to see recommendations' / Trending)
        - Matches cart items against association rules (Tier 1) with multi-item aggregation and linkage boost.
        - If fewer than top_n: falls back to Item-to-Item co-occurrence similarity (Tier 2).
        - If still fewer than top_n: falls back to deterministic shuffled catalog popularity (Tier 3).
        - Strictly only recommends items in the active catalog.
        - Never includes items currently in the cart.
        """
        if not cart_products:
            return []

        # Normalize cart product names
        cart_set: Set[str] = set()
        for p in cart_products:
            if isinstance(p, str) and p.strip():
                norm = normalize_product_name(p)
                if norm:
                    cart_set.add(norm)

        if not cart_set:
            return []

        # Available catalog set (if catalog is populated, restrict to catalog, else all)
        catalog_set = set(self.catalog_products.keys()) if self.catalog_products else None

        # Candidate pool: product -> dict
        candidates: Dict[str, Dict[str, Any]] = {}

        # -------------------------------------------------------------
        # TIER 1: Association Rules Matching via Inverted Index
        # -------------------------------------------------------------
        seen_rules = set()
        matched_rules = []
        for item in cart_set:
            for rule in self._rules_by_antecedent.get(item, []):
                rule_id = (rule[0], rule[1])
                if rule_id not in seen_rules:
                    seen_rules.add(rule_id)
                    matched_rules.append(rule)

        for ants, conqs, conf, lift, supp, base_score in matched_rules:
            if conf < min_confidence or lift < min_lift:
                continue

            matched = set(ants).intersection(cart_set)
            match_ratio = len(matched) / len(ants)

            for target in conqs:
                if target in cart_set:
                    continue
                if catalog_set and target not in catalog_set:
                    continue

                adjusted_score = base_score * (0.7 + 0.3 * match_ratio)

                if target not in candidates:
                    candidates[target] = {
                        "product": target,
                        "confidence": round(conf, 4),
                        "lift": round(lift, 2),
                        "support": round(supp, 4),
                        "score": round(adjusted_score, 4),
                        "is_fallback": False,
                        "matched_antecedents": set(matched),
                        "rule_description": f"Frequently bought with {', '.join(sorted(matched))}"
                    }
                else:
                    existing = candidates[target]
                    existing["matched_antecedents"].update(matched)
                    existing["score"] = round(existing["score"] + (adjusted_score * 0.4) + 0.12, 4)
                    if conf > existing["confidence"]:
                        existing["confidence"] = round(conf, 4)
                    if lift > existing["lift"]:
                        existing["lift"] = round(lift, 2)
                        existing["rule_description"] = f"Frequently bought with {', '.join(sorted(existing['matched_antecedents']))}"

        # -------------------------------------------------------------
        # TIER 2: Item-to-Item Co-occurrence Similarity
        # -------------------------------------------------------------
        if len(candidates) < top_n and self.similarity_matrix:
            for cart_item in cart_set:
                item_sims = self.similarity_matrix.get(cart_item, {})
                # Sort neighbors by Jaccard similarity descending
                sorted_neighbors = sorted(item_sims.items(), key=lambda x: x[1], reverse=True)

                for neighbor, sim_score in sorted_neighbors:
                    if neighbor in cart_set:
                        continue
                    if catalog_set and neighbor not in catalog_set:
                        continue

                    # Co-occurrence score scaled between 0.35 and 0.70
                    tier2_score = round(0.35 + (sim_score * 0.70), 4)

                    if neighbor not in candidates:
                        candidates[neighbor] = {
                            "product": neighbor,
                            "confidence": round(max(0.15, sim_score), 4),
                            "lift": round(max(1.2, sim_score * 10), 2),
                            "support": 0.01,
                            "score": tier2_score,
                            "is_fallback": False,
                            "matched_antecedents": {cart_item},
                            "rule_description": f"High co-purchase affinity with {cart_item}"
                        }
                    else:
                        candidates[neighbor]["matched_antecedents"].add(cart_item)
                        candidates[neighbor]["score"] = round(candidates[neighbor]["score"] + 0.08, 4)

                    if len(candidates) >= top_n * 2:
                        break

        # Sort recommendations by score descending
        sorted_recs = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)

        # -------------------------------------------------------------
        # TIER 3: Popularity Fallback (Deterministically Shuffled per Cart)
        # -------------------------------------------------------------
        if len(sorted_recs) < top_n:
            existing_names = set(r["product"] for r in sorted_recs).union(cart_set)
            
            # Deterministic seed based on cart contents
            cart_hash = sum(hash(item) for item in sorted(cart_set)) % 100000
            rng = random.Random(cart_hash)

            available_popular = [fb for fb in self.popular_catalog_items if fb["product"] not in existing_names]
            
            # Shuffle top available popular candidates
            pool_slice = available_popular[:min(30, len(available_popular))]
            rng.shuffle(pool_slice)

            for fb in pool_slice:
                if fb["product"] not in existing_names:
                    fb_copy = dict(fb)
                    fb_copy["matched_antecedents"] = list(cart_set)[:1]
                    fb_copy["rule_description"] = f"Popular storefront item complement"
                    sorted_recs.append(fb_copy)
                    existing_names.add(fb["product"])
                if len(sorted_recs) >= top_n:
                    break

        # Clean output schema
        final_results = []
        for r in sorted_recs[:top_n]:
            item_out = dict(r)
            if isinstance(item_out.get("matched_antecedents"), set):
                item_out["matched_antecedents"] = sorted(list(item_out["matched_antecedents"]))
            elif not item_out.get("matched_antecedents"):
                item_out["matched_antecedents"] = []
            final_results.append(item_out)

        return final_results

if __name__ == "__main__":
    engine = RecommendationEngine()
    test_p1 = "GREEN REGENCY TEACUP AND SAUCER"
    recs1 = engine.get_cart_recommendations([test_p1], top_n=3)
    print(f"\nRecs for {test_p1}:")
    for r in recs1:
        print(r["product"], r["score"], r["rule_description"])

    test_p2 = "WHITE HANGING HEART T-LIGHT HOLDER"
    recs2 = engine.get_cart_recommendations([test_p2], top_n=3)
    print(f"\nRecs for {test_p2}:")
    for r in recs2:
        print(r["product"], r["score"], r["rule_description"])
