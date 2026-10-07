import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List

from .config import PROCESSED_CSV_PATH, COLUMN_INVOICE, COLUMN_PRODUCT
from .association_rules import AssociationRuleMiner
from .analysis import EDAAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class ModelEvaluator:
    def __init__(self, data_path: str = str(PROCESSED_CSV_PATH)):
        self.miner = AssociationRuleMiner()
        self.analyzer = EDAAnalyzer()
        self.df = self.miner.load_cleaned_data()
        self._cached_holdout = None
        self._cached_quality = None

    def evaluate_rules_quality(self) -> Dict[str, Any]:
        """Calculates standard association rule quality metrics."""
        if self._cached_quality is not None:
            return self._cached_quality
        rules = self.miner.mine_rules()
        summary = self.miner.get_rules_summary()
        
        all_catalog_products = set(self.df[COLUMN_PRODUCT].unique())
        
        # Calculate catalog coverage
        rule_products = set()
        for _, row in rules.iterrows():
            rule_products.update(row["antecedents"])
            rule_products.update(row["consequents"])
            
        coverage = len(rule_products) / len(all_catalog_products) if all_catalog_products else 0.0

        self._cached_quality = {
            "frequent_itemsets_count": summary["frequent_itemsets_count"],
            "association_rules_count": summary["association_rules_count"],
            "avg_support": summary["avg_support"],
            "avg_confidence": summary["avg_confidence"],
            "avg_lift": summary["avg_lift"],
            "max_lift": summary["max_lift"],
            "min_lift": summary["min_lift"],
            "catalog_coverage_pct": round(coverage * 100, 2),
            "unique_products_in_rules": len(rule_products),
            "total_catalog_products": len(all_catalog_products)
        }
        return self._cached_quality

    def evaluate_train_test_split(self, train_ratio: float = 0.8) -> Dict[str, Any]:
        """
        Splits transaction dataset into Train (80%) and Test (20%).
        - Mines association rules on Train transactions.
        - For each Test basket (with size >= 2):
          - Uses first item as input query
          - Evaluates if recommended products appear in the remaining items of the test basket (Hit Rate & Precision@K).
        """
        if self._cached_holdout is not None:
            return self._cached_holdout
        logging.info(f"Performing Train/Test split evaluation ({int(train_ratio*100)}% train / {int((1-train_ratio)*100)}% test)...")
        
        invoices = self.df[COLUMN_INVOICE].unique()
        np.random.seed(42)
        np.random.shuffle(invoices)
        
        split_idx = int(len(invoices) * train_ratio)
        train_invoices = set(invoices[:split_idx])
        test_invoices = set(invoices[split_idx:])

        train_df = self.df[self.df[COLUMN_INVOICE].isin(train_invoices)]
        test_df = self.df[self.df[COLUMN_INVOICE].isin(test_invoices)]

        # Build train basket matrix
        train_basket = (train_df.groupby([COLUMN_INVOICE, COLUMN_PRODUCT])[COLUMN_PRODUCT]
                        .count().unstack().reset_index().fillna(0)
                        .set_index(COLUMN_INVOICE))
        train_matrix = (train_basket > 0)

        # Mine train rules
        from mlxtend.frequent_patterns import fpgrowth, association_rules
        freq_itemsets = fpgrowth(train_matrix, min_support=0.01, use_colnames=True, max_len=3)
        if freq_itemsets.empty:
            return {"error": "No itemsets found on train split"}

        train_rules = association_rules(freq_itemsets, metric="confidence", min_threshold=0.20)
        train_rules = train_rules[train_rules["lift"] >= 1.2]

        # Evaluate on Test set
        test_baskets = test_df.groupby(COLUMN_INVOICE)[COLUMN_PRODUCT].apply(set).tolist()
        
        hits = 0
        total_evaluations = 0
        precision_list = []

        for basket in test_baskets:
            if len(basket) < 2:
                continue
            
            basket_items = list(basket)
            input_item = basket_items[0]
            actual_ground_truth = set(basket_items[1:])
            
            # Find matching rules in train set
            matching = train_rules[train_rules["antecedents"].apply(lambda x: input_item in x)]
            if matching.empty:
                continue
                
            matching = matching.sort_values(by="confidence", ascending=False)
            predicted_consequents = set()
            for _, r in matching.head(5).iterrows():
                predicted_consequents.update(r["consequents"])
            
            predicted_consequents.discard(input_item)
            if not predicted_consequents:
                continue

            total_evaluations += 1
            intersection = predicted_consequents.intersection(actual_ground_truth)
            
            if len(intersection) > 0:
                hits += 1
                
            precision = len(intersection) / len(predicted_consequents)
            precision_list.append(precision)

        hit_rate = round(hits / total_evaluations, 4) if total_evaluations > 0 else 0.0
        avg_precision = round(float(np.mean(precision_list)), 4) if precision_list else 0.0

        self._cached_holdout = {
            "test_evaluations_count": total_evaluations,
            "hits_count": hits,
            "hit_rate_top5": hit_rate,
            "mean_precision_top5": avg_precision,
            "train_invoices": len(train_invoices),
            "test_invoices": len(test_invoices)
        }
        return self._cached_holdout

if __name__ == "__main__":
    evaluator = ModelEvaluator()
    print("Evaluating Rules Quality...")
    quality = evaluator.evaluate_rules_quality()
    print(quality)
    print("\nEvaluating Train/Test Split...")
    holdout = evaluator.evaluate_train_test_split()
    print(holdout)
