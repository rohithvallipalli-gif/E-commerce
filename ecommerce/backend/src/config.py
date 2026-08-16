import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_PATH = DATA_DIR / "raw" / "online_retail.csv"
PROCESSED_DATA_PATH = DATA_DIR / "processed" / "cleaned_online_retail.parquet"
PROCESSED_CSV_PATH = DATA_DIR / "processed" / "cleaned_online_retail.csv"
MODELS_DIR = BASE_DIR / "models"
RULES_CACHE_PATH = MODELS_DIR / "association_rules.pkl"
EDA_CHARTS_DIR = BASE_DIR / "static" / "charts"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True, parents=True)
(DATA_DIR / "raw").mkdir(exist_ok=True, parents=True)
(DATA_DIR / "processed").mkdir(exist_ok=True, parents=True)
MODELS_DIR.mkdir(exist_ok=True, parents=True)
EDA_CHARTS_DIR.mkdir(exist_ok=True, parents=True)

# Dataset Column Definitions (Auto-adaptation defaults for UCI Online Retail dataset)
COLUMN_INVOICE = "InvoiceNo"
COLUMN_STOCK_CODE = "StockCode"
COLUMN_PRODUCT = "Description"
COLUMN_QUANTITY = "Quantity"
COLUMN_DATE = "InvoiceDate"
COLUMN_PRICE = "UnitPrice"
COLUMN_CUSTOMER = "CustomerID"
COLUMN_COUNTRY = "Country"

# Default Market Basket Analysis Hyperparameters
DEFAULT_MIN_SUPPORT = 0.01
DEFAULT_MIN_CONFIDENCE = 0.20
DEFAULT_MIN_LIFT = 1.2
DEFAULT_METRIC = "lift"

# Minimum occurrences to keep a product (reduces matrix sparsity)
MIN_PRODUCT_FREQUENCY = 5
