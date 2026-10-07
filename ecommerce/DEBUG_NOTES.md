# NexusCart - Debug Notes & Root Cause Analysis

## Bug 1: Association Rules tab stuck on "Loading mined association rules..."
**Root Cause:** `AssociationRuleMiner.mine_rules()` returns cached rules without filtering by requested `min_confidence`/`min_lift`, and `frontend/app.js`'s `fetchRules()` lacks error/empty state handling and timeout aborts, leaving the initial loading spinner permanently visible if a failure or non-OK response occurs.

## Bug 2: Invisible visualizations on "Dataset Analytics"
**Root Cause:** Analytics charts rely on static server-rendered PNG images whose `onerror` fallback points to `via.placeholder.com` (a defunct service), resulting in broken images and empty boxes instead of dynamic client-side visual charts.

## Bug 3: "Frequently Bought Together" always showing the same 3 products
**Root Cause:** Recommendation engine falls back to an identical static top-10 popular items list due to high `min_support` (0.01) restricting rule coverage to a single teacup/cakestand cluster, lack of item-to-item co-occurrence fallback, a catalog of only the first 30 CSV rows, and querying recommendations with an empty cart on page load.
