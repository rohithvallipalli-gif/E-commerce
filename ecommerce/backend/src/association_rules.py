import pandas as pd
import numpy as np
import pickle
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from .config import (
    PROCESSED_CSV_PATH, RULES_CACHE_PATH,
    COLUMN_INVOICE, COLUMN_PRODUCT, COLUMN_QUANTITY,
    DEFAULT_MIN_SUPPORT, DEFAULT_MIN_CONFIDENCE, DEFAULT_MIN_LIFT
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class AssociationRuleMiner:
    def __init__(self, data_path: Path = PROCESSED_CSV_PATH):
        self.data_path = data_path
        self.df = None
        self.basket_matrix = None
        self.frequent_itemsets = None
        self.all_rules = None  # Comprehensive rules base
        self.rules = None      # Currently filtered rules

    def load_cleaned_data(self) -> pd.DataFrame:
        if self.df is None:
            if not self.data_path.exists():
                from .preprocessing import DataPreprocessor
                preprocessor = DataPreprocessor()
                self.df, _ = preprocessor.clean_data()
                preprocessor.save_cleaned_data()
            else:
                self.df = pd.read_csv(self.data_path, low_memory=False)
        return self.df

    def create_basket_matrix(self) -> pd.DataFrame:
        """
        Creates a memory-efficient boolean one-hot encoded matrix.
        Rows: InvoiceNo (Transactions)
        Columns: Description (Products)
        Values: True / False (Presence of product in transaction)
        """
        if self.basket_matrix is not None:
            return self.basket_matrix

        df = self.load_cleaned_data()
        logging.info("Building basket transaction matrix...")
        
        # Group by InvoiceNo and Description, aggregate quantity
        basket = (df.groupby([COLUMN_INVOICE, COLUMN_PRODUCT])[COLUMN_QUANTITY]
                  .sum().unstack().reset_index().fillna(0)
                  .set_index(COLUMN_INVOICE))
        
        # Encode presence as boolean for memory optimization and mlxtend apriori/fpgrowth speed
        self.basket_matrix = (basket > 0)
        
        # Drop baskets with 0 or 1 item, since co-purchase rules require at least 2 items
        basket_item_counts = self.basket_matrix.sum(axis=1)
        self.basket_matrix = self.basket_matrix[basket_item_counts >= 2]
        
        logging.info(f"Basket matrix created. Shape: {self.basket_matrix.shape} (Transactions x Unique Products)")
        return self.basket_matrix

    def _mine_full_rules(
        self,
        min_support: float = 0.005,
        min_confidence: float = 0.05,
        min_lift: float = 1.0
    ) -> pd.DataFrame:
        """
        Mines comprehensive rule set once at lowest sensible thresholds using FPGrowth.
        Saves rules to cache.
        """
        from mlxtend.frequent_patterns import fpgrowth, apriori, association_rules

        if self.basket_matrix is None:
            self.create_basket_matrix()

        logging.info(f"Mining comprehensive itemsets using FPGrowth (min_support={min_support}, max_len=3)...")
        try:
            self.frequent_itemsets = fpgrowth(
                self.basket_matrix,
                min_support=min_support,
                use_colnames=True,
                max_len=3
            )
        except Exception as e:
            logging.warning(f"FPGrowth failed ({e}), falling back to Apriori with low_memory=True...")
            self.frequent_itemsets = apriori(
                self.basket_matrix,
                min_support=min_support,
                use_colnames=True,
                max_len=3,
                low_memory=True
            )

        logging.info(f"Generated {len(self.frequent_itemsets)} frequent itemsets.")

        if self.frequent_itemsets.empty:
            logging.warning("No frequent itemsets found.")
            self.all_rules = pd.DataFrame()
            return self.all_rules

        logging.info(f"Generating association rules (min_confidence={min_confidence}, min_lift={min_lift})...")
        rules = association_rules(
            self.frequent_itemsets,
            metric="confidence",
            min_threshold=min_confidence
        )

        if not rules.empty:
            rules = rules[rules["lift"] >= min_lift].copy()

            # Replace any inf or nan in metrics
            rules["lift"] = rules["lift"].replace([np.inf, -np.inf], np.nan).fillna(1.0)
            rules["confidence"] = rules["confidence"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            rules["support"] = rules["support"].replace([np.inf, -np.inf], np.nan).fillna(0.0)

            # Compute Composite Recommendation Score
            max_lift = rules["lift"].max()
            min_lift_val = rules["lift"].min()
            denom = (max_lift - min_lift_val) if (max_lift - min_lift_val) > 0 else 1.0
            norm_lift = (rules["lift"] - min_lift_val) / denom

            rules["score"] = (
                (0.40 * rules["confidence"]) +
                (0.40 * norm_lift) +
                (0.20 * rules["support"])
            ).round(4)

            rules = rules.sort_values(by="score", ascending=False).reset_index(drop=True)

        self.all_rules = rules
        logging.info(f"Mined {len(self.all_rules)} total association rules. Caching to {RULES_CACHE_PATH}...")

        try:
            RULES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(RULES_CACHE_PATH, "wb") as f:
                pickle.dump({
                    "rules": self.all_rules,
                    "frequent_itemsets": self.frequent_itemsets,
                    "min_support": min_support,
                    "min_confidence": min_confidence,
                    "min_lift": min_lift
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
            logging.info(f"Successfully cached rules to {RULES_CACHE_PATH}")
        except Exception as e:
            logging.warning(f"Could not cache rules to disk: {e}")

        return self.all_rules

    def load_cache(self, force_recalculate: bool = False) -> pd.DataFrame:
        """Loads cached rules if valid and covers low min_support, else falls back to re-mining."""
        if not force_recalculate and self.all_rules is not None and not self.all_rules.empty:
            return self.all_rules

        if not force_recalculate and RULES_CACHE_PATH.exists():
            try:
                logging.info(f"Loading cached association rules from {RULES_CACHE_PATH}...")
                with open(RULES_CACHE_PATH, "rb") as f:
                    cache_data = pickle.load(f)
                
                cached_support = cache_data.get("min_support", 0.01)
                # Verify that cache has rules and covers min_support <= 0.005
                if "rules" in cache_data and isinstance(cache_data["rules"], pd.DataFrame) and cached_support <= 0.005:
                    self.all_rules = cache_data["rules"]
                    self.frequent_itemsets = cache_data.get("frequent_itemsets")
                    logging.info(f"Loaded {len(self.all_rules)} comprehensive rules from cache.")
                    return self.all_rules
                else:
                    logging.info(f"Cache exists but min_support is {cached_support} (> 0.005). Re-mining at 0.005...")
            except Exception as e:
                logging.warning(f"Failed to load rules cache ({e}). Re-mining rules once...")

        return self._mine_full_rules(min_support=0.005, min_confidence=0.05, min_lift=1.0)

    def mine_rules(
        self,
        min_support: float = DEFAULT_MIN_SUPPORT,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        min_lift: float = DEFAULT_MIN_LIFT,
        force_recalculate: bool = False
    ) -> pd.DataFrame:
        """
        Returns association rules filtered by requested min_confidence and min_lift in memory.
        Never re-runs Apriori/FPGrowth inside a request.
        """
        all_rules = self.load_cache(force_recalculate=force_recalculate)
        if all_rules is None or all_rules.empty:
            self.rules = pd.DataFrame()
            return self.rules

        # Filter in memory
        mask = (all_rules["confidence"] >= min_confidence) & (all_rules["lift"] >= min_lift)
        if "support" in all_rules.columns:
            mask = mask & (all_rules["support"] >= min_support)

        filtered = all_rules[mask].copy()
        if not filtered.empty:
            filtered = filtered.sort_values(by="score", ascending=False).reset_index(drop=True)

        self.rules = filtered
        return self.rules

    def get_rules_summary(self, rules_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """Calculates evaluation metrics over association rules, serialized safely."""
        target_rules = rules_df if rules_df is not None else (self.rules if self.rules is not None else self.mine_rules())

        def _safe_float(val, default=0.0, digits=4):
            if val is None or pd.isna(val) or np.isinf(val):
                return default
            return round(float(val), digits)

        if target_rules is None or target_rules.empty:
            return {
                "frequent_itemsets_count": len(self.frequent_itemsets) if self.frequent_itemsets is not None else 0,
                "association_rules_count": 0,
                "avg_support": 0.0,
                "avg_confidence": 0.0,
                "avg_lift": 0.0,
                "max_lift": 0.0,
                "min_lift": 0.0,
                "top_10_rules": []
            }

        top_10 = []
        for _, row in target_rules.head(10).iterrows():
            top_10.append({
                "antecedents": list(row["antecedents"]) if hasattr(row["antecedents"], "__iter__") else [str(row["antecedents"])],
                "consequents": list(row["consequents"]) if hasattr(row["consequents"], "__iter__") else [str(row["consequents"])],
                "support": _safe_float(row["support"], 0.0, 4),
                "confidence": _safe_float(row["confidence"], 0.0, 4),
                "lift": _safe_float(row["lift"], 0.0, 2),
                "score": _safe_float(row["score"], 0.0, 4)
            })

        return {
            "frequent_itemsets_count": len(self.frequent_itemsets) if self.frequent_itemsets is not None else 0,
            "association_rules_count": int(len(target_rules)),
            "avg_support": _safe_float(target_rules["support"].mean(), 0.0, 4),
            "avg_confidence": _safe_float(target_rules["confidence"].mean(), 0.0, 4),
            "avg_lift": _safe_float(target_rules["lift"].mean(), 0.0, 4),
            "max_lift": _safe_float(target_rules["lift"].max(), 0.0, 4),
            "min_lift": _safe_float(target_rules["lift"].min(), 0.0, 4),
            "top_10_rules": top_10
        }

if __name__ == "__main__":
    miner = AssociationRuleMiner()
    rules = miner.mine_rules(force_recalculate=True)
    summary = miner.get_rules_summary()
    print("Mined Rules Summary:")
    print(summary)
