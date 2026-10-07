import os
import re
import time
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

import pandas as pd
import numpy as np
from fastapi import FastAPI, Query, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from backend.src.config import BASE_DIR, EDA_CHARTS_DIR, COLUMN_PRODUCT, normalize_product_name
from backend.src.preprocessing import DataPreprocessor
from backend.src.association_rules import AssociationRuleMiner
from backend.src.recommender import RecommendationEngine
from backend.src.analysis import EDAAnalyzer
from backend.src.evaluation import ModelEvaluator
from backend.src.db import (
    init_db,
    get_user_by_email,
    get_user_by_id,
    create_user,
    list_all_users,
    update_user_status,
    update_user_role,
    verify_password,
    create_access_token,
    decode_access_token,
    get_products,
    get_all_categories,
    get_product_by_id,
    create_product,
    update_product,
    delete_product,
    create_order,
    get_orders_by_user,
    get_all_orders
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Singletons for Recommender Engine, Analyzer, and Evaluator
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initializing NexusCart SQLite database...")
    init_db()
    logging.info("Pre-warming Recommender models, rules cache, and EDA charts...")
    try:
        engine = get_recommender()
        engine.miner.load_cache()
        engine.miner.mine_rules(min_confidence=0.20, min_lift=1.2)
    except Exception as e:
        logging.error(f"Error warming rules cache during lifespan: {e}")
    try:
        an = get_analyzer()
        an.generate_eda_plots()
    except Exception as e:
        logging.warning(f"Error pre-generating EDA plots: {e}")
    logging.info("NexusCart FastAPI Server startup complete!")
    yield

app = FastAPI(
    title="NexusCart E-Commerce Recommender API",
    description="REST API for real-time market basket recommendation, association rules exploration, role-based auth, and analytics.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS setup restricted to app origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Mount EDA charts static directory
if not EDA_CHARTS_DIR.exists():
    EDA_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/charts", StaticFiles(directory=str(EDA_CHARTS_DIR)), name="charts")

# ==================== Authentication & Security ====================

security = HTTPBearer(auto_error=False)
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Basic in-memory brute force delay tracker: ip/email -> list of failed attempt timestamps
failed_login_attempts: Dict[str, List[float]] = {}

def check_login_rate_limit(key: str):
    now = time.time()
    attempts = failed_login_attempts.get(key, [])
    # Keep attempts in the last 60 seconds
    recent = [t for t in attempts if now - t < 60]
    failed_login_attempts[key] = recent
    if len(recent) >= 6:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 60 seconds."
        )

def record_failed_login(key: str):
    now = time.time()
    if key not in failed_login_attempts:
        failed_login_attempts[key] = []
    failed_login_attempts[key].append(now)
    # Add a slight delay to discourage automated brute force
    time.sleep(0.3)

def clear_failed_login(key: str):
    if key in failed_login_attempts:
        del failed_login_attempts[key]

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing. Please log in."
        )
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token. Please log in again."
        )
    user_id = payload.get("user_id") or payload.get("sub")
    try:
        user = get_user_by_id(int(user_id))
    except (ValueError, TypeError):
        user = get_user_by_email(str(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account does not exist."
        )
    if not user.get("is_active", 1):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated. Please contact an administrator."
        )
    return user

def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Administrator access required."
        )
    return current_user

# ==================== Pydantic Schemas ====================

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(...)
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[str] = None

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class UserStatusRequest(BaseModel):
    is_active: bool

class UserRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(user|admin)$")

class ProductCreateUpdateRequest(BaseModel):
    stock_code: Optional[str] = "N/A"
    product: str = Field(..., min_length=2)
    category: str = Field(..., min_length=2)
    emoji: Optional[str] = "📦"
    price: float = Field(..., gt=0.0)
    description: Optional[str] = ""

class OrderItemSchema(BaseModel):
    product: str
    quantity: int = Field(default=1, ge=1)
    price: float = Field(ge=0.0)

class CreateOrderRequest(BaseModel):
    items: List[OrderItemSchema]
    total: float = Field(ge=0.0)

class RecommendRequest(BaseModel):
    cart: List[str] = Field(..., description="List of product descriptions currently in the cart")
    top_n: int = Field(default=6, ge=1, le=20)
    min_confidence: float = Field(default=0.05, ge=0.0, le=1.0)
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

class RetrainRequest(BaseModel):
    min_support: float = Field(default=0.005, ge=0.001, le=0.1)
    min_confidence: float = Field(default=0.20, ge=0.01, le=1.0)
    min_lift: float = Field(default=1.2, ge=0.0)

# ==================== Public Endpoints ====================

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "NexusCart E-Commerce Recommender API",
        "version": "1.0.0"
    }

@app.post("/api/auth/register", response_model=AuthResponse)
def register_user(req: RegisterRequest):
    """Registers a new standard user account with role 'user'."""
    clean_email = req.email.strip().lower()
    if not EMAIL_REGEX.match(clean_email):
        raise HTTPException(status_code=400, detail="Invalid email address format.")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    existing = get_user_by_email(clean_email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = create_user(
        name=req.name.strip(),
        email=clean_email,
        password=req.password,
        role="user"
    )
    token = create_access_token({"sub": str(user["id"]), "user_id": user["id"], "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }

@app.post("/api/auth/login", response_model=AuthResponse)
def login_user(req: LoginRequest):
    """Logs in with email and password, returning a JWT access token."""
    clean_email = req.email.strip().lower()
    check_login_rate_limit(clean_email)

    user = get_user_by_email(clean_email)
    if not user or not verify_password(req.password, user["password_hash"]):
        record_failed_login(clean_email)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    if not user.get("is_active", 1):
        raise HTTPException(status_code=403, detail="Account is disabled. Contact an administrator.")

    clear_failed_login(clean_email)
    token = create_access_token({"sub": str(user["id"]), "user_id": user["id"], "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }

@app.get("/api/auth/me", response_model=UserResponse)
def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Returns the authenticated user's profile and active role."""
    return current_user

@app.post("/api/auth/logout")
def logout_user(current_user: dict = Depends(get_current_user)):
    """Client-side token deletion is acknowledged."""
    return {"status": "success", "message": "Successfully logged out."}

# ==================== Catalog & Recommender Endpoints ====================

@app.get("/api/products")
def list_products(
    q: Optional[str] = Query(None, description="Search keyword"),
    category: Optional[str] = Query(None, description="Category filter"),
    sort: Optional[str] = Query(None, description="Sort mode: price_asc, price_desc, name_desc, name_asc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """Retrieve catalog products from SQLite database with category filter, search, sort, and pagination."""
    products, total = get_products(category=category, q=q, sort=sort, limit=limit, offset=offset)
    categories = get_all_categories()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "categories": categories,
        "products": products
    }

@app.get("/api/categories")
def list_categories(current_user: dict = Depends(get_current_user)):
    """Returns distinct product categories in the active catalog."""
    return get_all_categories()

@app.post("/api/recommend", response_model=List[RecommendationItem])
def recommend_products(request: RecommendRequest, current_user: dict = Depends(get_current_user)):
    """
    Generate recommendations based on current cart items using:
    - Tier 1: Association Rules
    - Tier 2: Item-to-Item Co-occurrence Similarity
    - Tier 3: Deterministic catalog popularity
    """
    engine = get_recommender()
    recs = engine.get_cart_recommendations(
        cart_products=request.cart,
        top_n=request.top_n,
        min_confidence=request.min_confidence,
        min_lift=request.min_lift
    )
    return recs

# ==================== User Orders & Checkout ====================

@app.post("/api/orders")
def place_order(req: CreateOrderRequest, current_user: dict = Depends(get_current_user)):
    """Places an order for the logged-in user, saving to the database."""
    if not req.items:
        raise HTTPException(status_code=400, detail="Cart is empty. Cannot checkout.")

    order = create_order(
        user_id=current_user["id"],
        total=req.total,
        items=[item.model_dump() for item in req.items]
    )
    return {
        "status": "success",
        "message": "Order placed successfully!",
        "order": order
    }

@app.get("/api/orders/me")
def get_my_orders(current_user: dict = Depends(get_current_user)):
    """Returns orders placed by the current user."""
    return get_orders_by_user(current_user["id"])

# ==================== ADMIN ONLY Endpoints ====================

@app.get("/api/analytics/summary")
def get_analytics_summary(admin_user: dict = Depends(require_admin)):
    """Retrieve datasets EDA statistics and transaction metrics (ADMIN only)."""
    try:
        an = get_analyzer()
        stats = an.get_summary_statistics()
        top_freq = an.get_top_products_by_frequency(top_n=10)
        top_rev = an.get_top_products_by_revenue(top_n=10)
        top_countries = an.get_top_countries(top_n=10)
        basket_hist = an.get_basket_size_histogram()

        return {
            "summary": stats,
            "top_frequent_products": top_freq,
            "top_revenue_products": top_rev,
            "top_countries": top_countries,
            "basket_size_histogram": basket_hist,
            "charts": {
                "top_frequent_products": "/static/charts/top_frequent_products.png",
                "basket_size_distribution": "/static/charts/basket_size_distribution.png",
                "top_revenue_products": "/static/charts/top_revenue_products.png"
            }
        }
    except Exception as e:
        logging.error(f"Error in /api/analytics/summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate analytics summary: {str(e)}")

@app.get("/api/analytics/rules")
def get_association_rules(
    min_confidence: float = Query(0.20, ge=0.0, le=1.0),
    min_lift: float = Query(1.2, ge=0.0),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin_user: dict = Depends(require_admin)
):
    """Explore mined association rules with metrics filtering and pagination (ADMIN only)."""
    try:
        offset_val = int(offset.default if hasattr(offset, "default") else offset)
        limit_val = int(limit.default if hasattr(limit, "default") else limit)
        conf_val = float(min_confidence.default if hasattr(min_confidence, "default") else min_confidence)
        lift_val = float(min_lift.default if hasattr(min_lift, "default") else min_lift)

        engine = get_recommender()
        miner = engine.miner
        rules_df = miner.mine_rules(min_confidence=conf_val, min_lift=lift_val)
        
        if rules_df is None or rules_df.empty:
            summary = miner.get_rules_summary(pd.DataFrame())
            return {
                "total_rules": 0,
                "summary": summary,
                "rules": []
            }

        total_rules = len(rules_df)
        paged_df = rules_df.iloc[offset_val:offset_val+limit_val]

        formatted_rules = []
        for _, row in paged_df.iterrows():
            def _clean(val, digits=4):
                if val is None or pd.isna(val) or np.isinf(val):
                    return None
                return round(float(val), digits)

            formatted_rules.append({
                "antecedents": list(row["antecedents"]) if hasattr(row["antecedents"], "__iter__") else [str(row["antecedents"])],
                "consequents": list(row["consequents"]) if hasattr(row["consequents"], "__iter__") else [str(row["consequents"])],
                "support": _clean(row.get("support"), 4),
                "confidence": _clean(row.get("confidence"), 4),
                "lift": _clean(row.get("lift"), 2),
                "score": _clean(row.get("score"), 4)
            })

        summary = miner.get_rules_summary(rules_df)

        return {
            "total_rules": total_rules,
            "summary": summary,
            "rules": formatted_rules
        }
    except Exception as e:
        logging.error(f"Error in /api/analytics/rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch association rules: {str(e)}")

@app.get("/api/evaluate")
def evaluate_model(admin_user: dict = Depends(require_admin)):
    """Returns rule quality and train/test holdout evaluation metrics (ADMIN only)."""
    ev = get_evaluator()
    quality = ev.evaluate_rules_quality()
    holdout = ev.evaluate_train_test_split()
    return {
        "rule_quality": quality,
        "holdout_evaluation": holdout
    }

# Product CRUD
@app.post("/api/admin/products")
def admin_create_product(req: ProductCreateUpdateRequest, admin_user: dict = Depends(require_admin)):
    """Create a new product in the catalog (ADMIN only)."""
    try:
        new_prod = create_product(
            stock_code=req.stock_code or "N/A",
            product=req.product,
            category=req.category,
            emoji=req.emoji or "📦",
            price=req.price,
            description=req.description or ""
        )
        # Update recommender memory
        engine = get_recommender()
        engine.refresh_catalog()
        return new_prod
    except Exception as e:
        logging.error(f"Failed to create product: {e}")
        raise HTTPException(status_code=400, detail=f"Could not create product: {str(e)}")

@app.put("/api/admin/products/{product_id}")
def admin_update_product(product_id: int, req: ProductCreateUpdateRequest, admin_user: dict = Depends(require_admin)):
    """Update an existing catalog product (ADMIN only)."""
    existing = get_product_by_id(product_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found.")

    updated = update_product(
        product_id=product_id,
        stock_code=req.stock_code or existing.get("stock_code", "N/A"),
        product=req.product,
        category=req.category,
        emoji=req.emoji or "📦",
        price=req.price,
        description=req.description or ""
    )
    engine = get_recommender()
    engine.refresh_catalog()
    return updated

@app.delete("/api/admin/products/{product_id}")
def admin_delete_product(product_id: int, admin_user: dict = Depends(require_admin)):
    """Delete a catalog product (ADMIN only)."""
    existing = get_product_by_id(product_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found.")

    deleted = delete_product(product_id)
    engine = get_recommender()
    engine.refresh_catalog()
    return {"status": "success", "message": f"Product #{product_id} deleted."}

# User Management
@app.get("/api/admin/users")
def admin_list_users(admin_user: dict = Depends(require_admin)):
    """List all registered users (ADMIN only)."""
    return list_all_users()

@app.patch("/api/admin/users/{user_id}/status")
def admin_update_user_status(user_id: int, req: UserStatusRequest, admin_user: dict = Depends(require_admin)):
    """Enable or disable a user account (ADMIN only)."""
    if user_id == admin_user["id"] and not req.is_active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own admin account.")
    success = update_user_status(user_id, req.is_active)
    if not success:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"status": "success", "user_id": user_id, "is_active": req.is_active}

@app.patch("/api/admin/users/{user_id}/role")
def admin_update_user_role(user_id: int, req: UserRoleRequest, admin_user: dict = Depends(require_admin)):
    """Change a user's role between 'user' and 'admin' (ADMIN only)."""
    if user_id == admin_user["id"] and req.role != "admin":
        raise HTTPException(status_code=400, detail="You cannot revoke your own admin role.")
    success = update_user_role(user_id, req.role)
    if not success:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"status": "success", "user_id": user_id, "role": req.role}

# Order Management
@app.get("/api/admin/orders")
def admin_list_orders(admin_user: dict = Depends(require_admin)):
    """List all customer orders (ADMIN only)."""
    return get_all_orders()

# Model Retraining
@app.post("/api/admin/retrain")
def admin_retrain_model(req: RetrainRequest, admin_user: dict = Depends(require_admin)):
    """Re-mines association rules with specified parameters and updates cache (ADMIN only)."""
    engine = get_recommender()
    new_rules = engine.miner.mine_rules(
        min_support=req.min_support,
        min_confidence=req.min_confidence,
        min_lift=req.min_lift,
        force_recalculate=True
    )
    engine.refresh_catalog()
    return {
        "status": "success",
        "message": f"Successfully retrained model with min_support={req.min_support}, min_confidence={req.min_confidence}, min_lift={req.min_lift}.",
        "total_rules": len(new_rules),
        "summary": engine.miner.get_rules_summary(new_rules)
    }

# Mount Static Charts directory (for optional PNG downloads)
if EDA_CHARTS_DIR.exists():
    app.mount("/static/charts", StaticFiles(directory=str(EDA_CHARTS_DIR)), name="charts")

# Mount Frontend App static files at root (index.html, styles.css, app.js)
FRONTEND_DIR = BASE_DIR.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
