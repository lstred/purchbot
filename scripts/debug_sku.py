import sys
import pandas as pd
from app.services.metrics_service import compute_dashboard_data, MetricsFilters

# Args: SKU [CC1,CC2,...]
sku = sys.argv[1] if len(sys.argv) > 1 else "ENGRAFFBRDC"
ccs_arg = sys.argv[2] if len(sys.argv) > 2 else ""
ccs = [c.strip() for c in ccs_arg.split(",") if c.strip()] if ccs_arg else []

filters = MetricsFilters(cost_centers=ccs, start_date=None, end_date=None)
data = compute_dashboard_data(filters)

sku_metrics = data.get("sku_metrics", pd.DataFrame()).copy()
items = data.get("items", pd.DataFrame()).copy()
backorders = data.get("backorders", pd.DataFrame()).copy()

print(f"Looking for SKU: {sku}")
row = sku_metrics.loc[sku_metrics.get("sku").astype(str) == sku]
print(f"Rows found in sku_metrics: {len(row)}")
if not row.empty:
    cols = [c for c in [
        "sku","cost_center","price_class","inventory_sy","on_order_sy","partial_received_po",
        "assumed_on_order_sy","net_inventory_sy","avg_daily_sales_sy","cover_required_sy","jstock",
        "target_on_hand_sy","backorder_qty_sy","reorder_qty_sy","lead_time_days","seasonal_window_multiplier"
    ] if c in row.columns]
    print("\nMetrics row:\n", row[cols].to_string(index=False))
else:
    # Show similar SKUs and any alias/base mapping
    print("\nSimilar SKUs in metrics (contains 'GRAFF'):")
    sim = sku_metrics[sku_metrics.get("sku").astype(str).str.contains("GRAFF", case=False, na=False)]
    print(sim.head(10).to_string(index=False))

# Items mapping info
if not items.empty:
    it = items.copy()
    base = it.get("base_sku").astype(str) if "base_sku" in it.columns else pd.Series(dtype=str)
    mask = (it.get("sku").astype(str) == sku) | (base == sku)
    print("\nItems mapping rows (sku==SKU or base_sku==SKU):")
    print(it.loc[mask, [c for c in ["sku","base_sku","iixref","sku_description","cost_center","price_class"] if c in it.columns]].to_string(index=False))

# Show raw backorder lines contributing
if not backorders.empty:
    bo = backorders.copy()
    bo = bo[bo.get("sku").astype(str) == sku]
    print(f"\nBackorder lines for {sku} (from window copy): {len(bo)}")
    if not bo.empty:
        print(bo.head(20).to_string(index=False))
else:
    print("\nNo backorders frame returned.")
