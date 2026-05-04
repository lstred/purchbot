from __future__ import annotations

import pandas as pd


def build_reorder_plan(sku_metrics: pd.DataFrame) -> pd.DataFrame:
    """Return SKUs with non-zero recommended reorder quantity sorted by urgency."""

    if sku_metrics.empty:
        return sku_metrics

    columns = [
        "sku",
        "avg_daily_sales_sy",
        "inventory_sy",
        "on_order_sy",
        "lead_time_days",
        "reorder_qty_sy",
        "sku_rating",
    ]
    missing = [col for col in columns if col not in sku_metrics.columns]
    if missing:
        raise KeyError(f"Missing expected columns for reorder plan: {missing}")

    reorders = sku_metrics[sku_metrics["reorder_qty_sy"] > 0].copy()
    return reorders.sort_values(
        by=["runout_risk", "reorder_qty_sy", "avg_daily_sales_sy"], ascending=[False, False, False]
    )[columns]
