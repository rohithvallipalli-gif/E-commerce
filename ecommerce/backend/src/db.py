import os
import sqlite3
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import bcrypt
import jwt
from dotenv import load_dotenv

from .config import DATA_DIR, normalize_product_name

# Load environment variables
load_dotenv()

DB_PATH = DATA_DIR / "app.db"
CATALOG_JSON_PATH = DATA_DIR / "catalog.json"

SECRET_KEY = os.getenv("SECRET_KEY", "nexuscart_default_jwt_secret_key_change_me_in_prod_8492048102")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@nexuscart.local").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "AdminPass123!")

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None

def init_db():
    """Initializes tables, seeds admin, demo user, and catalog products."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT CHECK(role IN ('user', 'admin')) NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1
            );
        """)

        # Products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT,
                product TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                emoji TEXT NOT NULL DEFAULT '📦',
                price REAL NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                total REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # Order Items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                price REAL NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
            );
        """)

        conn.commit()

        # Seed Admin user if not exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,))
        admin_row = cursor.fetchone()
        if not admin_row:
            admin_hash = hash_password(ADMIN_PASSWORD)
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, role, is_active) VALUES (?, ?, ?, 'admin', 1)",
                ("NexusCart Administrator", ADMIN_EMAIL, admin_hash)
            )
            conn.commit()
            print(f"\n=======================================================")
            print(f"[NexusCart Auth] Seeded Default Admin:")
            print(f"  Email:    {ADMIN_EMAIL}")
            print(f"  Password: {ADMIN_PASSWORD}")
            print(f"=======================================================\n")
            logging.info(f"Default admin seeded: {ADMIN_EMAIL}")

        # Seed Demo User if not exists
        demo_email = "user@nexuscart.local"
        demo_pass = "UserPass123!"
        cursor.execute("SELECT id FROM users WHERE email = ?", (demo_email,))
        if not cursor.fetchone():
            demo_hash = hash_password(demo_pass)
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, role, is_active) VALUES (?, ?, ?, 'user', 1)",
                ("Demo Shopper", demo_email, demo_hash)
            )
            conn.commit()
            logging.info(f"Default demo user seeded: {demo_email}")

        # Seed products from catalog.json if products table is empty
        cursor.execute("SELECT COUNT(*) as cnt FROM products")
        p_count = cursor.fetchone()["cnt"]
        if p_count == 0:
            seed_catalog_products(conn)

def seed_catalog_products(conn: sqlite3.Connection):
    """Populates products table from catalog.json or triggers build_curated_catalog."""
    if not CATALOG_JSON_PATH.exists():
        from .build_catalog import build_curated_catalog
        build_curated_catalog()

    if CATALOG_JSON_PATH.exists():
        try:
            with open(CATALOG_JSON_PATH, "r", encoding="utf-8") as f:
                items = json.load(f)
            
            cursor = conn.cursor()
            for item in items:
                norm_name = normalize_product_name(item["product"])
                cursor.execute("""
                    INSERT OR IGNORE INTO products (stock_code, product, category, emoji, price, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(item.get("stock_code", "N/A")),
                    norm_name,
                    item.get("category", "General"),
                    item.get("emoji", "📦"),
                    float(item.get("price", 4.99)),
                    item.get("description", "")
                ))
            conn.commit()
            logging.info(f"Seeded {len(items)} products into SQLite database.")
        except Exception as e:
            logging.error(f"Error seeding products into database: {e}")

# ==================== User Management Helpers ====================

def get_user_by_email(email: str) -> Optional[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_user(name: str, email: str, password: str, role: str = "user") -> dict:
    clean_email = email.strip().lower()
    hashed = hash_password(password)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password_hash, role, is_active) VALUES (?, ?, ?, ?, 1)",
            (name.strip(), clean_email, hashed, role)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return get_user_by_id(user_id)

def list_all_users() -> List[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, role, created_at, is_active FROM users ORDER BY id ASC")
        return [dict(r) for r in cursor.fetchall()]

def update_user_status(user_id: int, is_active: bool) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
        conn.commit()
        return cursor.rowcount > 0

def update_user_role(user_id: int, role: str) -> bool:
    if role not in ("user", "admin"):
        return False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
        return cursor.rowcount > 0

# ==================== Product Helpers ====================

def get_products(
    category: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[dict], int]:
    """Retrieve catalog products with search, category filtering, sorting, and pagination."""
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if category and category.strip() and category != "All":
        query += " AND category = ?"
        params.append(category.strip())

    if q and q.strip():
        search_term = f"%{q.strip().upper()}%"
        query += " AND (UPPER(product) LIKE ? OR UPPER(description) LIKE ? OR UPPER(stock_code) LIKE ?)"
        params.extend([search_term, search_term, search_term])

    # Count total matching
    count_query = f"SELECT COUNT(*) as cnt FROM ({query})"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(count_query, params)
        total = cursor.fetchone()["cnt"]

        # Sort order
        if sort == "price_asc":
            query += " ORDER BY price ASC"
        elif sort == "price_desc":
            query += " ORDER BY price DESC"
        elif sort == "name_desc":
            query += " ORDER BY product DESC"
        else:
            query += " ORDER BY product ASC"

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        return rows, total

def get_all_categories() -> List[str]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM products ORDER BY category ASC")
        return [r["category"] for r in cursor.fetchall()]

def get_product_by_id(product_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_product(stock_code: str, product: str, category: str, emoji: str, price: float, description: str) -> dict:
    norm_name = normalize_product_name(product)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (stock_code, product, category, emoji, price, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (stock_code.strip(), norm_name, category.strip(), emoji.strip() or "📦", float(price), description.strip()))
        conn.commit()
        new_id = cursor.lastrowid
        return get_product_by_id(new_id)

def update_product(product_id: int, stock_code: str, product: str, category: str, emoji: str, price: float, description: str) -> Optional[dict]:
    norm_name = normalize_product_name(product)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE products
            SET stock_code = ?, product = ?, category = ?, emoji = ?, price = ?, description = ?
            WHERE id = ?
        """, (stock_code.strip(), norm_name, category.strip(), emoji.strip() or "📦", float(price), description.strip(), product_id))
        conn.commit()
        return get_product_by_id(product_id)

def delete_product(product_id: int) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        return cursor.rowcount > 0

# ==================== Order Helpers ====================

def create_order(user_id: int, total: float, items: List[dict]) -> dict:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user_id, total) VALUES (?, ?)", (user_id, float(total)))
        order_id = cursor.lastrowid

        for item in items:
            cursor.execute("""
                INSERT INTO order_items (order_id, product, quantity, price)
                VALUES (?, ?, ?, ?)
            """, (
                order_id,
                normalize_product_name(item["product"]),
                int(item.get("quantity", 1)),
                float(item.get("price", 0.0))
            ))

        conn.commit()
        return get_order_by_id(order_id)

def get_order_by_id(order_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.*, u.name as user_name, u.email as user_email
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.id = ?
        """, (order_id,))
        order_row = cursor.fetchone()
        if not order_row:
            return None

        order_dict = dict(order_row)
        cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
        order_dict["items"] = [dict(r) for r in cursor.fetchall()]
        return order_dict

def get_orders_by_user(user_id: int) -> List[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,))
        orders = [dict(r) for r in cursor.fetchall()]
        for o in orders:
            cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (o["id"],))
            o["items"] = [dict(r) for r in cursor.fetchall()]
        return orders

def get_all_orders() -> List[dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.*, u.name as user_name, u.email as user_email
            FROM orders o
            JOIN users u ON o.user_id = u.id
            ORDER BY o.id DESC
        """)
        orders = [dict(r) for r in cursor.fetchall()]
        for o in orders:
            cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (o["id"],))
            o["items"] = [dict(r) for r in cursor.fetchall()]
        return orders
