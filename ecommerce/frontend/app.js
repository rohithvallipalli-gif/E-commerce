/**
 * NexusCart E-Commerce Market Basket Recommender Frontend Logic
 */

const API_BASE = window.location.origin.includes("http") ? window.location.origin : "http://localhost:8000";

// Curated Showcase Products (Fallback Catalog)
const DEMO_PRODUCTS = [
    { product: "WHITE HANGING HEART T-LIGHT HOLDER", tag: "Home Decor", price: "$4.99" },
    { product: "GREEN REGENCY TEACUP AND SAUCER", tag: "Kitchenware", price: "$12.50" },
    { product: "ROSES REGENCY TEACUP AND SAUCER", tag: "Kitchenware", price: "$12.50" },
    { product: "PINK REGENCY TEACUP AND SAUCER", tag: "Kitchenware", price: "$12.50" },
    { product: "REGENCY CAKESTAND 3 TIER", tag: "Kitchenware", price: "$24.99" },
    { product: "JUMBO BAG RED RETROSPOT", tag: "Storage & Bags", price: "$6.99" },
    { product: "JUMBO BAG PINK POLKADOT", tag: "Storage & Bags", price: "$6.99" },
    { product: "JUMBO SHOPPER VINTAGE RED Paisley", tag: "Storage & Bags", price: "$7.50" },
    { product: "LUNCH BAG RED RETROSPOT", tag: "Bags", price: "$5.99" },
    { product: "HEART OF WICKER SMALL", tag: "Home Decor", price: "$3.99" },
    { product: "HEART OF WICKER LARGE", tag: "Home Decor", price: "$7.99" },
    { product: "WOODEN PICTURE FRAME WHITE FINISH", tag: "Home Decor", price: "$9.99" },
    { product: "PARTY BUNTING", tag: "Party", price: "$8.50" },
    { product: "SPOTTY BUNTING", tag: "Party", price: "$8.50" },
    { product: "SET OF 3 CAKE TINS PANTRY DESIGN", tag: "Kitchenware", price: "$15.99" },
    { product: "ALARM CLOCK BAKELIKE RED", tag: "Clocks", price: "$14.99" }
];

// App State
const state = {
    cart: [],
    catalog: [],
    rules: [],
    analytics: null,
    evaluation: null,
    searchQuery: ""
};

// DOM Elements
document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initCartDrawer();
    initSearch();
    initPresets();
    initRulesFilters();

    // Initial Load
    fetchCatalog();
    fetchAnalytics();
    fetchRules();
    fetchEvaluation();
    triggerRecommendations();
});


/* Navigation Tabs */
function initNavigation() {
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");

            navButtons.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));

            btn.classList.add("active");
            const targetEl = document.getElementById(targetTab);
            if (targetEl) targetEl.classList.add("active");
        });
    });
}


/* Cart & Drawer Handlers */
function initCartDrawer() {
    const cartToggleBtn = document.getElementById("cartToggleBtn");
    const cartOverlay = document.getElementById("cartOverlay");
    const cartDrawer = document.getElementById("cartDrawer");
    const closeCartBtn = document.getElementById("closeCartBtn");
    const btnClearCart = document.getElementById("btnClearCart");

    const toggleCart = (open) => {
        cartOverlay.classList.toggle("active", open);
        cartDrawer.classList.toggle("active", open);
    };

    cartToggleBtn.addEventListener("click", () => toggleCart(true));
    closeCartBtn.addEventListener("click", () => toggleCart(false));
    cartOverlay.addEventListener("click", () => toggleCart(false));

    btnClearCart.addEventListener("click", () => {
        state.cart = [];
        updateCartUI();
        triggerRecommendations();
    });
}

function addToCart(productName) {
    if (!state.cart.includes(productName)) {
        state.cart.push(productName);
        updateCartUI();
        triggerRecommendations();
    }
}

function removeFromCart(productName) {
    state.cart = state.cart.filter(p => p !== productName);
    updateCartUI();
    triggerRecommendations();
}

function updateCartUI() {
    const badge = document.getElementById("cartCountBadge");
    const drawerBody = document.getElementById("cartDrawerBody");
    const drawerItemCount = document.getElementById("cartDrawerItemCount");
    const cartTagsContainer = document.getElementById("cartTagsContainer");

    badge.innerText = state.cart.length;
    drawerItemCount.innerText = state.cart.length;

    // Update Buttons in Products Grid
    document.querySelectorAll(".btn-add-cart").forEach(btn => {
        const prod = btn.getAttribute("data-product");
        if (state.cart.includes(prod)) {
            btn.classList.add("in-cart");
            btn.innerHTML = `<i class="fa-solid fa-check"></i> Added`;
        } else {
            btn.classList.remove("in-cart");
            btn.innerHTML = `<i class="fa-solid fa-cart-plus"></i> Add to Cart`;
        }
    });

    // Update Drawer Body
    if (state.cart.length === 0) {
        drawerBody.innerHTML = `
            <div class="empty-cart-state">
                <i class="fa-solid fa-cart-flatbed-suitcase"></i>
                <p>Your shopping cart is empty.</p>
            </div>
        `;
        cartTagsContainer.innerHTML = `<span class="empty-cart-text">Cart is empty. Add products to generate co-purchase rules!</span>`;
    } else {
        drawerBody.innerHTML = state.cart.map(item => `
            <div class="cart-item-row">
                <span class="cart-item-name">${escapeHtml(item)}</span>
                <button class="btn-remove-item" onclick="removeFromCart('${escapeHtml(item)}')">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
        `).join('');

        cartTagsContainer.innerHTML = state.cart.map(item => `
            <span class="cart-chip">
                ${escapeHtml(item.length > 25 ? item.substring(0, 22) + '...' : item)}
                <i class="fa-solid fa-xmark" onclick="removeFromCart('${escapeHtml(item)}')"></i>
            </span>
        `).join('');
    }
}


/* Catalog Fetch & Render */
async function fetchCatalog(search = "") {
    const grid = document.getElementById("productsGrid");
    const countLabel = document.getElementById("productCountLabel");

    try {
        const res = await fetch(`${API_BASE}/api/products?q=${encodeURIComponent(search)}&limit=30`);
        if (res.ok) {
            const data = await res.json();
            state.catalog = data.products.map(p => ({
                product: p,
                tag: getProductTag(p),
                price: getProductPrice(p)
            }));
            countLabel.innerText = `Showing ${data.products.length} of ${data.total} products`;
        } else {
            throw new Error("Failed to fetch products API");
        }
    } catch (e) {
        console.warn("Using demo catalog fallback:", e);
        state.catalog = DEMO_PRODUCTS.filter(p => !search || p.product.toLowerCase().includes(search.toLowerCase()));
        countLabel.innerText = `Showing ${state.catalog.length} items`;
    }

    renderProductsGrid();
}

function renderProductsGrid() {
    const grid = document.getElementById("productsGrid");
    if (!state.catalog || state.catalog.length === 0) {
        grid.innerHTML = `<p style="grid-column: 1/-1; color: var(--text-muted);">No catalog items match your search term.</p>`;
        return;
    }

    grid.innerHTML = state.catalog.map(item => {
        const inCart = state.cart.includes(item.product);
        return `
            <div class="product-card">
                <div class="product-card-body">
                    <span class="product-tag">${escapeHtml(item.tag)}</span>
                    <h3 class="product-title" title="${escapeHtml(item.product)}">${escapeHtml(item.product)}</h3>
                </div>
                <div class="product-card-footer">
                    <span class="product-price">${item.price}</span>
                    <button class="btn-add-cart ${inCart ? 'in-cart' : ''}" data-product="${escapeHtml(item.product)}" onclick="toggleCartProduct('${escapeHtml(item.product)}')">
                        ${inCart ? '<i class="fa-solid fa-check"></i> Added' : '<i class="fa-solid fa-cart-plus"></i> Add to Cart'}
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function toggleCartProduct(productName) {
    if (state.cart.includes(productName)) {
        removeFromCart(productName);
    } else {
        addToCart(productName);
    }
}


/* Search & Presets */
function initSearch() {
    const searchInput = document.getElementById("catalogSearchInput");
    const clearBtn = document.getElementById("searchClearBtn");

    let debounceTimer;
    searchInput.addEventListener("input", (e) => {
        const query = e.target.value;
        clearBtn.style.display = query ? "block" : "none";
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            fetchCatalog(query);
        }, 300);
    });

    clearBtn.addEventListener("click", () => {
        searchInput.value = "";
        clearBtn.style.display = "none";
        fetchCatalog("");
    });
}

function initPresets() {
    document.querySelectorAll(".preset-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const keyword = btn.getAttribute("data-preset");
            if (keyword === "REGENCY") {
                state.cart = ["GREEN REGENCY TEACUP AND SAUCER", "ROSES REGENCY TEACUP AND SAUCER"];
            } else if (keyword === "HEART") {
                state.cart = ["WHITE HANGING HEART T-LIGHT HOLDER"];
            } else if (keyword === "JUMBO BAG") {
                state.cart = ["JUMBO BAG RED RETROSPOT"];
            } else {
                state.cart = ["PARTY BUNTING"];
            }
            updateCartUI();
            triggerRecommendations();
        });
    });
}


/* Live Recommendation Engine API Call */
async function triggerRecommendations() {
    const recList = document.getElementById("recommendationsList");
    const recBadge = document.getElementById("recBadge");

    try {
        const res = await fetch(`${API_BASE}/api/recommend`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cart: state.cart,
                top_n: 5,
                min_confidence: 0.10,
                min_lift: 1.0
            })
        });

        if (res.ok) {
            const recs = await res.json();
            renderRecommendations(recs);
            recBadge.innerText = state.cart.length > 0 ? "Apriori / FPGrowth Rules" : "Popular Fallback Items";
        } else {
            throw new Error("Recommender API failed");
        }
    } catch (e) {
        console.warn("Using offline fallback recommendation logic:", e);
        renderRecommendations(getOfflineFallbackRecommendations());
    }
}

function renderRecommendations(recs) {
    const recList = document.getElementById("recommendationsList");

    if (!recs || recs.length === 0) {
        recList.innerHTML = `<p style="font-size:0.85rem; color: var(--text-muted);">No recommendations available for current basket selection.</p>`;
        return;
    }

    recList.innerHTML = recs.map(r => `
        <div class="rec-item-card">
            <div class="rec-item-top">
                <span class="rec-product-name">${escapeHtml(r.product)}</span>
                <span class="rec-score-pill">Score: ${(r.score * 100).toFixed(0)}%</span>
            </div>
            <div class="rec-meta-row">
                <span class="rec-meta-tag"><i class="fa-solid fa-bullseye"></i> Conf: ${(r.confidence * 100).toFixed(0)}%</span>
                <span class="rec-meta-tag"><i class="fa-solid fa-arrow-up-right-dots"></i> Lift: ${r.lift}x</span>
            </div>
            <div class="rec-item-footer">
                <button class="btn-explain" onclick="explainRule('${escapeHtml(r.product)}', ${r.confidence}, ${r.lift}, ${r.support}, '${escapeHtml(r.rule_description)}')">
                    <i class="fa-solid fa-circle-question"></i> Why recommended?
                </button>
                <button class="btn-add-cart" style="padding: 3px 8px; font-size: 0.75rem;" onclick="addToCart('${escapeHtml(r.product)}')">
                    + Add
                </button>
            </div>
        </div>
    `).join('');
}


/* Analytics & Rules Fetching */
async function fetchAnalytics() {
    try {
        const res = await fetch(`${API_BASE}/api/analytics/summary`);
        if (res.ok) {
            const data = await res.json();
            state.analytics = data;

            document.getElementById("statTransactions").innerText = data.summary.total_transactions.toLocaleString();
            document.getElementById("statProducts").innerText = data.summary.total_unique_products.toLocaleString();
            document.getElementById("statRevenue").innerText = "$" + (data.summary.total_revenue / 1e6).toFixed(2) + "M";
            document.getElementById("statBasketSize").innerText = data.summary.basket_size_stats.mean;
        }
    } catch (e) {
        console.warn("Analytics fetch failed:", e);
    }
}

async function fetchRules(minConf = 0.20, minLift = 1.2) {
    const tableBody = document.getElementById("rulesTableBody");
    try {
        const res = await fetch(`${API_BASE}/api/analytics/rules?min_confidence=${minConf}&min_lift=${minLift}&limit=20`);
        if (res.ok) {
            const data = await res.json();
            state.rules = data.rules;
            renderRulesTable(data.rules);
        }
    } catch (e) {
        console.warn("Rules fetch failed:", e);
    }
}

function renderRulesTable(rules) {
    const tableBody = document.getElementById("rulesTableBody");

    if (!rules || rules.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No rules match selected confidence/lift criteria.</td></tr>`;
        return;
    }

    tableBody.innerHTML = rules.map((r, idx) => `
        <tr>
            <td><strong>#${idx + 1}</strong></td>
            <td>${r.antecedents.map(a => `<span class="itemset-tag">${escapeHtml(a)}</span>`).join(' ')}</td>
            <td style="color: var(--accent-cyan); font-size: 1.1rem;"><i class="fa-solid fa-arrow-right-long"></i></td>
            <td>${r.consequents.map(c => `<span class="itemset-tag consequent-tag">${escapeHtml(c)}</span>`).join(' ')}</td>
            <td>${(r.support * 100).toFixed(2)}%</td>
            <td>${(r.confidence * 100).toFixed(1)}%</td>
            <td><strong>${r.lift}x</strong></td>
            <td><span class="rec-score-pill">${r.score}</span></td>
        </tr>
    `).join('');
}

function initRulesFilters() {
    const btn = document.getElementById("btnFilterRules");
    if (btn) {
        btn.addEventListener("click", () => {
            const conf = parseFloat(document.getElementById("rulesMinConfidence").value) || 0.20;
            const lift = parseFloat(document.getElementById("rulesMinLift").value) || 1.2;
            fetchRules(conf, lift);
        });
    }
}

async function fetchEvaluation() {
    try {
        const res = await fetch(`${API_BASE}/api/evaluate`);
        if (res.ok) {
            const data = await res.json();
            state.evaluation = data;
            
            if (data.holdout_evaluation && data.holdout_evaluation.hit_rate_top5) {
                document.getElementById("evalHitRate").innerText = (data.holdout_evaluation.hit_rate_top5 * 100).toFixed(1) + "%";
                document.getElementById("evalPrecision").innerText = (data.holdout_evaluation.mean_precision_top5 * 100).toFixed(1) + "%";
            }
            if (data.rule_quality) {
                document.getElementById("evalCoverage").innerText = data.rule_quality.catalog_coverage_pct + "%";
                document.getElementById("evalAvgLift").innerText = data.rule_quality.avg_lift + "x";
            }
        }
    } catch (e) {
        console.warn("Evaluation fetch failed:", e);
    }
}


/* Helper Functions & Modals */
function explainRule(product, conf, lift, support, desc) {
    const modal = document.getElementById("ruleModalOverlay");
    const body = document.getElementById("modalBody");

    body.innerHTML = `
        <h4 style="font-size: 1.1rem; color: #fff; margin-bottom: 0.75rem;">${escapeHtml(product)}</h4>
        <p style="color: var(--text-muted); margin-bottom: 1.25rem; font-size: 0.9rem;">${escapeHtml(desc)}</p>
        
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1.25rem;">
            <div style="background: rgba(15,23,42,0.8); padding: 0.85rem; border-radius: 8px; text-align: center;">
                <span style="font-size: 0.75rem; color: var(--text-dim); display: block;">CONFIDENCE</span>
                <strong style="font-size: 1.2rem; color: var(--accent-cyan);">${(conf * 100).toFixed(1)}%</strong>
            </div>
            <div style="background: rgba(15,23,42,0.8); padding: 0.85rem; border-radius: 8px; text-align: center;">
                <span style="font-size: 0.75rem; color: var(--text-dim); display: block;">LIFT RATIO</span>
                <strong style="font-size: 1.2rem; color: var(--accent-emerald);">${lift}x</strong>
            </div>
            <div style="background: rgba(15,23,42,0.8); padding: 0.85rem; border-radius: 8px; text-align: center;">
                <span style="font-size: 0.75rem; color: var(--text-dim); display: block;">SUPPORT</span>
                <strong style="font-size: 1.2rem; color: var(--accent-amber);">${(support * 100).toFixed(2)}%</strong>
            </div>
        </div>

        <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5;">
            <strong>Interpretation:</strong> Customers purchasing items in your cart are <strong>${lift}x</strong> more likely to add this item compared to an average store customer, with a <strong>${(conf * 100).toFixed(1)}%</strong> conditional rule probability.
        </p>
    `;

    modal.classList.add("active");

    const closeBtn = document.getElementById("closeModalBtn");
    closeBtn.onclick = () => modal.classList.remove("active");
    modal.onclick = (e) => {
        if (e.target === modal) modal.classList.remove("active");
    };
}

function getProductTag(name) {
    if (name.includes("TEACUP") || name.includes("CAKE") || name.includes("MUG")) return "Kitchenware";
    if (name.includes("BAG") || name.includes("SHOPPER")) return "Bags & Storage";
    if (name.includes("HEART") || name.includes("FRAME") || name.includes("CLOCK")) return "Home Decor";
    if (name.includes("BUNTING") || name.includes("PARTY")) return "Party & Events";
    return "Store Item";
}

function getProductPrice(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    const price = (Math.abs(hash) % 25) + 3.99;
    return "$" + price.toFixed(2);
}

function getOfflineFallbackRecommendations() {
    return [
        { product: "PINK REGENCY TEACUP AND SAUCER", confidence: 0.70, lift: 18.79, support: 0.026, score: 0.95, is_fallback: false, rule_description: "Frequently bought with Regency Teacup set" },
        { product: "REGENCY CAKESTAND 3 TIER", confidence: 0.23, lift: 2.3, support: 0.009, score: 0.55, is_fallback: false, rule_description: "Frequently bought with Regency Teacup set" },
        { product: "WHITE HANGING HEART T-LIGHT HOLDER", confidence: 0.25, lift: 1.0, support: 0.11, score: 0.30, is_fallback: true, rule_description: "Popular Storefront Product" }
    ];
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
