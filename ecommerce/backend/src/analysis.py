import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, Any, List

from .config import (
    PROCESSED_CSV_PATH, EDA_CHARTS_DIR,
    COLUMN_INVOICE, COLUMN_PRODUCT, COLUMN_QUANTITY, COLUMN_PRICE, COLUMN_CUSTOMER, COLUMN_COUNTRY
)

class EDAAnalyzer:
    def __init__(self, data_path: Path = PROCESSED_CSV_PATH):
        self.data_path = data_path
        self.df = None

    def load_data(self) -> pd.DataFrame:
        if self.df is None:
            if not self.data_path.exists():
                from .preprocessing import DataPreprocessor
                preprocessor = DataPreprocessor()
                self.df, _ = preprocessor.clean_data()
                preprocessor.save_cleaned_data()
            else:
                self.df = pd.read_csv(self.data_path, low_memory=False)
        return self.df

    def get_summary_statistics(self) -> Dict[str, Any]:
        df = self.load_data()
        
        # Calculate Basket sizes
        basket_sizes = df.groupby(COLUMN_INVOICE)[COLUMN_PRODUCT].count()
        
        # Calculate Total Revenue
        if COLUMN_PRICE in df and COLUMN_QUANTITY in df:
            df['TotalSpend'] = df[COLUMN_QUANTITY] * df[COLUMN_PRICE]
            total_revenue = float(df['TotalSpend'].sum())
        else:
            total_revenue = 0.0

        # Basket size histogram bucketed counts
        bins = [0, 1, 2, 5, 10, 20, 50, float("inf")]
        labels = ["1", "2", "3-5", "6-10", "11-20", "21-50", "50+"]
        binned = pd.cut(basket_sizes, bins=bins, labels=labels, right=True)
        counts = binned.value_counts()[labels].to_dict()
        basket_hist = [{"bucket": str(k), "count": int(v)} for k, v in counts.items()]

        return {
            "total_transactions": int(df[COLUMN_INVOICE].nunique()),
            "total_unique_products": int(df[COLUMN_PRODUCT].nunique()),
            "total_unique_customers": int(df[COLUMN_CUSTOMER].nunique()) if COLUMN_CUSTOMER in df else 0,
            "total_line_items": int(len(df)),
            "total_revenue": round(total_revenue, 2),
            "basket_size_stats": {
                "mean": round(float(basket_sizes.mean()), 2),
                "median": float(basket_sizes.median()),
                "min": int(basket_sizes.min()),
                "max": int(basket_sizes.max()),
                "q25": float(basket_sizes.quantile(0.25)),
                "q75": float(basket_sizes.quantile(0.75))
            },
            "basket_size_histogram": basket_hist
        }

    def get_basket_size_histogram(self) -> List[Dict[str, Any]]:
        df = self.load_data()
        basket_sizes = df.groupby(COLUMN_INVOICE)[COLUMN_PRODUCT].count()
        bins = [0, 1, 2, 5, 10, 20, 50, float("inf")]
        labels = ["1", "2", "3-5", "6-10", "11-20", "21-50", "50+"]
        binned = pd.cut(basket_sizes, bins=bins, labels=labels, right=True)
        counts = binned.value_counts()[labels].to_dict()
        return [{"bucket": str(k), "count": int(v)} for k, v in counts.items()]

    def get_top_products_by_frequency(self, top_n: int = 10) -> List[Dict[str, Any]]:
        df = self.load_data()
        freq = df[COLUMN_PRODUCT].value_counts().head(top_n)
        return [{"product": str(k), "count": int(v)} for k, v in freq.items()]

    def get_top_products_by_quantity(self, top_n: int = 10) -> List[Dict[str, Any]]:
        df = self.load_data()
        qty = df.groupby(COLUMN_PRODUCT)[COLUMN_QUANTITY].sum().sort_values(ascending=False).head(top_n)
        return [{"product": str(k), "total_quantity": int(v)} for k, v in qty.items()]

    def get_top_products_by_revenue(self, top_n: int = 10) -> List[Dict[str, Any]]:
        df = self.load_data()
        df['TotalSpend'] = df[COLUMN_QUANTITY] * df[COLUMN_PRICE]
        rev = df.groupby(COLUMN_PRODUCT)['TotalSpend'].sum().sort_values(ascending=False).head(top_n)
        return [{"product": str(k), "total_revenue": round(float(v), 2)} for k, v in rev.items()]

    def get_top_countries(self, top_n: int = 10) -> List[Dict[str, Any]]:
        df = self.load_data()
        if COLUMN_COUNTRY not in df:
            return []
        cnt = df[COLUMN_COUNTRY].value_counts().head(top_n)
        return [{"country": str(k), "transactions": int(v)} for k, v in cnt.items()]

    def generate_eda_plots(self) -> Dict[str, str]:
        """Generates clear, publication-quality EDA plots saved to EDA_CHARTS_DIR."""
        df = self.load_data()
        sns.set_theme(style="whitegrid", palette="muted")
        saved_plots = {}

        # Plot 1: Top 10 Most Frequent Products
        plt.figure(figsize=(10, 6))
        top_freq = df[COLUMN_PRODUCT].value_counts().head(10)
        ax = sns.barplot(x=top_freq.values, y=top_freq.index, hue=top_freq.index, legend=False, palette="viridis")
        plt.title("Top 10 Most Frequently Purchased Products", fontsize=14, fontweight="bold", pad=15)
        plt.xlabel("Number of Orders", fontsize=12)
        plt.ylabel("")
        plt.tight_layout()
        plot1_path = EDA_CHARTS_DIR / "top_frequent_products.png"
        plt.savefig(plot1_path, dpi=300)
        plt.close()
        saved_plots["top_frequent_products"] = str(plot1_path)

        # Plot 2: Basket Size Distribution
        plt.figure(figsize=(10, 6))
        basket_sizes = df.groupby(COLUMN_INVOICE)[COLUMN_PRODUCT].count()
        # Cap at 95th percentile for clean visualization
        cap = basket_sizes.quantile(0.95)
        sns.histplot(basket_sizes[basket_sizes <= cap], bins=30, kde=True, color="#4F46E5")
        plt.title("Distribution of Basket Sizes (Items per Transaction)", fontsize=14, fontweight="bold", pad=15)
        plt.xlabel("Items in Basket", fontsize=12)
        plt.ylabel("Transaction Count", fontsize=12)
        plt.tight_layout()
        plot2_path = EDA_CHARTS_DIR / "basket_size_distribution.png"
        plt.savefig(plot2_path, dpi=300)
        plt.close()
        saved_plots["basket_size_distribution"] = str(plot2_path)

        # Plot 3: Top 10 Products by Total Revenue
        plt.figure(figsize=(10, 6))
        df['TotalSpend'] = df[COLUMN_QUANTITY] * df[COLUMN_PRICE]
        top_rev = df.groupby(COLUMN_PRODUCT)['TotalSpend'].sum().sort_values(ascending=False).head(10)
        sns.barplot(x=top_rev.values, y=top_rev.index, hue=top_rev.index, legend=False, palette="magma")
        plt.title("Top 10 Products by Total Revenue", fontsize=14, fontweight="bold", pad=15)
        plt.xlabel("Revenue ($)", fontsize=12)
        plt.ylabel("")
        plt.tight_layout()
        plot3_path = EDA_CHARTS_DIR / "top_revenue_products.png"
        plt.savefig(plot3_path, dpi=300)
        plt.close()
        saved_plots["top_revenue_products"] = str(plot3_path)

        return saved_plots

if __name__ == "__main__":
    analyzer = EDAAnalyzer()
    stats = analyzer.get_summary_statistics()
    print("Summary Stats:", stats)
    plots = analyzer.generate_eda_plots()
    print("Generated Plots:", plots)
