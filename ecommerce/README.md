# NexusCart | AI Market-Basket Recommender E-Commerce Platform

NexusCart is an enterprise-grade AI market-basket recommender e-commerce web application. It combines real-time association rule mining (FPGrowth/Apriori), item-to-item co-occurrence similarity, role-based authentication, and interactive analytics inside a modern dark glassmorphism UI.

---

## 🏛️ System Architecture

```text
+-----------------------------------------------------------------------------------+
|                            NexusCart Client (Browser)                             |
|  - Vanilla HTML5 / Modern CSS3 (Dark Glassmorphism Theme)                         |
|  - Vanilla JavaScript ES6+ (SPA with AuthFetch, AbortController, Chart.js 4.4)    |
|  - Role-based UI: Storefront, Cart Drawer, Analytics, Rules Explorer, Admin Panel|
+------------------------------------------+----------------------------------------+
                                           |
                              HTTP / REST API (JWT Bearer)
                                           |
+------------------------------------------v----------------------------------------+
|                             FastAPI Backend (app.py)                              |
|  - Security & Auth: JWT (HS256), Bcrypt Password Hashing, Login Rate-Limiting    |
|  - Access Control: public, role='user', role='admin'                              |
|  - Lifespan Pre-warming: Rule caches, Inverted Indices, Item Similarity Matrix    |
+----+-------------------+--------------------+-------------------+-----------------+
     |                   |                    |                   |
     v                   v                    v                   v
+------------+   +---------------+   +------------------+   +-------------------+
| Catalog &  |   | 3-Tier Hybrid |   | FPGrowth / Rule  |   | EDA Analytics &   |
| Database   |   | Recommender   |   | Mining Engine    |   | Model Evaluation  |
| (db.py)    |   | (recommender) |   | (assoc_rules.py) |   | (analysis / eval) |
|            |   |               |   |                  |   |                   |
| SQLite3:   |   | Tier 1: Rules |   | mlxtend FPGrowth |   | Basket Histogram  |
| - users    |   | Tier 2: Item  |   | In-memory filter |   | Top Products      |
| - products |   |    Similarity |   | Inverted Index   |   | Revenue Analysis  |
| - orders   |   | Tier 3: Trend |   | 68,000+ cached   |   | Precision@K /     |
| - items    |   |    Fallback   |   | rules (<40ms)    |   | Hit Rate Holdout  |
+------------+   +---------------+   +------------------+   +-------------------+
```

---

## 🚀 Key Features & Bug Fixes

1. **Association Rules Engine (Task 1 Fix):**
   - Mined comprehensive rule base using FPGrowth at `min_support=0.005`, `min_confidence=0.05`, and `min_lift=1.0` (68,467 rules saved to `backend/models/association_rules.pkl`).
   - Query filters (`min_confidence`, `min_lift`, `limit`) are evaluated in-memory via pandas vector operations in < 50ms without re-mining.
   - Lifespan startup pre-warms the cache and builds an inverted index for $O(1)$ antecedent candidate lookups.
   - Frontend features safe JSON serialization, 15-second `AbortController` timeout, 7-column error state with a retry button.

2. **Client-Side Analytics with Chart.js (Task 2 Fix):**
   - Replaced broken PNG `<img onerror>` fallbacks pointing to defunct services with responsive Chart.js 4.4 canvas elements.
   - 4 dark-themed charts with gradient accents:
     - Top 10 Most Frequently Purchased Products (Horizontal Bar)
     - Top 10 Revenue Generating Products (Horizontal Bar with GBP currency tooltips)
     - Basket Size Distribution (Histogram buckets: 1, 2, 3-5, 6-10, 11-20, 21-50, 50+)
     - Top 10 Purchasing Countries (Doughnut chart)
   - Dynamic tab resize handlers (`chart.resize()`) preventing 0px collapse on hidden tabs.

3. **3-Tier Diverse Recommender Engine (Task 3 Fix):**
   - **Tier 1 (Association Rules):** Multi-item cart aggregation with antecedent linkage boost.
   - **Tier 2 (Item-to-Item Co-occurrence Similarity):** Precomputed Jaccard similarity matrix across catalog items on the 18,266-transaction basket matrix.
   - **Tier 3 (Shuffled Popularity Fallback):** Deterministically seeded by cart items across popular catalog goods.
   - Prevents empty cart queries, strictly restricts output to available catalog items, and guarantees cart items are excluded.
   - Interactive **"Why recommended?"** popover detailing rule metrics (support, confidence, lift, linkage score).

4. **Curated Product Catalog (Task 4):**
   - Programmatically derived 64 high-quality catalog products from UCI Online Retail dataset.
   - Curated across 8 diverse categories: *Kitchenware, Home Decor, Storage & Bags, Gift & Party, Garden, Lighting, Stationery, Seasonal/Christmas*.
   - Filter chips, search bar, sort options (price asc/desc, name asc/desc), and quick-try preset bundles.

5. **Role-Based Authentication & Admin Suite (Task 5):**
   - SQLite persistence (`backend/data/app.db`) for `users`, `products`, `orders`, and `order_items`.
   - Passwords securely hashed with `bcrypt`. JWT access tokens (HS256, 60m expiry).
   - Rate limiting and incremental login delays on repeated failed authentication attempts.
   - Role-based tabs and backend endpoint guards (`get_current_user` and `require_admin`).
   - Admin Panel with full Product CRUD, User activation/deactivation/role promotion, Order monitoring, and Model Retraining controls.

---

## 🔑 Default Credentials

| Role | Email | Password | Allowed Access |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@nexuscart.local` | `AdminPass123!` | Storefront, Analytics, Rules Explorer, Model Accuracy, Admin Panel (Product CRUD, Users, Orders, Retrain) |
| **User (Demo)** | `user@nexuscart.local` | `UserPass123!` | Storefront & Cart Drawer, Recommendations, Place Orders, My Orders |

> Quick-fill demo buttons are provided directly on the Login form for one-click access.

---

## ⚙️ Environment Variables (`.env`)

```env
SECRET_KEY=nexuscart_production_super_secret_jwt_key_2026_x89f
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
ADMIN_EMAIL=admin@nexuscart.local
ADMIN_PASSWORD=AdminPass123!
```

---

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.10+ (tested on Python 3.13)
- Windows PowerShell or Unix Terminal

### 1. Clone & Set Up Virtual Environment
```bash
git clone <repo-url>
cd ecommerce

# Create clean virtual environment
python -m venv venv

# Activate virtual environment
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize & Start the Server
```bash
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```
The server will warm the rules cache, verify the SQLite database, and launch on `http://127.0.0.1:8000`.

---

## 🧪 Automated Testing & Verification

Run the comprehensive automated test suites:

```bash
# 1. Test Recommender Engine Diversity & Blending
python tests/test_recommender.py

# 2. Test Full 14-Step Acceptance Suite (Auth, 401/403 Guards, Rules Speed, CRUD, Orders)
python tests/test_acceptance.py
```

### Acceptance Test Results
- ✅ **1. Health endpoint online** (200 OK)
- ✅ **2. Unauthenticated protected endpoints return 401 Unauthorized**
- ✅ **3. User registration & JWT issuance** (`role='user'`)
- ✅ **4. Role enforcement** (User receives 403 Forbidden on all admin endpoints)
- ✅ **5. Catalog browsing, category filtering, and search** (64 products across 8 categories)
- ✅ **6. Recommendations engine** (Empty cart returns `[]`, distinct items yield unique top-N recs, cart items excluded)
- ✅ **7. Order placement and retrieval** (`POST /api/orders` & `GET /api/orders/me`)
- ✅ **8. Admin authentication**
- ✅ **9. Association Rules endpoint** (Returns ranked rules in <50ms; filters change results)
- ✅ **10. Dataset Analytics Summary** (Includes `basket_size_histogram` and top metrics)
- ✅ **11. Model Evaluation endpoint** (Rule quality and train/test holdout precision)
- ✅ **12. Admin Product CRUD** (Create, search in storefront, update price, delete)
- ✅ **13. Admin User & Order management**
- ✅ **14. Password security** (Verified stored as bcrypt hashes in `app.db`)

---

## 📡 REST API Reference

### Public Endpoints
- `GET /api/health` - Server health status and version.
- `POST /api/auth/register` - Create customer account (`role: 'user'`).
- `POST /api/auth/login` - Authenticate with email and password to receive JWT token.

### Customer Endpoints (`role: user` or `admin`)
- `GET /api/auth/me` - Authenticated user profile and role.
- `POST /api/auth/logout` - Session invalidation.
- `GET /api/products` - Catalog search, category filter, sort, and pagination.
- `GET /api/categories` - List of product categories.
- `POST /api/recommend` - 3-tier market basket recommendations for active cart items.
- `POST /api/orders` - Place checkout order.
- `GET /api/orders/me` - Retrieve authenticated user's order history.

### Admin-Only Endpoints (`role: admin`)
- `GET /api/analytics/summary` - Transaction statistics, top products, revenue, and basket size histogram.
- `GET /api/analytics/rules` - Filtered association rules ranked by lift/confidence/score.
- `GET /api/evaluate` - Rule quality metrics and train/test holdout evaluation (Hit Rate, Precision@K).
- `POST /api/admin/products` - Create new catalog product.
- `PUT /api/admin/products/{id}` - Update existing product.
- `DELETE /api/admin/products/{id}` - Delete catalog product.
- `GET /api/admin/users` - List all registered user accounts.
- `PATCH /api/admin/users/{id}/status` - Enable or disable user account.
- `PATCH /api/admin/users/{id}/role` - Promote/demote user role.
- `GET /api/admin/orders` - List all system orders across all users.
- `POST /api/admin/retrain` - Re-mine association rules with custom `min_support`, `min_confidence`, and `min_lift`.
