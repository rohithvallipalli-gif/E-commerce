/**
 * NexusCart E-Commerce Market Basket Recommender Frontend Logic
 */

const API_BASE = window.location.origin.includes("http") ? window.location.origin : "http://localhost:8000";

// App State
const state = {
    token: localStorage.getItem("nexuscart_jwt") || null,
    user: JSON.parse(localStorage.getItem("nexuscart_user") || "null"),
    cart: [],
    catalog: [],
    categories: [],
    selectedCategory: "All",
    searchQuery: "",
    sortMode: "name_asc",
    rules: [],
    analytics: null,
    evaluation: null,
    adminProducts: [],
    adminUsers: [],
    adminOrders: [],
    userOrders: []
};

// Chart.js instances cache
let chartInstances = {};
let rulesAbortController = null;

// ==================== Initialization ====================
document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initCartDrawer();
    initSearch();
    initPresets();
    initRulesFilters();

    if (state.token && state.user) {
        initAuthenticatedApp();
    } else {
        showAuthView();
    }
});

/* Authenticated Fetch Wrapper */
async function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (state.token) {
        options.headers["Authorization"] = `Bearer ${state.token}`;
    }
    const res = await fetch(url, options);
    if (res.status === 401) {
        console.warn("Session expired or unauthorized (401). Redirecting to login...");
        handleLogout();
    }
    return res;
}

// ==================== Authentication Logic ====================

function switchAuthTab(tab) {
    const loginForm = document.getElementById("loginForm");
    const regForm = document.getElementById("registerForm");
    const tabLogin = document.getElementById("tabBtnLogin");
    const tabReg = document.getElementById("tabBtnRegister");
    const alertBox = document.getElementById("authAlert");
    alertBox.style.display = "none";

    if (tab === "login") {
        loginForm.style.display = "block";
        regForm.style.display = "none";
        tabLogin.classList.add("active");
        tabReg.classList.remove("active");
    } else {
        loginForm.style.display = "none";
        regForm.style.display = "block";
        tabLogin.classList.remove("active");
        tabReg.classList.add("active");
    }
}

function togglePasswordVisibility(fieldId, btn) {
    const input = document.getElementById(fieldId);
    if (!input) return;
    if (input.type === "password") {
        input.type = "text";
        btn.innerHTML = `<i class="fa-solid fa-eye-slash"></i>`;
    } else {
        input.type = "password";
        btn.innerHTML = `<i class="fa-solid fa-eye"></i>`;
    }
}

function fillQuickLogin(email, password) {
    switchAuthTab("login");
    document.getElementById("loginEmail").value = email;
    document.getElementById("loginPassword").value = password;
    const form = document.getElementById("loginForm");
    if (form) form.requestSubmit();
}

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;
    const btn = document.getElementById("btnLoginSubmit");
    const alertBox = document.getElementById("authAlert");

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Signing in...`;
    alertBox.style.display = "none";

    try {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();

        if (res.ok) {
            state.token = data.access_token;
            state.user = data.user;
            localStorage.setItem("nexuscart_jwt", data.access_token);
            localStorage.setItem("nexuscart_user", JSON.stringify(data.user));

            showToast(`Welcome back, ${data.user.name}!`, "success");
            initAuthenticatedApp();
        } else {
            throw new Error(data.detail || "Authentication failed.");
        }
    } catch (err) {
        alertBox.className = "auth-alert error";
        alertBox.innerText = err.message;
        alertBox.style.display = "block";
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Sign In</span> <i class="fa-solid fa-arrow-right"></i>`;
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const name = document.getElementById("regName").value.trim();
    const email = document.getElementById("regEmail").value.trim();
    const password = document.getElementById("regPassword").value;
    const btn = document.getElementById("btnRegSubmit");
    const alertBox = document.getElementById("authAlert");

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Creating account...`;
    alertBox.style.display = "none";

    try {
        const res = await fetch(`${API_BASE}/api/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, email, password })
        });
        const data = await res.json();

        if (res.ok) {
            state.token = data.access_token;
            state.user = data.user;
            localStorage.setItem("nexuscart_jwt", data.access_token);
            localStorage.setItem("nexuscart_user", JSON.stringify(data.user));

            showToast(`Account created successfully! Welcome, ${data.user.name}.`, "success");
            initAuthenticatedApp();
        } else {
            throw new Error(data.detail || "Registration failed.");
        }
    } catch (err) {
        alertBox.className = "auth-alert error";
        alertBox.innerText = err.message;
        alertBox.style.display = "block";
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Create Free Account</span> <i class="fa-solid fa-user-plus"></i>`;
    }
}

function handleLogout() {
    state.token = null;
    state.user = null;
    state.cart = [];
    localStorage.removeItem("nexuscart_jwt");
    localStorage.removeItem("nexuscart_user");
    showToast("You have been signed out.", "info");
    showAuthView();
}

function showAuthView() {
    document.getElementById("authSection").style.display = "flex";
    document.getElementById("mainAppContainer").style.display = "none";
    document.getElementById("userHeaderPill").style.display = "none";
    document.getElementById("btnLogout").style.display = "none";
    document.getElementById("cartToggleBtn").style.display = "none";

    // Hide admin tabs in nav
    document.querySelectorAll(".admin-only").forEach(el => el.style.display = "none");
    const navMyOrders = document.getElementById("navMyOrdersBtn");
    if (navMyOrders) navMyOrders.style.display = "none";
}

function initAuthenticatedApp() {
    document.getElementById("authSection").style.display = "none";
    document.getElementById("mainAppContainer").style.display = "block";
    document.getElementById("userHeaderPill").style.display = "flex";
    document.getElementById("btnLogout").style.display = "flex";
    document.getElementById("cartToggleBtn").style.display = "flex";

    // Update Header Profile Badge
    document.getElementById("headerUserName").innerText = state.user.name.split(" ")[0];
    const roleBadge = document.getElementById("headerUserRole");
    roleBadge.innerText = state.user.role.toUpperCase();
    roleBadge.className = `role-badge ${state.user.role}`;

    const isAdmin = state.user.role === "admin";

    // Show/hide role-based navigation tabs
    document.querySelectorAll(".admin-only").forEach(el => {
        el.style.display = isAdmin ? "inline-flex" : "none";
    });
    const navMyOrders = document.getElementById("navMyOrdersBtn");
    if (navMyOrders) navMyOrders.style.display = "inline-flex";

    document.getElementById("btnLogout").onclick = handleLogout;

    // Load storefront catalog
    fetchCatalog();
    updateCartUI();

    // Reset view to storefront tab
    switchTab("storefront-tab");

    // Preload analytics/evaluation if admin
    if (isAdmin) {
        fetchAnalytics();
        fetchRules();
        fetchEvaluation();
    }
}

// ==================== Navigation Tabs ====================

function initNavigation() {
    const navButtons = document.querySelectorAll(".nav-btn");
    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            switchTab(targetTab);
        });
    });
}

function switchTab(tabId) {
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    navButtons.forEach(b => {
        if (b.getAttribute("data-tab") === tabId) b.classList.add("active");
        else b.classList.remove("active");
    });

    tabContents.forEach(c => {
        if (c.id === tabId) c.classList.add("active");
        else c.classList.remove("active");
    });

    // Lazy load/update content when switching tabs
    if (tabId === "analytics-tab") {
        if (!state.analytics) fetchAnalytics();
        else renderAnalyticsCharts();
    } else if (tabId === "rules-tab") {
        if (!state.rules || state.rules.length === 0) fetchRules();
    } else if (tabId === "evaluation-tab") {
        if (!state.evaluation) fetchEvaluation();
    } else if (tabId === "orders-tab") {
        fetchUserOrders();
    } else if (tabId === "admin-products-tab") {
        fetchAdminProducts();
    } else if (tabId === "admin-users-tab") {
        fetchAdminUsers();
    } else if (tabId === "admin-orders-tab") {
        fetchAdminOrders();
    }
}

// ==================== Storefront Catalog & Filters ====================

async function fetchCatalog(search = state.searchQuery, category = state.selectedCategory, sort = state.sortMode) {
    const grid = document.getElementById("productsGrid");
    const countLabel = document.getElementById("productCountLabel");

    try {
        let url = `${API_BASE}/api/products?limit=100`;
        if (search && search.trim()) url += `&q=${encodeURIComponent(search.trim())}`;
        if (category && category !== "All") url += `&category=${encodeURIComponent(category)}`;
        if (sort) url += `&sort=${encodeURIComponent(sort)}`;

        const res = await authFetch(url);
        if (res.ok) {
            const data = await res.json();
            state.catalog = data.products || [];
            countLabel.innerText = `Showing ${state.catalog.length} of ${data.total} products`;
            renderProductsGrid();
        } else {
            throw new Error(`Catalog fetch failed with status ${res.status}`);
        }
    } catch (e) {
        console.warn("Catalog fetch error:", e);
        grid.innerHTML = `<p style="grid-column: 1/-1; color: #f43f5e; padding: 1.5rem;">Failed to load catalog products. Check server connection.</p>`;
    }
}

function renderProductsGrid() {
    const grid = document.getElementById("productsGrid");
    if (!state.catalog || state.catalog.length === 0) {
        grid.innerHTML = `<p style="grid-column: 1/-1; color: var(--text-muted); padding: 2rem 0;">No products match your current search or category filter.</p>`;
        return;
    }

    grid.innerHTML = state.catalog.map(item => {
        const inCart = state.cart.some(c => c.product === item.product);
        const emoji = item.emoji || "📦";
        const price = typeof item.price === "number" ? `$${item.price.toFixed(2)}` : `$${item.price}`;

        return `
            <div class="product-card">
                <div>
                    <div class="product-card-top-line">
                        <span class="product-emoji-icon">${emoji}</span>
                        <span class="product-stock-code">SKU: ${escapeHtml(item.stock_code || 'N/A')}</span>
                    </div>
                    <span class="product-tag">${escapeHtml(item.category)}</span>
                    <h3 class="product-title" title="${escapeHtml(item.product)}">${escapeHtml(item.product)}</h3>
                    <p class="product-desc-text">${escapeHtml(item.description || '')}</p>
                </div>
                <div class="product-card-footer">
                    <span class="product-price">${price}</span>
                    <button class="btn-add-cart ${inCart ? 'in-cart' : ''}" onclick="toggleCartItem('${escapeHtml(item.product)}', ${item.price}, '${escapeHtml(emoji)}')">
                        ${inCart ? '<i class="fa-solid fa-check"></i> Added' : '<i class="fa-solid fa-cart-plus"></i> Add to Cart'}
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function filterByCategory(cat) {
    state.selectedCategory = cat;
    document.querySelectorAll(".cat-chip").forEach(btn => {
        if (btn.getAttribute("data-category") === cat) btn.classList.add("active");
        else btn.classList.remove("active");
    });
    fetchCatalog();
}

function handleSortChange(sortVal) {
    state.sortMode = sortVal;
    fetchCatalog();
}

function initSearch() {
    const searchInput = document.getElementById("catalogSearchInput");
    const clearBtn = document.getElementById("searchClearBtn");

    let debounceTimer;
    searchInput.addEventListener("input", (e) => {
        const query = e.target.value;
        clearBtn.style.display = query ? "block" : "none";
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            state.searchQuery = query;
            fetchCatalog();
        }, 300);
    });

    clearBtn.addEventListener("click", () => {
        searchInput.value = "";
        clearBtn.style.display = "none";
        state.searchQuery = "";
        fetchCatalog();
    });
}

function initPresets() {
    document.querySelectorAll(".preset-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const presetKey = btn.getAttribute("data-preset");
            if (presetKey === "REGENCY") {
                setCartItems([
                    { product: "GREEN REGENCY TEACUP AND SAUCER", price: 12.50, emoji: "☕" },
                    { product: "ROSES REGENCY TEACUP AND SAUCER", price: 12.50, emoji: "☕" }
                ]);
            } else if (presetKey === "HEART") {
                setCartItems([
                    { product: "WHITE HANGING HEART T-LIGHT HOLDER", price: 4.99, emoji: "🏠" },
                    { product: "HEART OF WICKER SMALL", price: 3.99, emoji: "🏠" }
                ]);
            } else if (presetKey === "JUMBO BAG") {
                setCartItems([
                    { product: "JUMBO BAG RED RETROSPOT", price: 6.99, emoji: "👜" },
                    { product: "JUMBO BAG PINK POLKADOT", price: 6.99, emoji: "👜" }
                ]);
            } else if (presetKey === "PANTRY") {
                setCartItems([
                    { product: "SET OF 3 CAKE TINS PANTRY DESIGN", price: 15.99, emoji: "☕" },
                    { product: "PARTY BUNTING", price: 8.50, emoji: "🎉" }
                ]);
            }
        });
    });
}

function setCartItems(items) {
    state.cart = items.map(i => ({ ...i, quantity: 1 }));
    updateCartUI();
    triggerRecommendations();
    showToast("Quick Try Cart loaded!", "info");
}

// ==================== Cart & Recommendations Logic ====================

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
        showToast("Cart cleared", "info");
    });
}

function toggleCartItem(productName, price = 4.99, emoji = "📦") {
    const idx = state.cart.findIndex(c => c.product === productName);
    if (idx >= 0) {
        state.cart.splice(idx, 1);
        showToast(`Removed "${truncateText(productName, 25)}" from cart`, "info");
    } else {
        state.cart.push({ product: productName, price: parseFloat(price) || 4.99, quantity: 1, emoji });
        showToast(`Added "${truncateText(productName, 25)}" to cart`, "success");
    }
    updateCartUI();
    triggerRecommendations();
}

function addProductToCart(productName, price = 4.99, emoji = "📦") {
    const existing = state.cart.find(c => c.product === productName);
    if (existing) {
        existing.quantity += 1;
    } else {
        state.cart.push({ product: productName, price: parseFloat(price) || 4.99, quantity: 1, emoji });
    }
    updateCartUI();
    triggerRecommendations();
    showToast(`Added "${truncateText(productName, 25)}" to cart`, "success");
}

function updateCartQuantity(productName, delta) {
    const item = state.cart.find(c => c.product === productName);
    if (!item) return;
    item.quantity += delta;
    if (item.quantity <= 0) {
        state.cart = state.cart.filter(c => c.product !== productName);
    }
    updateCartUI();
    triggerRecommendations();
}

function updateCartUI() {
    const badge = document.getElementById("cartCountBadge");
    const drawerBody = document.getElementById("cartDrawerBody");
    const drawerItemCount = document.getElementById("cartDrawerItemCount");
    const drawerSubtotal = document.getElementById("cartDrawerSubtotal");
    const cartTagsContainer = document.getElementById("cartTagsContainer");

    const totalItems = state.cart.reduce((sum, item) => sum + item.quantity, 0);
    const subtotal = state.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);

    badge.innerText = totalItems;
    drawerItemCount.innerText = totalItems;
    drawerSubtotal.innerText = `$${subtotal.toFixed(2)}`;

    // Re-render buttons in products grid
    renderProductsGrid();

    // Update Drawer Body
    if (state.cart.length === 0) {
        drawerBody.innerHTML = `
            <div class="empty-cart-state">
                <i class="fa-solid fa-cart-flatbed-suitcase"></i>
                <p>Your shopping cart is empty.</p>
            </div>
        `;
        cartTagsContainer.innerHTML = `<span class="empty-cart-text">Cart is empty. Add products to trigger recommendations!</span>`;
    } else {
        drawerBody.innerHTML = state.cart.map(item => `
            <div class="cart-item-row">
                <div class="cart-item-info">
                    <span class="cart-item-name" title="${escapeHtml(item.product)}">${escapeHtml(item.product)}</span>
                    <span class="cart-item-unit-price">$${item.price.toFixed(2)} each</span>
                </div>
                <div class="cart-qty-controls">
                    <button class="cart-qty-btn" onclick="updateCartQuantity('${escapeHtml(item.product)}', -1)">-</button>
                    <span class="cart-qty-val">${item.quantity}</span>
                    <button class="cart-qty-btn" onclick="updateCartQuantity('${escapeHtml(item.product)}', 1)">+</button>
                </div>
                <button class="btn-remove-item" onclick="toggleCartItem('${escapeHtml(item.product)}')">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
        `).join('');

        cartTagsContainer.innerHTML = state.cart.map(item => `
            <span class="cart-chip">
                ${escapeHtml(item.product.length > 22 ? item.product.substring(0, 20) + '...' : item.product)}
                <i class="fa-solid fa-xmark" onclick="toggleCartItem('${escapeHtml(item.product)}')"></i>
            </span>
        `).join('');
    }
}

async function triggerRecommendations() {
    const recList = document.getElementById("recommendationsList");
    const recBadge = document.getElementById("recBadge");

    // If cart is empty, do NOT call recommender API; show clear empty state
    if (state.cart.length === 0) {
        recBadge.innerText = "Active Engine";
        recList.innerHTML = `
            <div style="text-align: center; padding: 2rem 1rem; color: var(--text-muted);">
                <i class="fa-solid fa-wand-magic-sparkles" style="font-size: 1.8rem; color: var(--accent-cyan); margin-bottom: 0.75rem; display: block;"></i>
                <p style="font-size: 0.9rem; margin-bottom: 0.4rem; color: #fff;">Add products to see recommendations</p>
                <p style="font-size: 0.8rem; color: var(--text-dim);">Live Apriori/FPGrowth co-occurrence rules activate as soon as you add an item to your cart.</p>
            </div>
        `;
        return;
    }

    try {
        const cartProductNames = state.cart.map(c => c.product);
        const res = await authFetch(`${API_BASE}/api/recommend`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cart: cartProductNames,
                top_n: 6,
                min_confidence: 0.05,
                min_lift: 1.0
            })
        });

        if (res.ok) {
            const recs = await res.json();
            renderRecommendations(recs);
            recBadge.innerText = recs.some(r => !r.is_fallback) ? "Rule Affinity Mined" : "Popular Complement";
        } else {
            throw new Error(`Recommender error ${res.status}`);
        }
    } catch (e) {
        console.warn("Recommender fetch error:", e);
        recList.innerHTML = `<p style="font-size:0.85rem; color: #f43f5e; padding: 1rem;">Failed to retrieve recommendations.</p>`;
    }
}

function renderRecommendations(recs) {
    const recList = document.getElementById("recommendationsList");
    if (!recs || recs.length === 0) {
        recList.innerHTML = `<p style="font-size:0.85rem; color: var(--text-muted); padding: 1rem;">No strong co-purchase affinity matches found for current basket.</p>`;
        return;
    }

    recList.innerHTML = recs.map(r => `
        <div class="rec-item-card">
            <div class="rec-item-top">
                <span class="rec-product-name" title="${escapeHtml(r.product)}">${escapeHtml(r.product)}</span>
                <span class="rec-score-pill">Score: ${(r.score * 100).toFixed(0)}%</span>
            </div>
            <div class="rec-meta-row">
                <span class="rec-meta-tag"><i class="fa-solid fa-bullseye"></i> Conf: ${(r.confidence * 100).toFixed(0)}%</span>
                <span class="rec-meta-tag"><i class="fa-solid fa-arrow-up-right-dots"></i> Lift: ${r.lift}x</span>
            </div>
            <div class="rec-item-footer">
                <button class="btn-explain" onclick='explainRecommendation(${JSON.stringify(r)})'>
                    <i class="fa-solid fa-circle-question"></i> Why recommended?
                </button>
                <button class="btn-add-cart" style="padding: 4px 10px; font-size: 0.78rem;" onclick="addProductToCart('${escapeHtml(r.product)}')">
                    + Add
                </button>
            </div>
        </div>
    `).join('');
}

function explainRecommendation(r) {
    const modal = document.getElementById("ruleModalOverlay");
    const body = document.getElementById("modalBody");
    const matched = r.matched_antecedents && r.matched_antecedents.length > 0 
        ? r.matched_antecedents.map(m => `<span class="cart-chip" style="margin-right: 4px;">${escapeHtml(m)}</span>`).join('')
        : "Storefront Popularity Pattern";

    body.innerHTML = `
        <h4 style="font-size: 1.1rem; color: #fff; margin-bottom: 0.5rem;">${escapeHtml(r.product)}</h4>
        <div style="margin-bottom: 1.25rem;">
            <span style="font-size: 0.8rem; color: var(--text-dim); display: block; margin-bottom: 0.3rem;">TRIGGERED BY CART ITEMS:</span>
            <div>${matched}</div>
        </div>
        
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-bottom: 1.25rem;">
            <div style="background: rgba(15,23,42,0.8); padding: 0.85rem; border-radius: 8px; text-align: center; border: 1px solid var(--border-color);">
                <span style="font-size: 0.72rem; color: var(--text-dim); display: block;">CONFIDENCE</span>
                <strong style="font-size: 1.2rem; color: var(--accent-cyan);">${(r.confidence * 100).toFixed(1)}%</strong>
            </div>
            <div style="background: rgba(15,23,42,0.8); padding: 0.85rem; border-radius: 8px; text-align: center; border: 1px solid var(--border-color);">
                <span style="font-size: 0.72rem; color: var(--text-dim); display: block;">LIFT RATIO</span>
                <strong style="font-size: 1.2rem; color: var(--accent-emerald);">${r.lift}x</strong>
            </div>
            <div style="background: rgba(15,23,42,0.8); padding: 0.85rem; border-radius: 8px; text-align: center; border: 1px solid var(--border-color);">
                <span style="font-size: 0.72rem; color: var(--text-dim); display: block;">SUPPORT</span>
                <strong style="font-size: 1.2rem; color: var(--accent-amber);">${(r.support * 100).toFixed(2)}%</strong>
            </div>
        </div>

        <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5; background: rgba(15,23,42,0.5); padding: 0.85rem; border-radius: 8px;">
            <strong>Affinity Analysis:</strong> ${escapeHtml(r.rule_description)}. Customers purchasing items in your cart are <strong>${r.lift}x</strong> more likely to buy this product compared to independent store baseline.
        </p>
    `;
    modal.classList.add("active");
}

async function handleCheckout() {
    if (state.cart.length === 0) {
        showToast("Your cart is empty.", "error");
        return;
    }

    const btn = document.getElementById("btnCheckout");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Placing Order...`;

    try {
        const subtotal = state.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        const orderPayload = {
            items: state.cart.map(c => ({ product: c.product, quantity: c.quantity, price: c.price })),
            total: subtotal
        };

        const res = await authFetch(`${API_BASE}/api/orders`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(orderPayload)
        });

        if (res.ok) {
            const data = await res.json();
            state.cart = [];
            updateCartUI();
            triggerRecommendations();
            closeCart();
            showToast(`Order #${data.order.id} placed successfully! Total: $${subtotal.toFixed(2)}`, "success");
            switchTab("orders-tab");
        } else {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Checkout failed");
        }
    } catch (e) {
        showToast(e.message || "Failed to place order.", "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-credit-card"></i> Checkout`;
    }
}

function closeCart() {
    document.getElementById("cartOverlay").classList.remove("active");
    document.getElementById("cartDrawer").classList.remove("active");
}

// ==================== User Orders Tab ====================

async function fetchUserOrders() {
    const container = document.getElementById("userOrdersContainer");
    container.innerHTML = `<div class="loading-state-card glass-card"><i class="fa-solid fa-spinner fa-spin"></i> Loading your past orders...</div>`;

    try {
        const res = await authFetch(`${API_BASE}/api/orders/me`);
        if (res.ok) {
            const orders = await res.json();
            state.userOrders = orders;
            renderUserOrders(orders);
        } else {
            throw new Error("Could not fetch orders.");
        }
    } catch (e) {
        container.innerHTML = `<div class="auth-alert error">Failed to load order history: ${escapeHtml(e.message)}</div>`;
    }
}

function renderUserOrders(orders) {
    const container = document.getElementById("userOrdersContainer");
    if (!orders || orders.length === 0) {
        container.innerHTML = `
            <div class="glass-card" style="grid-column: 1/-1; text-align: center; padding: 3rem 1rem;">
                <i class="fa-solid fa-receipt" style="font-size: 2.5rem; color: var(--text-dim); margin-bottom: 1rem; display: block;"></i>
                <h3 style="color: #fff; margin-bottom: 0.5rem;">No Orders Yet</h3>
                <p style="color: var(--text-muted); font-size: 0.9rem;">Browse the catalog, add products to your cart, and complete checkout to see your transaction history.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = orders.map(o => `
        <div class="order-receipt-card glass-card">
            <div class="order-head">
                <div>
                    <strong style="color: #fff; font-size: 1rem;">Order #${o.id}</strong>
                    <span style="display: block; font-size: 0.75rem; color: var(--text-dim);">${new Date(o.created_at).toLocaleString()}</span>
                </div>
                <div style="text-align: right;">
                    <strong style="color: var(--accent-emerald); font-size: 1.1rem;">$${parseFloat(o.total).toFixed(2)}</strong>
                    <span class="status-badge active" style="display: block; margin-top: 4px;">Completed</span>
                </div>
            </div>
            <div style="margin-top: 0.75rem;">
                <span style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Items in Basket (${o.items ? o.items.length : 0}):</span>
                <ul style="list-style: none; margin-top: 0.4rem; padding: 0;">
                    ${(o.items || []).map(i => `
                        <li style="display: flex; justify-content: space-between; font-size: 0.82rem; padding: 3px 0; color: var(--text-main);">
                            <span>${i.quantity}x ${escapeHtml(i.product)}</span>
                            <span style="color: var(--text-muted);">$${(i.price * i.quantity).toFixed(2)}</span>
                        </li>
                    `).join('')}
                </ul>
            </div>
        </div>
    `).join('');
}

// ==================== Dataset Analytics (Chart.js) ====================

async function fetchAnalytics() {
    try {
        const res = await authFetch(`${API_BASE}/api/analytics/summary`);
        if (res.ok) {
            const data = await res.json();
            state.analytics = data;

            document.getElementById("statTransactions").innerText = data.summary.total_transactions.toLocaleString();
            document.getElementById("statProducts").innerText = data.summary.total_unique_products.toLocaleString();
            document.getElementById("statRevenue").innerText = "$" + (data.summary.total_revenue / 1e6).toFixed(2) + "M";
            document.getElementById("statBasketSize").innerText = data.summary.basket_size_stats.mean;

            const analyticsTab = document.getElementById("analytics-tab");
            if (analyticsTab && analyticsTab.classList.contains("active")) {
                renderAnalyticsCharts();
            }
        }
    } catch (e) {
        console.warn("Analytics fetch failed:", e);
    }
}

function renderAnalyticsCharts() {
    if (!state.analytics) return;
    const { top_frequent_products, top_revenue_products, basket_size_histogram, top_countries } = state.analytics;

    const textColor = "#94a3b8";
    const gridColor = "rgba(255, 255, 255, 0.07)";

    // 1. Top Frequent Products Chart
    const ctxFreq = document.getElementById("chartFrequentProducts");
    if (ctxFreq && top_frequent_products && top_frequent_products.length > 0) {
        if (chartInstances.frequent) chartInstances.frequent.destroy();
        const fullLabels = top_frequent_products.map(p => p.product);
        const displayLabels = fullLabels.map(p => truncateText(p, 20));
        const counts = top_frequent_products.map(p => p.count);

        chartInstances.frequent = new Chart(ctxFreq, {
            type: "bar",
            data: {
                labels: displayLabels,
                datasets: [{
                    label: "Orders Count",
                    data: counts,
                    backgroundColor: "rgba(99, 102, 241, 0.75)",
                    borderColor: "#6366f1",
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: (items) => fullLabels[items[0].dataIndex],
                            label: (item) => `Orders: ${item.raw.toLocaleString()}`
                        }
                    }
                },
                scales: {
                    x: { ticks: { color: textColor }, grid: { color: gridColor } },
                    y: { ticks: { color: textColor }, grid: { display: false } }
                }
            }
        });
    }

    // 2. Basket Size Distribution Chart
    const ctxDist = document.getElementById("chartBasketDistribution");
    const histData = basket_size_histogram || (state.analytics.summary && state.analytics.summary.basket_size_histogram);
    if (ctxDist && histData && histData.length > 0) {
        if (chartInstances.distribution) chartInstances.distribution.destroy();
        const labels = histData.map(h => h.bucket + (h.bucket === "50+" ? " items" : " items"));
        const counts = histData.map(h => h.count);

        chartInstances.distribution = new Chart(ctxDist, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Transactions",
                    data: counts,
                    backgroundColor: "rgba(6, 182, 212, 0.75)",
                    borderColor: "#06b6d4",
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (item) => `Transactions: ${item.raw.toLocaleString()}`
                        }
                    }
                },
                scales: {
                    x: { title: { display: true, text: "Basket Size (Items/Cart)", color: textColor }, ticks: { color: textColor }, grid: { display: false } },
                    y: { ticks: { color: textColor }, grid: { color: gridColor } }
                }
            }
        });
    }

    // 3. Top Revenue Generating Products Chart
    const ctxRev = document.getElementById("chartRevenueProducts");
    if (ctxRev && top_revenue_products && top_revenue_products.length > 0) {
        if (chartInstances.revenue) chartInstances.revenue.destroy();
        const fullLabels = top_revenue_products.map(p => p.product);
        const displayLabels = fullLabels.map(p => truncateText(p, 20));
        const revenues = top_revenue_products.map(p => p.total_revenue);

        chartInstances.revenue = new Chart(ctxRev, {
            type: "bar",
            data: {
                labels: displayLabels,
                datasets: [{
                    label: "Revenue ($)",
                    data: revenues,
                    backgroundColor: "rgba(16, 185, 129, 0.75)",
                    borderColor: "#10b981",
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: (items) => fullLabels[items[0].dataIndex],
                            label: (item) => `Revenue: $${item.raw.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: textColor,
                            callback: (val) => "$" + (val >= 1000 ? (val / 1000).toFixed(0) + "k" : val)
                        },
                        grid: { color: gridColor }
                    },
                    y: { ticks: { color: textColor }, grid: { display: false } }
                }
            }
        });
    }

    // 4. Top Countries Chart
    const ctxCountries = document.getElementById("chartCountries");
    if (ctxCountries && top_countries && top_countries.length > 0) {
        if (chartInstances.countries) chartInstances.countries.destroy();
        const labels = top_countries.map(c => c.country);
        const counts = top_countries.map(c => c.transactions);

        chartInstances.countries = new Chart(ctxCountries, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Transactions",
                    data: counts,
                    backgroundColor: "rgba(245, 158, 11, 0.75)",
                    borderColor: "#f59e0b",
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (item) => `Transactions: ${item.raw.toLocaleString()}`
                        }
                    }
                },
                scales: {
                    x: { ticks: { color: textColor }, grid: { color: gridColor } },
                    y: { ticks: { color: textColor }, grid: { display: false } }
                }
            }
        });
    }
}

// ==================== Association Rules Tab ====================

async function fetchRules(minConf = 0.20, minLift = 1.2) {
    const tableBody = document.getElementById("rulesTableBody");
    if (!tableBody) return;

    tableBody.innerHTML = `<tr><td colspan="7" class="loading-cell"><i class="fa-solid fa-spinner fa-spin"></i> Loading mined association rules...</td></tr>`;

    if (rulesAbortController) {
        rulesAbortController.abort();
    }
    rulesAbortController = new AbortController();
    const timeoutId = setTimeout(() => {
        if (rulesAbortController) rulesAbortController.abort();
    }, 15000);

    try {
        const res = await authFetch(`${API_BASE}/api/analytics/rules?min_confidence=${minConf}&min_lift=${minLift}&limit=50`, {
            signal: rulesAbortController.signal
        });
        clearTimeout(timeoutId);

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `Server error (${res.status})`);
        }

        const data = await res.json();
        state.rules = data.rules || [];
        renderRulesTable(data.rules || []);
    } catch (e) {
        clearTimeout(timeoutId);
        console.warn("Rules fetch failed:", e);
        const isTimeout = e.name === "AbortError";
        const errorMsg = isTimeout ? "Request timed out after 15 seconds." : (e.message || "Failed to load association rules.");
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; color: #f43f5e; padding: 1.5rem; background: rgba(244, 63, 94, 0.08);">
                    <i class="fa-solid fa-circle-exclamation" style="margin-right: 8px;"></i>
                    <strong>Error:</strong> ${escapeHtml(errorMsg)}
                    <button id="btnRetryRules" onclick="fetchRules(${minConf}, ${minLift})" style="margin-left: 14px; padding: 5px 14px; background: rgba(244,63,94,0.25); border: 1px solid #f43f5e; color: #fff; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 500;">
                        <i class="fa-solid fa-rotate-right"></i> Retry
                    </button>
                </td>
            </tr>
        `;
    }
}

function renderRulesTable(rules) {
    const tableBody = document.getElementById("rulesTableBody");
    if (!tableBody) return;

    if (!rules || rules.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No rules match these filters.</td></tr>`;
        return;
    }

    tableBody.innerHTML = rules.map((r, idx) => `
        <tr>
            <td><strong>#${idx + 1}</strong></td>
            <td>${r.antecedents.map(a => `<span class="itemset-tag">${escapeHtml(a)}</span>`).join(' ')}</td>
            <td><i class="fa-solid fa-arrow-right" style="color: var(--accent-cyan); margin-right: 6px;"></i>${r.consequents.map(c => `<span class="itemset-tag consequent-tag">${escapeHtml(c)}</span>`).join(' ')}</td>
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

// ==================== Model Accuracy Tab ====================

async function fetchEvaluation() {
    try {
        const res = await authFetch(`${API_BASE}/api/evaluate`);
        if (res.ok) {
            const data = await res.json();
            state.evaluation = data;
            
            if (data.holdout_evaluation && data.holdout_evaluation.hit_rate_top5 !== undefined) {
                document.getElementById("evalHitRate").innerText = (data.holdout_evaluation.hit_rate_top5 * 100).toFixed(1) + "%";
                document.getElementById("evalPrecision").innerText = (data.holdout_evaluation.mean_precision_top5 * 100).toFixed(1) + "%";
            }
            if (data.rule_quality) {
                document.getElementById("evalCoverage").innerText = (data.rule_quality.catalog_coverage_pct || 0) + "%";
                document.getElementById("evalAvgLift").innerText = (data.rule_quality.avg_lift || 0) + "x";
            }
        }
    } catch (e) {
        console.warn("Evaluation fetch failed:", e);
    }
}

// ==================== Admin Panel: Products CRUD ====================

async function fetchAdminProducts() {
    const tableBody = document.getElementById("adminProductsTableBody");
    tableBody.innerHTML = `<tr><td colspan="6" class="loading-cell"><i class="fa-solid fa-spinner fa-spin"></i> Loading catalog products...</td></tr>`;

    try {
        const res = await authFetch(`${API_BASE}/api/products?limit=200`);
        if (res.ok) {
            const data = await res.json();
            state.adminProducts = data.products || [];
            renderAdminProductsTable(data.products || []);
        } else {
            throw new Error(`Failed with status ${res.status}`);
        }
    } catch (e) {
        tableBody.innerHTML = `<tr><td colspan="6" style="color: #f43f5e; text-align: center; padding: 1.5rem;">Failed to load products: ${escapeHtml(e.message)}</td></tr>`;
    }
}

function renderAdminProductsTable(products) {
    const tableBody = document.getElementById("adminProductsTableBody");
    if (!products || products.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No products found in database.</td></tr>`;
        return;
    }

    tableBody.innerHTML = products.map(p => `
        <tr>
            <td style="font-family: monospace; color: var(--text-dim);">${escapeHtml(p.stock_code || 'N/A')}</td>
            <td>
                <span style="font-size: 1.2rem; margin-right: 6px;">${p.emoji || '📦'}</span>
                <strong>${escapeHtml(p.product)}</strong>
            </td>
            <td><span class="product-tag">${escapeHtml(p.category)}</span></td>
            <td><strong style="color: var(--accent-emerald);">$${parseFloat(p.price).toFixed(2)}</strong></td>
            <td style="color: var(--text-muted); max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(p.description || '')}</td>
            <td>
                <button class="btn-table-action edit" onclick="openEditProductModal(${p.id})"><i class="fa-solid fa-pen-to-square"></i> Edit</button>
                <button class="btn-table-action delete" onclick="handleDeleteProduct(${p.id}, '${escapeHtml(p.product)}')"><i class="fa-solid fa-trash"></i></button>
            </td>
        </tr>
    `).join('');
}

function openAddProductModal() {
    document.getElementById("productModalTitle").innerHTML = `<i class="fa-solid fa-plus"></i> Add New Product`;
    document.getElementById("prodEditId").value = "";
    document.getElementById("prodStockCode").value = "";
    document.getElementById("prodName").value = "";
    document.getElementById("prodCategory").value = "Kitchenware";
    document.getElementById("prodEmoji").value = "☕";
    document.getElementById("prodPrice").value = "9.99";
    document.getElementById("prodDesc").value = "";
    document.getElementById("productModalOverlay").classList.add("active");
}

function openEditProductModal(productId) {
    const prod = state.adminProducts.find(p => p.id === productId);
    if (!prod) return;

    document.getElementById("productModalTitle").innerHTML = `<i class="fa-solid fa-pen-to-square"></i> Edit Product #${productId}`;
    document.getElementById("prodEditId").value = prod.id;
    document.getElementById("prodStockCode").value = prod.stock_code || "";
    document.getElementById("prodName").value = prod.product;
    document.getElementById("prodCategory").value = prod.category;
    document.getElementById("prodEmoji").value = prod.emoji || "📦";
    document.getElementById("prodPrice").value = prod.price;
    document.getElementById("prodDesc").value = prod.description || "";
    document.getElementById("productModalOverlay").classList.add("active");
}

async function handleProductFormSubmit(e) {
    e.preventDefault();
    const editId = document.getElementById("prodEditId").value;
    const stock_code = document.getElementById("prodStockCode").value.trim();
    const product = document.getElementById("prodName").value.trim();
    const category = document.getElementById("prodCategory").value;
    const emoji = document.getElementById("prodEmoji").value.trim() || "📦";
    const price = parseFloat(document.getElementById("prodPrice").value);
    const description = document.getElementById("prodDesc").value.trim();

    const payload = { stock_code, product, category, emoji, price, description };
    const isEdit = Boolean(editId);
    const url = isEdit ? `${API_BASE}/api/admin/products/${editId}` : `${API_BASE}/api/admin/products`;
    const method = isEdit ? "PUT" : "POST";

    try {
        const res = await authFetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            closeModal("productModalOverlay");
            showToast(`Product ${isEdit ? 'updated' : 'created'} successfully!`, "success");
            fetchAdminProducts();
            fetchCatalog();
        } else {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Operation failed.");
        }
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function handleDeleteProduct(productId, productName) {
    if (!confirm(`Are you sure you want to delete "${productName}"?`)) return;

    try {
        const res = await authFetch(`${API_BASE}/api/admin/products/${productId}`, {
            method: "DELETE"
        });
        if (res.ok) {
            showToast(`Product "${productName}" deleted.`, "info");
            fetchAdminProducts();
            fetchCatalog();
        } else {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to delete product.");
        }
    } catch (err) {
        showToast(err.message, "error");
    }
}

// ==================== Admin Panel: User Management ====================

async function fetchAdminUsers() {
    const tableBody = document.getElementById("adminUsersTableBody");
    tableBody.innerHTML = `<tr><td colspan="7" class="loading-cell"><i class="fa-solid fa-spinner fa-spin"></i> Loading users...</td></tr>`;

    try {
        const res = await authFetch(`${API_BASE}/api/admin/users`);
        if (res.ok) {
            const users = await res.json();
            state.adminUsers = users;
            renderAdminUsersTable(users);
        } else {
            throw new Error(`Failed to load users (${res.status})`);
        }
    } catch (e) {
        tableBody.innerHTML = `<tr><td colspan="7" style="color: #f43f5e; text-align: center; padding: 1.5rem;">Failed to load users: ${escapeHtml(e.message)}</td></tr>`;
    }
}

function renderAdminUsersTable(users) {
    const tableBody = document.getElementById("adminUsersTableBody");
    if (!users || users.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No users found.</td></tr>`;
        return;
    }

    tableBody.innerHTML = users.map(u => `
        <tr>
            <td><strong>#${u.id}</strong></td>
            <td><strong>${escapeHtml(u.name)}</strong></td>
            <td style="color: var(--text-dim);">${escapeHtml(u.email)}</td>
            <td><span class="role-badge ${u.role}">${u.role.toUpperCase()}</span></td>
            <td>
                <span class="status-badge ${u.is_active ? 'active' : 'inactive'}">
                    ${u.is_active ? 'Active' : 'Disabled'}
                </span>
            </td>
            <td style="color: var(--text-dim); font-size: 0.8rem;">${new Date(u.created_at).toLocaleDateString()}</td>
            <td>
                <button class="btn-table-action toggle" onclick="handleToggleUserStatus(${u.id}, ${u.is_active})">
                    ${u.is_active ? '<i class="fa-solid fa-user-slash"></i> Disable' : '<i class="fa-solid fa-user-check"></i> Enable'}
                </button>
                <button class="btn-table-action edit" onclick="handleToggleUserRole(${u.id}, '${u.role}')">
                    <i class="fa-solid fa-shield"></i> Set ${u.role === 'admin' ? 'User' : 'Admin'}
                </button>
            </td>
        </tr>
    `).join('');
}

async function handleToggleUserStatus(userId, currentActive) {
    try {
        const res = await authFetch(`${API_BASE}/api/admin/users/${userId}/status`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_active: !currentActive })
        });
        if (res.ok) {
            showToast(`User status updated.`, "success");
            fetchAdminUsers();
        } else {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to update user status.");
        }
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function handleToggleUserRole(userId, currentRole) {
    const newRole = currentRole === "admin" ? "user" : "admin";
    try {
        const res = await authFetch(`${API_BASE}/api/admin/users/${userId}/role`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role: newRole })
        });
        if (res.ok) {
            showToast(`User role updated to ${newRole.toUpperCase()}.`, "success");
            fetchAdminUsers();
        } else {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to update role.");
        }
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== Admin Panel: All Orders ====================

async function fetchAdminOrders() {
    const tableBody = document.getElementById("adminOrdersTableBody");
    tableBody.innerHTML = `<tr><td colspan="7" class="loading-cell"><i class="fa-solid fa-spinner fa-spin"></i> Loading orders ledger...</td></tr>`;

    try {
        const res = await authFetch(`${API_BASE}/api/admin/orders`);
        if (res.ok) {
            const orders = await res.json();
            state.adminOrders = orders;
            renderAdminOrdersTable(orders);
        } else {
            throw new Error(`Failed to load orders (${res.status})`);
        }
    } catch (e) {
        tableBody.innerHTML = `<tr><td colspan="7" style="color: #f43f5e; text-align: center; padding: 1.5rem;">Failed to load orders: ${escapeHtml(e.message)}</td></tr>`;
    }
}

function renderAdminOrdersTable(orders) {
    const tableBody = document.getElementById("adminOrdersTableBody");
    if (!orders || orders.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No customer orders placed yet.</td></tr>`;
        return;
    }

    tableBody.innerHTML = orders.map(o => `
        <tr>
            <td><strong>#${o.id}</strong></td>
            <td><strong>${escapeHtml(o.user_name || 'Customer')}</strong></td>
            <td style="color: var(--text-dim);">${escapeHtml(o.user_email || 'N/A')}</td>
            <td><strong style="color: var(--accent-emerald);">$${parseFloat(o.total).toFixed(2)}</strong></td>
            <td><span class="rec-score-pill">${o.items ? o.items.length : 0} items</span></td>
            <td style="color: var(--text-dim); font-size: 0.8rem;">${new Date(o.created_at).toLocaleString()}</td>
            <td>
                <button class="btn-table-action edit" onclick="viewOrderReceipt(${o.id})">
                    <i class="fa-solid fa-eye"></i> Receipt
                </button>
            </td>
        </tr>
    `).join('');
}

function viewOrderReceipt(orderId) {
    const order = state.adminOrders.find(o => o.id === orderId) || state.userOrders.find(o => o.id === orderId);
    if (!order) return;

    const modal = document.getElementById("orderDetailModalOverlay");
    const title = document.getElementById("orderDetailTitle");
    const body = document.getElementById("orderDetailBody");

    title.innerHTML = `<i class="fa-solid fa-receipt"></i> Order Receipt #${order.id}`;
    body.innerHTML = `
        <div style="margin-bottom: 1.25rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border-color);">
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
                <span style="color: var(--text-muted);">Customer:</span>
                <strong style="color: #fff;">${escapeHtml(order.user_name || state.user.name)}</strong>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
                <span style="color: var(--text-muted);">Email:</span>
                <span style="color: var(--text-main);">${escapeHtml(order.user_email || state.user.email)}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
                <span style="color: var(--text-muted);">Date:</span>
                <span style="color: var(--text-dim);">${new Date(order.created_at).toLocaleString()}</span>
            </div>
        </div>

        <h4 style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.75rem;">Basket Items</h4>
        <div style="max-height: 240px; overflow-y: auto; margin-bottom: 1.25rem;">
            ${(order.items || []).map(i => `
                <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem;">
                    <div>
                        <span style="color: #fff; font-weight: 500;">${escapeHtml(i.product)}</span>
                        <span style="display: block; font-size: 0.75rem; color: var(--text-dim);">${i.quantity} x $${parseFloat(i.price).toFixed(2)}</span>
                    </div>
                    <strong style="color: var(--text-main);">$${(i.price * i.quantity).toFixed(2)}</strong>
                </div>
            `).join('')}
        </div>

        <div style="display: flex; justify-content: space-between; font-size: 1.2rem; color: #fff; font-weight: 700; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
            <span>Order Total:</span>
            <span style="color: var(--accent-emerald);">$${parseFloat(order.total).toFixed(2)}</span>
        </div>
    `;
    modal.classList.add("active");
}

// ==================== Admin Panel: Model Retrain ====================

async function handleRetrain(e) {
    e.preventDefault();
    const btn = document.getElementById("btnRetrainSubmit");
    const output = document.getElementById("retrainStatusOutput");

    const min_support = parseFloat(document.getElementById("retrainSupport").value) || 0.005;
    const min_confidence = parseFloat(document.getElementById("retrainConfidence").value) || 0.20;
    const min_lift = parseFloat(document.getElementById("retrainLift").value) || 1.2;

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Mining Itemsets with FPGrowth...`;
    output.innerHTML = `
        <div style="text-align: center; padding: 2rem 1rem;">
            <i class="fa-solid fa-brain fa-fade" style="font-size: 2rem; color: var(--primary); margin-bottom: 1rem; display: block;"></i>
            <h4 style="color: #fff; margin-bottom: 0.5rem;">Mining Frequent Itemsets & Rules</h4>
            <p style="font-size: 0.85rem; color: var(--text-muted);">Executing FPGrowth across 18.2K baskets at min_support=${min_support}... Please wait.</p>
        </div>
    `;

    try {
        const res = await authFetch(`${API_BASE}/api/admin/retrain`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ min_support, min_confidence, min_lift })
        });

        if (res.ok) {
            const data = await res.json();
            showToast("Model retrained successfully!", "success");
            output.innerHTML = `
                <div style="padding: 1rem 0;">
                    <div class="auth-alert success" style="margin-bottom: 1rem;">
                        <i class="fa-solid fa-circle-check"></i> ${escapeHtml(data.message)}
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; margin-bottom: 1rem;">
                        <div style="background: rgba(15,23,42,0.6); padding: 0.85rem; border-radius: 8px;">
                            <span style="font-size: 0.75rem; color: var(--text-dim); display: block;">MINED RULES</span>
                            <strong style="font-size: 1.4rem; color: var(--accent-cyan);">${data.total_rules.toLocaleString()}</strong>
                        </div>
                        <div style="background: rgba(15,23,42,0.6); padding: 0.85rem; border-radius: 8px;">
                            <span style="font-size: 0.75rem; color: var(--text-dim); display: block;">AVG LIFT</span>
                            <strong style="font-size: 1.4rem; color: var(--accent-emerald);">${data.summary.avg_lift}x</strong>
                        </div>
                    </div>
                    <p style="font-size: 0.82rem; color: var(--text-dim);">New rules have been cached to disk and loaded into live inference memory.</p>
                </div>
            `;
            // Refresh rules and evaluation
            fetchRules();
            fetchEvaluation();
        } else {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Retraining failed.");
        }
    } catch (e) {
        showToast(e.message, "error");
        output.innerHTML = `<div class="auth-alert error">Retraining failed: ${escapeHtml(e.message)}</div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-gear"></i> Start Model Retraining`;
    }
}

// ==================== Modals & Utilities ====================

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove("active");
}

window.addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-overlay")) {
        e.target.classList.remove("active");
    }
});

function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;

    let icon = "fa-circle-info";
    if (type === "success") icon = "fa-circle-check";
    else if (type === "error") icon = "fa-circle-exclamation";

    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(100%)";
        toast.style.transition = "all 0.3s ease";
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

function truncateText(str, maxLen = 22) {
    if (!str) return '';
    return str.length > maxLen ? str.substring(0, maxLen - 2) + '...' : str;
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
