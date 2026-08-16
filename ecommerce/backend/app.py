import os
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.src.config import BASE_DIR, EDA_CHARTS_DIR, COLUMN_PRODUCT
from backend.src.preprocessing import DataPreprocessor
from backend.src.association_rules import AssociationRuleMiner
from backend.src.recommender import RecommendationEngine
from backend.src.analysis import EDAAnalyzer
from backend.src.evaluation import ModelEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Pre-warming Recommender models and EDA charts...")
    engine = get_recommender()
    an = get_analyzer()
    an.generate_eda_plots()
    logging.info("FastAPI Server startup complete!")
    yield

app = FastAPI(
    title="E-Commerce Market Basket Recommender API",
    description="REST API for real-time market basket recommendation, association rules exploration, and model analytics.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Setup for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount EDA charts static directory
if not EDA_CHARTS_DIR.exists():
    EDA_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/charts", StaticFiles(directory=str(EDA_CHARTS_DIR)), name="charts")

# Singletons for Recommender Engine and Analyzer
recommender_engine: Optional[RecommendationEngine] = None
analyzer: Optional[EDAAnalyzer] = None
evaluator: Optional[ModelEvaluator] = None

def get_recommender() -> RecommendationEngine:
    global recommender_engine
    if recommender_engine is None:
        logging.info("Initializing RecommendationEngine...")
        recommender_engine = RecommendationEngine()
    return recommender_engine

def get_analyzer() -> EDAAnalyzer:
    global analyzer
    if analyzer is None:
        analyzer = EDAAnalyzer()
    return analyzer

def get_evaluator() -> ModelEvaluator:
    global evaluator
    if evaluator is None:
        evaluator = ModelEvaluator()
    return evaluator


# Pydantic Schemas
class RecommendRequest(BaseModel):
    cart: List[str] = Field(..., description="List of product descriptions currently in the cart", json_schema_extra={"example": ["GREEN REGENCY TEACUP AND SAUCER"]})
    top_n: int = Field(default=6, ge=1, le=20, description="Number of recommendations to return")
    min_confidence: float = Field(default=0.10, ge=0.0, le=1.0)
    min_lift: float = Field(default=1.0, ge=0.0)

class RecommendationItem(BaseModel):
    product: str
    confidence: float
    lift: float
    support: float
    score: float
    is_fallback: bool
    rule_description: str
    matched_antecedents: Optional[List[str]] = None


@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "E-Commerce Recommender API",
        "version": "1.0.0"
    }


@app.get("/api/products")
def list_products(
    q: Optional[str] = Query(None, description="Search term for product description"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Retrieve catalog products with optional keyword search."""
    an = get_analyzer()
    df = an.load_data()
    
    unique_products = df[COLUMN_PRODUCT].drop_duplicates().tolist()
    
    if q and q.strip():
        search_term = q.strip().upper()
        unique_products = [p for p in unique_products if search_term in str(p)]
    
    total = len(unique_products)
    paged_products = unique_products[offset:offset+limit]
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": paged_products
    }


@app.post("/api/recommend", response_model=List[RecommendationItem])
def recommend_products(request: RecommendRequest):
    """Generate recommendations based on current cart items using association rules & composite scoring."""
    engine = get_recommender()
    recs = engine.get_cart_recommendations(
        cart_products=request.cart,
        top_n=request.top_n,
        min_confidence=request.min_confidence,
        min_lift=request.min_lift
    )
    return recs


@app.get("/api/analytics/summary")
def get_analytics_summary():
    """Retrieve datasets EDA statistics and transaction metrics."""
    an = get_analyzer()
    stats = an.get_summary_statistics()
    top_freq = an.get_top_products_by_frequency(top_n=10)
    top_rev = an.get_top_products_by_revenue(top_n=10)
    top_countries = an.get_top_countries(top_n=10)

    return {
        "summary": stats,
        "top_frequent_products": top_freq,
        "top_revenue_products": top_rev,
        "top_countries": top_countries,
        "charts": {
            "top_frequent_products": "/static/charts/top_frequent_products.png",
            "basket_size_distribution": "/static/charts/basket_size_distribution.png",
            "top_revenue_products": "/static/charts/top_revenue_products.png"
        }
    }


@app.get("/api/analytics/rules")
def get_association_rules(
    min_confidence: float = Query(0.20, ge=0.0, le=1.0),
    min_lift: float = Query(1.2, ge=0.0),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Explore mined association rules with metrics filtering and pagination."""
    engine = get_recommender()
    miner = engine.miner
    rules_df = miner.mine_rules(min_confidence=min_confidence, min_lift=min_lift)
    
    if rules_df.empty:
        return {"total_rules": 0, "rules": []}

    total_rules = len(rules_df)
    paged_df = rules_df.iloc[offset:offset+limit]

    formatted_rules = []
    for _, row in paged_df.iterrows():
        formatted_rules.append({
            "antecedents": list(row["antecedents"]),
            "consequents": list(row["consequents"]),
            "support": round(float(row["support"]), 4),
            "confidence": round(float(row["confidence"]), 4),
            "lift": round(float(row["lift"]), 2),
            "score": round(float(row["score"]), 4)
        })

    summary = miner.get_rules_summary()

    return {
        "total_rules": total_rules,
        "summary": summary,
        "rules": formatted_rules
    }


@app.get("/api/evaluate")
def evaluate_model():
    """Returns rule quality and train/test holdout evaluation metrics."""
    ev = get_evaluator()
    quality = ev.evaluate_rules_quality()
    holdout = ev.evaluate_train_test_split()
    return {
        "rule_quality": quality,
        "holdout_evaluation": holdout
    }

# Mount Frontend App static files at root (index.html, styles.css, app.js)
FRONTEND_DIR = BASE_DIR.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
