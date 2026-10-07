import requests
import json
import sqlite3
import time

BASE_URL = "http://127.0.0.1:8000"

def test_acceptance():
    print("=== NexusCart Acceptance Testing Suite ===")
    
    # 1. Health check
    res = requests.get(f"{BASE_URL}/api/health")
    assert res.status_code == 200, f"Health check failed: {res.status_code}"
    print("[PASS] 1. Health endpoint online (200 OK)")

    # 2. Protected endpoints without token return 401
    unauth_urls = [
        ("GET", f"{BASE_URL}/api/products"),
        ("POST", f"{BASE_URL}/api/recommend"),
        ("GET", f"{BASE_URL}/api/analytics/summary"),
        ("GET", f"{BASE_URL}/api/analytics/rules"),
        ("GET", f"{BASE_URL}/api/evaluate"),
        ("GET", f"{BASE_URL}/api/admin/users")
    ]
    for method, url in unauth_urls:
        r = requests.get(url) if method == "GET" else requests.post(url, json={})
        assert r.status_code == 401, f"Expected 401 for {url}, got {r.status_code}"
    print("[PASS] 2. All protected endpoints strictly return 401 Unauthorized without token")

    # 3. User Registration and Login
    test_user_email = f"customer_{int(time.time())}@nexuscart.local"
    reg_payload = {
        "name": "Jane Customer",
        "email": test_user_email,
        "password": "SecurePassword123!"
    }
    r = requests.post(f"{BASE_URL}/api/auth/register", json=reg_payload)
    assert r.status_code in [200, 201], f"Registration failed: {r.status_code} {r.text}"
    user_data = r.json()
    assert user_data["user"]["role"] == "user"
    user_token = user_data["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}
    print("[PASS] 3. Customer registration and JWT token creation successful (role='user')")

    # 4. Role Enforcement: User cannot access Admin endpoints (403)
    admin_only_urls = [
        f"{BASE_URL}/api/analytics/summary",
        f"{BASE_URL}/api/analytics/rules",
        f"{BASE_URL}/api/evaluate",
        f"{BASE_URL}/api/admin/users",
        f"{BASE_URL}/api/admin/orders"
    ]
    for url in admin_only_urls:
        r = requests.get(url, headers=user_headers)
        assert r.status_code == 403, f"Expected 403 for user at {url}, got {r.status_code}"
    print("[PASS] 4. User cannot access any admin endpoints (403 Forbidden)")

    # 5. User storefront browsing & filtering
    r = requests.get(f"{BASE_URL}/api/products?limit=100", headers=user_headers)
    assert r.status_code == 200
    res_json = r.json()
    products = res_json["products"]
    assert res_json["total"] >= 60, f"Expected total >=60, got {res_json['total']}"
    categories = set(p["category"] for p in products)
    assert len(categories) >= 6, f"Expected >=6 categories, got {len(categories)}"
    
    # Filter by category
    r = requests.get(f"{BASE_URL}/api/products?category=Kitchenware", headers=user_headers)
    assert r.status_code == 200
    kw_products = r.json()["products"]
    assert all(p["category"] == "Kitchenware" for p in kw_products)
    
    # Search by keyword
    r = requests.get(f"{BASE_URL}/api/products?q=CAKE", headers=user_headers)
    assert r.status_code == 200
    assert len(r.json()["products"]) > 0
    print(f"[PASS] 5. Catalog browsing, category filtering, and search verified ({res_json['total']} products across {len(categories)} categories)")

    # 6. Recommendations & Cart
    # Empty cart returns empty recommendations
    r = requests.post(f"{BASE_URL}/api/recommend", json={"cart": []}, headers=user_headers)
    assert r.status_code == 200
    recs = r.json()
    assert len(recs) == 0
    
    # Single item in cart
    test_prod = products[0]["product"]
    r = requests.post(f"{BASE_URL}/api/recommend", json={"cart": [test_prod], "top_n": 5}, headers=user_headers)
    assert r.status_code == 200
    recs = r.json()
    assert len(recs) == 5
    rec_names = [rec["product"] for rec in recs]
    assert test_prod not in rec_names, "Cart item was returned as recommendation!"
    assert all("score" in rec and "rule_description" in rec for rec in recs)
    print(f"[PASS] 6. Recommendations verified: empty cart returns [], '{test_prod}' gets 5 distinct recommendations with explanations")

    # 7. Order Placement & User Orders
    order_payload = {
        "items": [
            {"product": products[0]["product"], "quantity": 2, "price": products[0]["price"]},
            {"product": products[1]["product"], "quantity": 1, "price": products[1]["price"]}
        ],
        "total": round(products[0]["price"] * 2 + products[1]["price"] * 1, 2)
    }
    r = requests.post(f"{BASE_URL}/api/orders", json=order_payload, headers=user_headers)
    assert r.status_code == 200
    order_id = r.json()["order"]["id"]
    
    r = requests.get(f"{BASE_URL}/api/orders/me", headers=user_headers)
    assert r.status_code == 200
    user_orders = r.json()
    assert any(o["id"] == order_id for o in user_orders)
    print(f"[PASS] 7. Order placement and retrieval verified (Order #{order_id})")

    # 8. Admin Login & Full Access
    login_payload = {
        "email": "admin@nexuscart.local",
        "password": "AdminPass123!"
    }
    r = requests.post(f"{BASE_URL}/api/auth/login", json=login_payload)
    assert r.status_code == 200
    admin_data = r.json()
    assert admin_data["user"]["role"] == "admin"
    admin_token = admin_data["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("[PASS] 8. Admin authentication successful")

    # 9. Task 1 Verification: Association Rules endpoint
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/analytics/rules?min_confidence=0.2&min_lift=1.2&limit=25", headers=admin_headers)
    elapsed = time.time() - t0
    assert r.status_code == 200
    rules_resp = r.json()
    assert len(rules_resp["rules"]) == 25
    total_default = rules_resp["total_rules"]
    assert elapsed < 1.5, f"Rules endpoint took {elapsed:.2f}s, expected < 1.5s"
    
    # Changing filters changes row count/results
    r_filtered = requests.get(f"{BASE_URL}/api/analytics/rules?min_confidence=0.5&min_lift=2.0&limit=25", headers=admin_headers)
    assert r_filtered.status_code == 200
    total_filtered = r_filtered.json()["total_rules"]
    assert total_filtered < total_default, f"Expected fewer rules with tighter filters: {total_filtered} vs {total_default}"
    print(f"[PASS] 9. Association Rules endpoint verified: {len(rules_resp['rules'])} ranked rules in {elapsed*1000:.1f}ms; filters change results ({total_default} -> {total_filtered})")

    # 10. Task 2 Verification: Dataset Analytics Summary
    r = requests.get(f"{BASE_URL}/api/analytics/summary", headers=admin_headers)
    assert r.status_code == 200
    summary = r.json()
    assert "basket_size_histogram" in summary, "Missing basket_size_histogram in summary!"
    assert len(summary["basket_size_histogram"]) >= 5
    assert len(summary["top_frequent_products"]) >= 10
    assert len(summary["top_revenue_products"]) >= 10
    assert len(summary["top_countries"]) >= 10
    print("[PASS] 10. Dataset Analytics Summary verified with basket_size_histogram and top product metrics")

    # 11. Model Evaluation endpoint
    r = requests.get(f"{BASE_URL}/api/evaluate", headers=admin_headers)
    assert r.status_code == 200
    eval_data = r.json()
    assert "rule_quality" in eval_data and "holdout_evaluation" in eval_data
    print("[PASS] 11. Model Evaluation endpoint verified")

    ts = int(time.time())
    new_prod_payload = {
        "product": f"TEST VINTAGE TEA SET {ts}",
        "category": "Kitchenware",
        "price": 18.50,
        "stock_code": f"TEST{ts % 10000}",
        "description": "Unique test vintage tea set for testing CRUD",
        "emoji": "🍵"
    }
    r = requests.post(f"{BASE_URL}/api/admin/products", json=new_prod_payload, headers=admin_headers)
    assert r.status_code in [200, 201], f"Create product failed: {r.status_code} {r.text}"
    created_prod = r.json()
    new_prod_id = created_prod["id"]
    
    # Verify product appears in storefront
    r = requests.get(f"{BASE_URL}/api/products", params={"q": str(ts)}, headers=user_headers)
    assert r.status_code == 200
    assert len(r.json()["products"]) == 1
    
    # Update product
    r = requests.put(f"{BASE_URL}/api/admin/products/{new_prod_id}", json={
        "product": f"TEST VINTAGE TEA SET {ts}",
        "category": "Kitchenware",
        "price": 22.00
    }, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["price"] == 22.00
    
    # Delete product
    r = requests.delete(f"{BASE_URL}/api/admin/products/{new_prod_id}", headers=admin_headers)
    assert r.status_code == 200
    
    r = requests.get(f"{BASE_URL}/api/products", params={"q": str(ts)}, headers=user_headers)
    assert len(r.json()["products"]) == 0
    print("[PASS] 12. Admin Product CRUD verified (Create, Search in storefront, Update, Delete)")

    # 13. Admin User Management & Orders
    r = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
    assert r.status_code == 200
    users_list = r.json()
    assert len(users_list) >= 2
    
    r = requests.get(f"{BASE_URL}/api/admin/orders", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1
    print("[PASS] 13. Admin Users and Orders endpoints verified")

    # 14. Password Bcrypt Hash Verification in SQLite
    conn = sqlite3.connect("backend/data/app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE email='admin@nexuscart.local'")
    hash_val = cursor.fetchone()[0]
    conn.close()
    assert hash_val.startswith("$2b$") or hash_val.startswith("$2a$"), f"Not a valid bcrypt hash: {hash_val}"
    print(f"[PASS] 14. SQLite users table verified: password is stored as secure bcrypt hash ({hash_val[:12]}...)")

    print("\nALL 14 ACCEPTANCE CHECKS PASSED WITH ZERO ERRORS!")

if __name__ == "__main__":
    test_acceptance()
