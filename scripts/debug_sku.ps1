Param(
  [string]$Sku = "ENGRAFFBRDC"
)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot\..
try {
  $env:PYTHONPATH = (Get-Location).Path
  & ".\.venv\Scripts\python.exe" - << 'PY'
import os, sys
import pandas as pd
from app.services.metrics_service import compute_dashboard_data, MetricsFilters
from app.config import get_config
from datetime import date

sku = os.environ.get('DBG_SKU') or 'ENGRAFFBRDC'
cfg = get_config()
# Mirror UI defaults: no supplier/pc filters, default CCs and window from config
filters = MetricsFilters(cost_centers=[], start_date=None, end_date=None)
res = compute_dashboard_data(filters)
met = res.get('sku_metrics', pd.DataFrame())
items = res.get('items', pd.DataFrame())
backorders = res.get('backorders', pd.DataFrame())

print('SKU metrics size:', met.shape)
row = met.loc[met.get('sku').astype(str)==sku]
print('Rows for', sku, ':', len(row))
if not row.empty:
    cols = [c for c in ['sku','inventory_sy','on_order_sy','partial_received_po','assumed_on_order_sy','net_inventory_sy','avg_daily_sales_sy','cover_required_sy','jstock','target_on_hand_sy','backorder_qty_sy','reorder_qty_sy','lead_time_days'] if c in row.columns]
    print(row[cols].to_string(index=False))
else:
    print('\nSimilar SKUs in metrics (GRAFF):')
    print(met[met.get('sku').astype(str).str.contains('GRAFF', case=False, na=False)].head(15).to_string(index=False))

print('\nBackorder qty map sample for GRAFF:')
if 'backorder_qty_sy' in met.columns:
    print(met.loc[met.get('sku').astype(str).str.contains('GRAFF', case=False, na=False), ['sku','backorder_qty_sy']].head(15).to_string(index=False))

if not backorders.empty:
    bo = backorders[backorders.get('sku').astype(str)==sku]
    print('\nWindow backorder lines for', sku, ':', len(bo))
    if not bo.empty:
        print(bo[['order_number','line_number','order_entry_date','quantity_sy','detail_line_status']].head(20).to_string(index=False))
PY
} finally {
  Pop-Location
}
