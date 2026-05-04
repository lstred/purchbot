from __future__ import annotations

from typing import Dict, List

import pandas as pd


def build_alerts(summary: Dict[str, float], sku_metrics: pd.DataFrame) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []

    stock_turn = summary.get("stock_turn")
    stock_turn_target = summary.get("stock_turn_target")
    if stock_turn is not None and stock_turn_target is not None and stock_turn < stock_turn_target:
        alerts.append(
            {
                "severity": "warning",
                "title": "Stock turn below target",
                "body": f"Current stock turn is {stock_turn:.2f} vs target {stock_turn_target:.2f}.",
            }
        )

    if summary.get("fill_rate", 1) < 0.95:
        alerts.append(
            {
                "severity": "error",
                "title": "Fill rate risk",
                "body": f"Fill rate is {summary.get('fill_rate', 0):.1%}; investigate backorders",
            }
        )

    aging_bad = summary.get("aging_bad_sku_count", 0)
    if aging_bad:
        alerts.append(
            {
                "severity": "info",
                "title": "Aging inventory",
                "body": f"{aging_bad} SKUs have not moved for 18+ months.",
            }
        )

    runout_df = sku_metrics[sku_metrics.get("runout_risk", False)]
    if not runout_df.empty:
        top = runout_df.nlargest(5, "reorder_qty_sy")[["sku", "reorder_qty_sy"]]
        sku_list = ", ".join(f"{row.sku} ({row.reorder_qty_sy:.1f} SY)" for row in top.itertuples())
        alerts.append(
            {
                "severity": "error",
                "title": "Runout risk",
                "body": f"{len(runout_df)} SKUs projected to run out before replenishment: {sku_list}",
            }
        )

    return alerts
