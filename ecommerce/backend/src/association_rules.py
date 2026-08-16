import pandas as pd
import numpy as np
import pickle
import logging
from pathlib import Path
from typing import Dict, Any, Tuple
from mlxtend.frequent_patterns import apriori, association_rules

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
        self.rules = None

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
        df = self.load_cleaned_data()
        logging.info("Building basket transaction matrix...")
        
        # Group by InvoiceNo and Description, aggregate quantity
        basket = (df.groupby([COLUMN_INVOICE, COLUMN_PRODUCT])[COLUMN_QUANTITY]
                  .sum().unstack().reset_index().fillna(0)
                  .set_index(COLUMN_INVOICE))
        
        # Encode presence as boolean for memory optimization and mlxtend apriori speed
        self.basket_matrix = (basket > 0)
        
        # Drop baskets with 0 or 1 item, since co-purchase rules require at least 2 items
        basket_item_counts = self.basket_matrix.sum(axis=1)
        self.basket_matrix = self.basket_matrix[basket_item_counts >= 2]
        
        logging.info(f"Basket matrix created. Shape: {self.basket_matrix.shape} (Transactions x Unique Products)")
        return self.basket_matrix

    def mine_rules(
        self,
        min_support: float = DEFAULT_MIN_SUPPORT,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        min_lift: float = DEFAULT_MIN_LIFT,
        force_recalculate: bool = False
    ) -> pd.DataFrame:
        """
        Executes Apriori algorithm to find frequent itemsets and generates association rules.
        Filters rules by min_support, min_confidence, min_lift.
        """
        if not force_recalculate and RULES_CACHE_PATH.exists():
            try:
                logging.info(f"Loading cached association rules from {RULES_CACHE_PATH}...")
                with open(RULES_CACHE_PATH, "rb") as f:
                    cache_data = pickle.load(f)
                    self.rules = cache_data["rules"]
                    self.frequent_itemsets = cache_data.get("frequent_itemsets")
                    logging.info(f"Loaded {len(self.rules)} rules from cache successfully.")
                    return self.rules
            except Exception as e:
                logging.warning(f"Failed to load rules from cache: {e}. Re-mining rules...")

        if self.basket_matrix is None:
            self.create_basket_matrix()

        from mlxtend.frequent_patterns import apriori, fpgrowth, association_rules

        logging.info(f"Running FPGrowth algorithm with min_support={min_support}...")
        try:
            self.frequent_itemsets = fpgrowth(
                self.basket_matrix,
                min_support=min_support,
                use_colnames=True,
                max_len=3
            )
        except Exception as e:
            logging.warning(f"FPGrowth failed ({e}), trying Apriori with low_memory=True...")
            try:
                self.frequent_itemsets = apriori(
                    self.basket_matrix,
                    min_support=min_support,
                    use_colnames=True,
                    max_len=3,
                    low_memory=True
                )
            except Exception as ex:
                logging.error(f"Apriori execution failed: {ex}")
                raise ex

        logging.info(f"Generated {len(self.frequent_itemsets)} frequent itemsets.")

        if self.frequent_itemsets.empty:
            logging.warning("No frequent itemsets found with given min_support. Lowering threshold...")
            self.rules = pd.DataFrame()
            return self.rules

        logging.info(f"Mining association rules with min_threshold(confidence)={min_confidence}...")
        all_rules = association_rules(
            self.frequent_itemsets,
            metric="confidence",
            min_threshold=min_confidence
        )

        # Filter by min_lift
        self.rules = all_rules[all_rules["lift"] >= min_lift].copy()

        # Compute Composite Recommendation Score
        # Composite Score = (0.40 * Confidence) + (0.40 * Normalized Lift) + (0.20 * Support)
        if not self.rules.empty:
            max_lift = self.rules["lift"].max()
            min_lift_val = self.rules["lift"].min()
            norm_lift = (self.rules["lift"] - min_lift_val) / (max_lift - min_lift_val + 1e-6)
            
            self.rules["score"] = (
                (0.40 * self.rules["confidence"]) +
                (0.40 * norm_lift) +
                (0.20 * self.rules["support"])
            ).round(4)
            
            self.rules = self.rules.sort_values(by="score", ascending=False).reset_index(drop=True)

        logging.info(f"Mined {len(self.rules)} association rules successfully.")

        # Cache rules and metadata
        try:
            with open(RULES_CACHE_PATH, "wb") as f:
                pickle.dump({
                    "rules": self.rules,
                    "frequent_itemsets": self.frequent_itemsets,
                    "min_support": min_support,
                    "min_confidence": min_confidence,
                    "min_lift": min_lift
                }, f)
            logging.info(f"Cached mined rules to {RULES_CACHE_PATH}")
        except Exception as e:
            logging.warning(f"Could not cache rules to disk: {e}")

        return self.rules

    def get_rules_summary(self) -> Dict[str, Any]:
        """Calculates evaluation metrics over mined association rules."""
        if self.rules is None:
            self.mine_rules()

        if self.rules.empty:
            return {
                "frequent_itemsets_count": 0,
                "association_rules_count": 0,
                "avg_support": 0.0,
                "avg_confidence": 0.0,
                "avg_lift": 0.0,
                "max_lift": 0.0,
                "min_lift": 0.0
            }

        return {
            "frequent_itemsets_count": len(self.frequent_itemsets) if self.frequent_itemsets is not None else 0,
            "association_rules_count": len(self.rules),
            "avg_support": round(float(self.rules["support"].mean()), 4),
            "avg_confidence": round(float(self.rules["confidence"].mean()), 4),
            "avg_lift": round(float(self.rules["lift"].mean()), 4),
            "max_lift": round(float(self.rules["lift"].max()), 4),
            "min_lift": round(float(self.rules["lift"].min()), 4),
            "top_10_rules": [
                {
                    "antecedents": list(row["antecedents"]),
                    "consequents": list(row["consequents"]),
                    "support": round(float(row["support"]), 4),
                    "confidence": round(float(row["confidence"]), 4),
                    "lift": round(float(row["lift"]), 4),
                    "score": round(float(row["score"]), 4)
                }
                for _, row in self.rules.head(10).iterrows()
            ]
        }

if __name__ == "__main__":
    miner = AssociationRuleMiner()
    rules = miner.mine_rules(force_recalculate=True)
    summary = miner.get_rules_summary()
    print("Mined Rules Summary:")
    print(summary)
