import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Dict, Tuple, Any

from .config import (
    RAW_DATA_PATH, PROCESSED_DATA_PATH, PROCESSED_CSV_PATH,
    COLUMN_INVOICE, COLUMN_PRODUCT, COLUMN_QUANTITY, COLUMN_PRICE,
    COLUMN_CUSTOMER, MIN_PRODUCT_FREQUENCY
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class DataPreprocessor:
    def __init__(self, file_path: Path = RAW_DATA_PATH):
        self.file_path = file_path
        self.raw_df = None
        self.cleaned_df = None
        self.stats = {}

    def load_data(self) -> pd.DataFrame:
        """Load raw dataset with error handling and format detection."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"Raw data file not found at {self.file_path}")
        
        logging.info(f"Loading raw data from {self.file_path}...")
        try:
            self.raw_df = pd.read_csv(self.file_path, encoding='latin1', low_memory=False)
        except Exception as e:
            logging.warning(f"CSV read failed with latin1, trying utf-8: {e}")
            self.raw_df = pd.read_csv(self.file_path, encoding='utf-8', low_memory=False)
            
        logging.info(f"Dataset successfully loaded. Shape: {self.raw_df.shape}")
        return self.raw_df

    def clean_data(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Executes robust data cleaning pipeline:
        - Removes missing descriptions
        - Strips whitespace & uppercases product descriptions
        - Filters out cancelled orders (InvoiceNo starting with 'C')
        - Filters out negative/zero quantities and unit prices
        - Drops exact duplicate rows
        - Removes generic non-product descriptions (e.g., 'POSTAGE', 'MANUAL', 'BANK CHARGES')
        - Filters out very low frequency items to optimize basket matrix
        """
        if self.raw_df is None:
            self.load_data()

        df = self.raw_df.copy()
        
        raw_rows = len(df)
        raw_invoices = df[COLUMN_INVOICE].nunique() if COLUMN_INVOICE in df else 0
        raw_products = df[COLUMN_PRODUCT].nunique() if COLUMN_PRODUCT in df else 0
        raw_customers = df[COLUMN_CUSTOMER].nunique() if COLUMN_CUSTOMER in df else 0

        # Step 1: Remove missing descriptions
        df = df.dropna(subset=[COLUMN_PRODUCT])

        # Step 2: Clean text formatting
        df[COLUMN_PRODUCT] = df[COLUMN_PRODUCT].astype(str).str.strip().str.upper()
        df = df[df[COLUMN_PRODUCT] != ""]
        df = df[df[COLUMN_PRODUCT] != "NAN"]

        # Step 3: Remove non-item service codes/descriptions if present
        excluded_patterns = ["POSTAGE", "MANUAL", "BANK CHARGES", "AMAZON FEE", "SAMPLES", "ADJUST", "CRUK Commission"]
        df = df[~df[COLUMN_PRODUCT].isin(excluded_patterns)]

        # Step 4: Handle Cancellations (Invoice starting with 'C')
        if COLUMN_INVOICE in df:
            df[COLUMN_INVOICE] = df[COLUMN_INVOICE].astype(str).str.strip()
            df = df[~df[COLUMN_INVOICE].str.startswith('C')]

        # Step 5: Filter positive quantities and unit prices
        if COLUMN_QUANTITY in df:
            df = df[df[COLUMN_QUANTITY] > 0]
        if COLUMN_PRICE in df:
            df = df[df[COLUMN_PRICE] > 0]

        # Step 6: Drop duplicate records
        df = df.drop_duplicates()

        # Step 7: Filter products occurring fewer than MIN_PRODUCT_FREQUENCY times to reduce sparsity noise
        product_counts = df[COLUMN_PRODUCT].value_counts()
        frequent_products = product_counts[product_counts >= MIN_PRODUCT_FREQUENCY].index
        df = df[df[COLUMN_PRODUCT].isin(frequent_products)]

        self.cleaned_df = df

        # Statistics summary
        cleaned_rows = len(df)
        cleaned_invoices = df[COLUMN_INVOICE].nunique()
        cleaned_products = df[COLUMN_PRODUCT].nunique()
        cleaned_customers = df[COLUMN_CUSTOMER].nunique() if COLUMN_CUSTOMER in df else 0

        self.stats = {
            "before": {
                "total_rows": raw_rows,
                "total_invoices": raw_invoices,
                "total_products": raw_products,
                "total_customers": raw_customers
            },
            "after": {
                "total_rows": cleaned_rows,
                "total_invoices": cleaned_invoices,
                "total_products": cleaned_products,
                "total_customers": cleaned_customers
            },
            "removed_rows": raw_rows - cleaned_rows
        }

        logging.info(f"Data cleaned. Rows reduced from {raw_rows} to {cleaned_rows} (removed {raw_rows - cleaned_rows}).")
        return self.cleaned_df, self.stats

    def save_cleaned_data(self) -> Path:
        """Saves cleaned dataset to parquet and csv format."""
        if self.cleaned_df is None:
            self.clean_data()

        try:
            self.cleaned_df.to_parquet(PROCESSED_DATA_PATH, index=False)
            logging.info(f"Saved cleaned parquet to {PROCESSED_DATA_PATH}")
        except Exception as e:
            logging.warning(f"Could not save parquet ({e}), saving CSV...")
        
        self.cleaned_df.to_csv(PROCESSED_CSV_PATH, index=False)
        logging.info(f"Saved cleaned CSV to {PROCESSED_CSV_PATH}")
        return PROCESSED_CSV_PATH

    def get_transaction_basket_representation(self) -> pd.DataFrame:
        """Returns InvoiceNo -> list of products dictionary or grouped representation."""
        if self.cleaned_df is None:
            self.clean_data()
        return self.cleaned_df.groupby(COLUMN_INVOICE)[COLUMN_PRODUCT].apply(list).reset_index()


if __name__ == "__main__":
    preprocessor = DataPreprocessor()
    df, stats = preprocessor.clean_data()
    print("Preprocessing completed!")
    print(stats)
    preprocessor.save_cleaned_data()
