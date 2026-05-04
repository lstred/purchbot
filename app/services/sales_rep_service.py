"""Sales Rep Performance Metrics and Health Score Calculation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np


def build_bscode_peer_groups(
    assignments_df: pd.DataFrame,
    salesman_map: Dict[str, str],
    min_peers: int = 3,
    dominance_pct_threshold: float = 0.15,
    dominance_count_threshold: int = 3,
    similarity_threshold: float = 0.60
) -> Dict[str, List[str]]:
    """Build peer groups based on dominant BSCODE (cost center) assignment profiles.
    
    This method uses BILLSLMN assignments as the source of truth for similarity,
    ensuring reps are only compared to those with genuinely similar product category
    responsibilities.
    
    Algorithm:
    1. For each rep (salesman_number), determine their dominant BSCODE set:
       - A BSCODE is "dominant" if it appears on >= X% of assigned accounts
         AND on >= Y distinct accounts
       - This filters out incidental/edge-case assignments
    
    2. Calculate similarity between reps using Jaccard similarity on dominant BSCODEs:
       - similarity = |intersection| / |union|
       - Reps with similarity >= threshold are considered peers
    
    3. Form peer groups with minimum size requirement for stability
    
    Args:
        assignments_df: DataFrame from BILLSLMN with columns:
            - account_number (BSACCT)
            - salesman_number (BSSLMN)
            - cost_center (BSCODE)
        salesman_map: Dict mapping salesman_number -> salesperson_name
        min_peers: Minimum peer group size (default 3)
        dominance_pct_threshold: Min % of accounts for BSCODE to be "dominant" (default 15%)
        dominance_count_threshold: Min account count for BSCODE to be "dominant" (default 3)
        similarity_threshold: Min Jaccard similarity to be considered peers (default 0.60)
    
    Returns:
        Dict mapping salesperson_name -> list of peer salesperson names
    
    Default thresholds rationale:
    - 15% / 3 accounts: Balances filtering noise while capturing secondary specializations
    - 0.60 similarity: Requires substantial BSCODE overlap (stricter than old 0.30 threshold)
    """
    peer_groups = {}
    
    # Build dominant BSCODE profile for each rep
    rep_bscode_profiles = {}
    
    for salesman_num, salesperson_name in salesman_map.items():
        # Get this rep's assignments
        rep_assignments = assignments_df[
            assignments_df["salesman_number"] == salesman_num
        ]
        
        if rep_assignments.empty:
            continue
        
        # Count accounts per BSCODE
        bscode_account_counts = rep_assignments.groupby("cost_center")["account_number"].nunique()
        total_accounts = rep_assignments["account_number"].nunique()
        
        # Determine dominant BSCODEs (meet both percentage AND count thresholds)
        dominant_bscodes = set()
        for bscode, account_count in bscode_account_counts.items():
            pct_of_accounts = account_count / total_accounts if total_accounts > 0 else 0
            
            if pct_of_accounts >= dominance_pct_threshold and account_count >= dominance_count_threshold:
                dominant_bscodes.add(bscode)
        
        # Store profile (only if has dominant BSCODEs)
        if dominant_bscodes:
            rep_bscode_profiles[salesperson_name] = {
                "dominant_bscodes": dominant_bscodes,
                "total_accounts": total_accounts,
                "all_bscodes": set(bscode_account_counts.keys())
            }
    
    # Form peer groups based on dominant BSCODE similarity
    for rep_name, rep_profile in rep_bscode_profiles.items():
        rep_dominant = rep_profile["dominant_bscodes"]
        peers = []
        
        for other_rep, other_profile in rep_bscode_profiles.items():
            other_dominant = other_profile["dominant_bscodes"]
            
            # Calculate Jaccard similarity on dominant BSCODEs only
            if rep_dominant and other_dominant:
                intersection = len(rep_dominant & other_dominant)
                union = len(rep_dominant | other_dominant)
                similarity = intersection / union if union > 0 else 0
                
                # Include as peer if similarity meets threshold
                if similarity >= similarity_threshold:
                    peers.append(other_rep)
        
        # Only use peer group if it has enough members
        if len(peers) >= min_peers:
            peer_groups[rep_name] = peers
        else:
            # Not enough similar peers - use all reps with any BSCODE profile as fallback
            # (This prevents penalizing reps with unique specializations)
            peer_groups[rep_name] = list(rep_bscode_profiles.keys())
    
    return peer_groups


def build_category_peer_groups(all_reps_metrics: List[Dict], min_peers: int = 3) -> Dict[str, List[str]]:
    """DEPRECATED: Legacy peer grouping based on sales category overlap.
    
    Use build_bscode_peer_groups() instead for more accurate BSCODE-based similarity.
    
    This function is maintained for backward compatibility only.
    
    Reps are grouped as peers if they sell similar product categories. This avoids
    unfair comparisons between narrow specialists and broad generalists.
    
    Args:
        all_reps_metrics: List of metrics dicts for all reps (each has revenue_by_category)
        min_peers: Minimum number of peers required for a valid peer group (default 3)
    
    Returns:
        Dict mapping rep_name -> list of peer names (including self) that sell overlapping categories
    """
    peer_groups = {}
    
    # Extract rep names and their categories
    rep_categories = {}
    for metrics in all_reps_metrics:
        rep_name = metrics.get("salesperson", "Unknown")
        categories = set(metrics.get("revenue_by_category", {}).keys())
        if categories:  # Only include reps with category data
            rep_categories[rep_name] = categories
    
    # For each rep, find peers with overlapping categories
    for rep_name, rep_cats in rep_categories.items():
        peers = []
        for other_rep, other_cats in rep_categories.items():
            # Calculate Jaccard similarity (intersection / union)
            if rep_cats and other_cats:
                overlap = len(rep_cats & other_cats)
                union = len(rep_cats | other_cats)
                similarity = overlap / union if union > 0 else 0
                
                # Include as peer if >30% category overlap
                if similarity >= 0.3:
                    peers.append(other_rep)
        
        # Only use peer group if it has enough members
        if len(peers) >= min_peers:
            peer_groups[rep_name] = peers
        else:
            # Not enough peers - use all reps as fallback
            peer_groups[rep_name] = list(rep_categories.keys())
    
    return peer_groups


def calculate_rep_metrics(df: pd.DataFrame, rep_name: str, start_date: date, end_date: date) -> Dict:
    """Calculate comprehensive metrics for a single sales rep.
    
    Args:
        df: DataFrame with columns: order_date, salesperson, order_number, account_number,
            line_revenue, line_gross_profit, product_category, price_class
        rep_name: Name of the sales rep to analyze
        start_date: Start of analysis period
        end_date: End of analysis period
    
    Returns:
        Dictionary with all calculated metrics
    """
    # Filter to this rep and date range
    rep_df = df[
        (df["salesperson"] == rep_name) &
        (df["order_date"] >= pd.Timestamp(start_date)) &
        (df["order_date"] <= pd.Timestamp(end_date))
    ].copy()
    
    if rep_df.empty:
        return {
            "salesperson": rep_name,
            "total_revenue": 0,
            "total_gross_profit": 0,
            "avg_margin_pct": 0,
            "orders_count": 0,
            "active_customers": 0,
            "revenue_per_customer": 0,
            "gp_per_customer": 0,
            "avg_gp_per_order": 0,
            "revenue_by_category": {},
            "margin_by_category": {},
            "top_customer_concentration": 0,
            "top3_customer_concentration": 0,
            "margin_std_dev": 0,
        }
    
    # Aggregate by order for order-level metrics
    order_agg = rep_df.groupby("order_number").agg({
        "line_revenue": "sum",
        "line_gross_profit": "sum",
        "account_number": "first"
    }).reset_index()
    order_agg["margin_pct"] = (order_agg["line_gross_profit"] / order_agg["line_revenue"] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    
    # Core outcomes
    total_revenue = rep_df["line_revenue"].sum()
    total_gp = rep_df["line_gross_profit"].sum()
    avg_margin_pct = (total_gp / total_revenue * 100) if total_revenue > 0 else 0
    orders_count = order_agg["order_number"].nunique()
    
    # Customer health
    active_customers = rep_df["account_number"].nunique()
    revenue_per_customer = total_revenue / active_customers if active_customers > 0 else 0
    gp_per_customer = total_gp / active_customers if active_customers > 0 else 0
    
    # Sales efficiency - CHANGED: Removed avg_order_value (not meaningful for specialists)
    # GP per order still useful when compared within category peer groups
    avg_gp_per_order = total_gp / orders_count if orders_count > 0 else 0
    
    # Product mix
    category_agg = rep_df.groupby("product_category").agg({
        "line_revenue": "sum",
        "line_gross_profit": "sum"
    })
    revenue_by_category = category_agg["line_revenue"].to_dict()
    margin_by_category = {}
    for cat in category_agg.index:
        cat_rev = category_agg.loc[cat, "line_revenue"]
        cat_gp = category_agg.loc[cat, "line_gross_profit"]
        margin_by_category[cat] = (cat_gp / cat_rev * 100) if cat_rev > 0 else 0
    
    # Risk indicators
    customer_revenue = rep_df.groupby("account_number")["line_revenue"].sum().sort_values(ascending=False)
    top_customer_concentration = (customer_revenue.iloc[0] / total_revenue * 100) if len(customer_revenue) > 0 else 0
    top3_customer_concentration = (customer_revenue.head(3).sum() / total_revenue * 100) if len(customer_revenue) > 0 else 0
    
    # Margin consistency (order-level std dev)
    margin_std_dev = order_agg["margin_pct"].std() if len(order_agg) > 1 else 0
    
    return {
        "salesperson": rep_name,  # Include rep name for peer grouping
        "total_revenue": total_revenue,
        "total_gross_profit": total_gp,
        "avg_margin_pct": avg_margin_pct,
        "orders_count": orders_count,
        "active_customers": active_customers,
        "revenue_per_customer": revenue_per_customer,
        "gp_per_customer": gp_per_customer,  # NEW: Customer-based efficiency metric
        "avg_gp_per_order": avg_gp_per_order,  # CHANGED: Now compared within category peers only
        "revenue_by_category": revenue_by_category,
        "margin_by_category": margin_by_category,
        "top_customer_concentration": top_customer_concentration,
        "top3_customer_concentration": top3_customer_concentration,
        "margin_std_dev": margin_std_dev,
    }


def calculate_rolling_metrics(df: pd.DataFrame, rep_name: str, weeks: int = 12) -> Dict:
    """Calculate rolling window metrics using CLOSED ISO WEEKS for seasonality robustness.
    
    CHANGED: Now uses 12 closed ISO weeks (Mon-Sun) instead of months to handle seasonality.
    Excludes current in-progress week to ensure apples-to-apples comparisons.
    
    Args:
        df: Full DataFrame with all dates
        rep_name: Sales rep name
        weeks: Number of closed weeks for rolling window (default 12)
    
    Returns:
        Dict with rolling metrics including seasonally-adjusted momentum
    """
    rep_df = df[df["salesperson"] == rep_name].copy()
    
    if rep_df.empty or "order_date" not in rep_df.columns:
        return {
            "rolling_revenue": [],
            "rolling_margin": [],
            "revenue_growth_pct": 0,
            "weekly_trend_slope": 0,
            "rep_vs_company_index": 100
        }
    
    # Calculate last closed Sunday (end of last complete week)
    today = pd.Timestamp(date.today())
    days_since_monday = today.weekday()  # Monday = 0, Sunday = 6
    last_sunday = today - timedelta(days=days_since_monday + 1)
    
    # Filter to only closed weeks (exclude current in-progress week)
    rep_df = rep_df[rep_df["order_date"] <= last_sunday].copy()
    
    if rep_df.empty:
        return {
            "rolling_revenue": [],
            "rolling_margin": [],
            "revenue_growth_pct": 0,
            "weekly_trend_slope": 0,
            "rep_vs_company_index": 100
        }
    
    # Add ISO week column (YYYY-WW format)
    rep_df["iso_year"] = rep_df["order_date"].dt.isocalendar().year
    rep_df["iso_week"] = rep_df["order_date"].dt.isocalendar().week
    rep_df["year_week"] = rep_df["iso_year"].astype(str) + "-W" + rep_df["iso_week"].astype(str).str.zfill(2)
    
    # Aggregate by ISO week
    weekly = rep_df.groupby("year_week").agg({
        "line_revenue": "sum",
        "line_gross_profit": "sum",
        "order_date": "min"  # Keep first date of week for sorting
    }).reset_index()
    weekly = weekly.sort_values("order_date")
    
    # Calculate margin %
    weekly["margin_pct"] = (weekly["line_gross_profit"] / weekly["line_revenue"] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    
    # Calculate rolling averages (12-week window)
    weekly["rolling_revenue"] = weekly["line_revenue"].rolling(window=weeks, min_periods=1).mean()
    weekly["rolling_margin"] = weekly["margin_pct"].rolling(window=weeks, min_periods=1).mean()
    
    # SEASONALLY-ADJUSTED MOMENTUM: Compare last 12 weeks vs prior 12 weeks
    # This smooths volatility and handles seasonal patterns better than month-based
    if len(weekly) >= 24:
        recent_12w = weekly.tail(12)["line_revenue"].sum()
        prior_12w = weekly.iloc[-24:-12]["line_revenue"].sum()
        revenue_growth_pct = ((recent_12w / prior_12w - 1) * 100) if prior_12w > 0 else 0
    elif len(weekly) >= 12:
        # Not enough for full comparison, use available data
        recent_12w = weekly.tail(12)["line_revenue"].sum()
        if len(weekly) > 12:
            prior_weeks = weekly.iloc[:-12]["line_revenue"].sum()
            revenue_growth_pct = ((recent_12w / prior_weeks - 1) * 100) if prior_weeks > 0 else 0
        else:
            revenue_growth_pct = 0
    else:
        revenue_growth_pct = 0
    
    # Calculate trend slope (linear regression over last 12 weeks)
    # Positive slope = upward trend, negative = downward
    weekly_trend_slope = 0
    if len(weekly) >= 12:
        last_12_weeks = weekly.tail(12).copy()
        last_12_weeks["week_num"] = range(len(last_12_weeks))
        # Simple linear regression: slope = correlation * (std_y / std_x)
        if last_12_weeks["line_revenue"].std() > 0:
            correlation = last_12_weeks["week_num"].corr(last_12_weeks["line_revenue"])
            std_ratio = last_12_weeks["line_revenue"].std() / last_12_weeks["week_num"].std()
            weekly_trend_slope = correlation * std_ratio
    
    return {
        "rolling_revenue": weekly[["order_date", "rolling_revenue"]].to_dict("records"),
        "rolling_margin": weekly[["order_date", "rolling_margin"]].to_dict("records"),
        "revenue_growth_pct": revenue_growth_pct,
        "weekly_trend_slope": weekly_trend_slope,
        "weeks_analyzed": len(weekly)
    }


def calculate_new_vs_existing_customers(df: pd.DataFrame, rep_name: str, lookback_days: int = 90) -> Dict:
    """Calculate new vs existing customer revenue mix.
    
    A customer is "new" if their first order was within the last lookback_days.
    
    Args:
        df: Full DataFrame
        rep_name: Sales rep name
        lookback_days: Days to consider a customer "new" (default 90)
    
    Returns:
        Dict with new_customer_revenue, existing_customer_revenue, new_pct
    """
    rep_df = df[df["salesperson"] == rep_name].copy()
    
    if rep_df.empty:
        return {
            "new_customer_revenue": 0,
            "existing_customer_revenue": 0,
            "new_pct": 0
        }
    
    # Find first order date per customer
    first_orders = rep_df.groupby("account_number")["order_date"].min().reset_index()
    first_orders.columns = ["account_number", "first_order_date"]
    
    # Merge back
    rep_df = rep_df.merge(first_orders, on="account_number", how="left")
    
    # Calculate days since first order
    rep_df["days_since_first"] = (rep_df["order_date"] - rep_df["first_order_date"]).dt.days
    
    # Classify as new or existing
    cutoff_date = date.today() - timedelta(days=lookback_days)
    rep_df["is_new_customer"] = rep_df["first_order_date"] >= pd.Timestamp(cutoff_date)
    
    new_customer_revenue = rep_df[rep_df["is_new_customer"]]["line_revenue"].sum()
    existing_customer_revenue = rep_df[~rep_df["is_new_customer"]]["line_revenue"].sum()
    total_revenue = new_customer_revenue + existing_customer_revenue
    new_pct = (new_customer_revenue / total_revenue * 100) if total_revenue > 0 else 0
    
    return {
        "new_customer_revenue": new_customer_revenue,
        "existing_customer_revenue": existing_customer_revenue,
        "new_pct": new_pct
    }


def calculate_health_score(
    rep_metrics: Dict,
    rolling_metrics: Dict,
    all_reps_metrics: List[Dict],
    all_reps_rolling: List[Dict],
    company_avg_margin: float,
    account_coverage_metrics: Dict = None,
    assignments_df: pd.DataFrame = None,
    salesman_map: Dict[str, str] = None
) -> Tuple[float, Dict]:
    """Calculate Rep Health Score (0-100) with BSCODE-aware component breakdown.
    
    CHANGED: BSCODE-based peer grouping using BILLSLMN assignments for accurate similarity.
    ADDED: Account Coverage Effectiveness component to measure assignment conversion.
    
    Score components (UPDATED WEIGHTS with dynamic adjustment):
    - Revenue Momentum (13%): Seasonally-adjusted using 12-week closed periods + percentile rank
    - Margin Discipline (21%): Avg margin vs company avg, penalty for volatility
    - Customer Health (21%): Customer count and revenue per customer, concentration penalty
    - Sales Efficiency (17%): GP per customer and GP per order (BSCODE-aware)
    - Product Mix Quality (13%): BSCODE-scoped margin performance
    - Account Coverage Effectiveness (15%): Conversion rate of assigned accounts (NEW)
    
    BSCODE-based peer grouping: Reps are compared only to peers with similar dominant cost center
    assignments (60%+ BSCODE overlap). This prevents unfair comparisons between reps with different
    product category responsibilities, using the official assignment data as source of truth.
    
    Args:
        rep_metrics: Current rep's metrics
        rolling_metrics: Rolling trend metrics (now week-based)
        all_reps_metrics: List of metrics for all reps (for normalization)
        all_reps_rolling: List of rolling metrics for all reps (for momentum percentile)
        company_avg_margin: Company-wide average margin %
        account_coverage_metrics: Account coverage metrics from calculate_account_coverage() (optional)
        assignments_df: BILLSLMN assignments DataFrame (optional, for BSCODE-based peer grouping)
        salesman_map: Dict mapping salesman_number -> salesperson_name (optional)
    
    Returns:
        Tuple of (total_score, component_scores_dict)
    """
    component_scores = {}
    rep_name = rep_metrics.get("salesperson", "Unknown")
    
    # Build BSCODE-based peer groups (preferred) or fall back to category-based
    if assignments_df is not None and salesman_map is not None:
        peer_groups = build_bscode_peer_groups(
            assignments_df=assignments_df,
            salesman_map=salesman_map,
            min_peers=3,
            similarity_threshold=0.60  # Stricter than old 0.30 category threshold
        )
    else:
        # Fallback to legacy category-based peer grouping
        peer_groups = build_category_peer_groups(all_reps_metrics, min_peers=3)
    
    # Get this rep's peer group (falls back to all reps if insufficient peers)
    peer_names = peer_groups.get(rep_name, [m.get("salesperson") for m in all_reps_metrics])
    peer_metrics = [m for m in all_reps_metrics if m.get("salesperson") in peer_names]
    
    # Track which components are comparable (for dynamic weight adjustment)
    comparable_components = {}
    
    # A. Revenue Momentum (15%) - SEASONALLY ADJUSTED
    # Uses multiple signals to avoid binary outcomes:
    # 1. Percentile rank of 12-week revenue among peers (40%)
    # 2. Growth rate capped at ±30% (30%)
    # 3. Trend direction (slope sign) (30%)
    
    revenue_growth = rolling_metrics.get("revenue_growth_pct", 0)
    trend_slope = rolling_metrics.get("weekly_trend_slope", 0)
    weeks_analyzed = rolling_metrics.get("weeks_analyzed", 0)
    
    # Component 1: Percentile rank (smooths seasonality by comparing to peers)
    if all_reps_rolling and len(all_reps_rolling) > 1:
        growth_values = [r.get("revenue_growth_pct", 0) for r in all_reps_rolling]
        percentile_rank = (sum(1 for g in growth_values if g <= revenue_growth) / len(growth_values)) * 100
    else:
        percentile_rank = 50  # Neutral if no peers
    
    # Component 2: Absolute growth with caps to avoid extremes
    # Cap at ±30% to prevent binary scoring
    capped_growth = max(-30, min(30, revenue_growth))
    growth_score = 50 + (capped_growth / 30) * 50  # Maps -30% to 0, 0% to 50, +30% to 100
    
    # Component 3: Trend direction (slope-based)
    # Positive slope = upward trend even if absolute numbers are seasonal
    if weeks_analyzed >= 12:
        if trend_slope > 0:
            trend_score = 60  # Upward trend
        elif trend_slope < 0:
            trend_score = 40  # Downward trend
        else:
            trend_score = 50  # Flat
    else:
        trend_score = 50  # Not enough data
    
    # Combine momentum signals (weighted)
    momentum_score = (
        percentile_rank * 0.40 +
        growth_score * 0.30 +
        trend_score * 0.30
    )
    momentum_score = max(0, min(100, momentum_score))  # Clamp to 0-100
    component_scores["revenue_momentum"] = momentum_score
    
    # B. Margin Discipline (25%) - CHANGED: BSCODE-based peer comparison
    avg_margin = rep_metrics.get("avg_margin_pct", 0)
    margin_std = rep_metrics.get("margin_std_dev", 0)
    
    # Calculate peer average margin (only reps with similar BSCODE assignments)
    if peer_metrics and len(peer_metrics) >= 3:
        peer_margins = [m.get("avg_margin_pct", 0) for m in peer_metrics if m.get("avg_margin_pct", 0) > 0]
        peer_avg_margin = sum(peer_margins) / len(peer_margins) if peer_margins else company_avg_margin
        
        # Also calculate peer average volatility for comparison
        peer_stds = [m.get("margin_std_dev", 0) for m in peer_metrics if m.get("margin_std_dev", 0) > 0]
        peer_avg_std = sum(peer_stds) / len(peer_stds) if peer_stds else 10
    else:
        # Fall back to company average if insufficient peers
        peer_avg_margin = company_avg_margin
        peer_avg_std = 10  # Reasonable default
    
    # Margin score: compare to peer average (BSCODE-based peers)
    margin_diff = avg_margin - peer_avg_margin
    margin_base = max(0, min(100, 50 + margin_diff * 5))  # ±10% margin diff = ±50 points
    
    # Penalty for high volatility compared to peer group
    # If rep's std dev is higher than peer average, apply penalty
    volatility_vs_peers = margin_std - peer_avg_std
    if volatility_vs_peers > 0:
        volatility_penalty = min(20, volatility_vs_peers * 2)
    else:
        volatility_penalty = 0
    
    margin_score = max(0, margin_base - volatility_penalty)
    component_scores["margin_discipline"] = margin_score
    comparable_components["margin_discipline"] = True
    
    # C. Customer Health (25%) - WEIGHT INCREASED from 20%
    active_customers = rep_metrics.get("active_customers", 0)
    revenue_per_customer = rep_metrics.get("revenue_per_customer", 0)
    top3_concentration = rep_metrics.get("top3_customer_concentration", 0)
    
    # Normalize customer count (percentile among all reps)
    if all_reps_metrics and len(all_reps_metrics) > 1:
        customer_counts = [m.get("active_customers", 0) for m in all_reps_metrics]
        customer_percentile = (sum(1 for c in customer_counts if c <= active_customers) / len(customer_counts)) * 100
    else:
        customer_percentile = 50
    
    # Revenue per customer (higher is better, normalized)
    if all_reps_metrics and len(all_reps_metrics) > 1:
        rpc_values = [m.get("revenue_per_customer", 0) for m in all_reps_metrics if m.get("revenue_per_customer", 0) > 0]
        if rpc_values:
            rpc_percentile = (sum(1 for r in rpc_values if r <= revenue_per_customer) / len(rpc_values)) * 100
        else:
            rpc_percentile = 50
    else:
        rpc_percentile = 50
    
    # Concentration penalty (>50% in top 3 = risky)
    concentration_penalty = max(0, (top3_concentration - 50) * 0.5) if top3_concentration > 50 else 0
    
    customer_health_score = max(0, (customer_percentile * 0.6 + rpc_percentile * 0.4) - concentration_penalty)
    component_scores["customer_health"] = customer_health_score
    comparable_components["customer_health"] = True
    
    # D. Sales Efficiency (20%) - CHANGED: BSCODE-based peer comparison
    gp_per_customer = rep_metrics.get("gp_per_customer", 0)
    avg_gp_per_order = rep_metrics.get("avg_gp_per_order", 0)
    
    # GP per customer - compare within peer group (similar BSCODE assignments)
    if peer_metrics and len(peer_metrics) > 1:
        gpc_values = [m.get("gp_per_customer", 0) for m in peer_metrics if m.get("gp_per_customer", 0) > 0]
        gpc_percentile = (sum(1 for v in gpc_values if v <= gp_per_customer) / len(gpc_values)) * 100 if gpc_values else 50
    else:
        gpc_percentile = 50
    
    # GP per order - compare within peer group (BSCODE-based peers)
    if peer_metrics and len(peer_metrics) >= 3:  # Need at least 3 peers for meaningful comparison
        gpo_values = [m.get("avg_gp_per_order", 0) for m in peer_metrics if m.get("avg_gp_per_order", 0) > 0]
        gpo_percentile = (sum(1 for v in gpo_values if v <= avg_gp_per_order) / len(gpo_values)) * 100 if gpo_values else 50
        efficiency_score = (gpc_percentile * 0.5 + gpo_percentile * 0.5)
        comparable_components["sales_efficiency"] = True
    else:
        # Not enough category peers - use GP per customer only
        efficiency_score = gpc_percentile
        comparable_components["sales_efficiency"] = "partial"  # Only 1 metric comparable
    
    component_scores["sales_efficiency"] = efficiency_score
    
    # E. Product Mix Quality (15%) - CHANGED: Category-scoped margin performance
    # Compare rep's margin performance within each category they sell
    rep_categories = rep_metrics.get("margin_by_category", {})
    
    if rep_categories and peer_metrics and len(peer_metrics) >= 3:
        # Calculate weighted average of category-specific margin performance
        category_scores = []
        category_revenues = []
        
        for cat, rep_margin in rep_categories.items():
            # Get peer margins in this category
            peer_cat_margins = []
            for peer in peer_metrics:
                peer_margin_by_cat = peer.get("margin_by_category", {})
                if cat in peer_margin_by_cat:
                    peer_cat_margins.append(peer_margin_by_cat[cat])
            
            if len(peer_cat_margins) >= 3:  # Need enough peers in this category
                # Percentile rank within category
                cat_percentile = (sum(1 for m in peer_cat_margins if m <= rep_margin) / len(peer_cat_margins)) * 100
                category_scores.append(cat_percentile)
                
                # Weight by revenue in this category
                rep_revenue_by_cat = rep_metrics.get("revenue_by_category", {})
                cat_revenue = rep_revenue_by_cat.get(cat, 0)
                category_revenues.append(cat_revenue)
        
        # Calculate weighted average score
        if category_scores and sum(category_revenues) > 0:
            total_rev = sum(category_revenues)
            product_mix_score = sum(score * rev / total_rev for score, rev in zip(category_scores, category_revenues))
            comparable_components["product_mix_quality"] = True
        else:
            # Fall back to margin discipline as proxy
            product_mix_score = margin_score
            comparable_components["product_mix_quality"] = False
    else:
        # Not enough peers or no category data - use margin discipline as proxy
        product_mix_score = margin_score
        comparable_components["product_mix_quality"] = False
    
    component_scores["product_mix_quality"] = product_mix_score
    comparable_components["revenue_momentum"] = True  # Always comparable (seasonally-adjusted)
    comparable_components["margin_discipline"] = True  # Always comparable (vs company avg)
    
    # F. Account Coverage Effectiveness (15%) - NEW
    # Measures how effectively rep converts their assigned account-category responsibilities
    # This is about opportunity capture, not punishment
    coverage_score = 50  # Default neutral score
    
    if account_coverage_metrics and account_coverage_metrics.get("total_assigned", 0) > 0:
        pct_active = account_coverage_metrics.get("pct_active_with_rep", 0)
        
        # Score based on capture rate, with curve to reward high conversion
        # 0% capture = 0 points, 50% = 50 points, 80% = 80 points, 100% = 100 points
        coverage_score = pct_active
        
        # Normalize against peers with similar assignment sizes to be fair
        # Reps with 5 accounts shouldn't be compared to reps with 500 accounts
        total_assigned = account_coverage_metrics.get("total_assigned", 0)
        
        # Find peers with similar assignment size (within 50% range)
        peer_coverage = []
        for peer_m in all_reps_metrics:
            peer_coverage_data = peer_m.get("account_coverage", {})
            peer_assigned = peer_coverage_data.get("total_assigned", 0)
            if peer_assigned > 0:
                # Check if similar size (within 2x range)
                ratio = peer_assigned / total_assigned if total_assigned > 0 else 0
                if 0.5 <= ratio <= 2.0:
                    peer_pct = peer_coverage_data.get("pct_active_with_rep", 0)
                    peer_coverage.append(peer_pct)
        
        # If we have peer data, adjust score based on percentile
        if peer_coverage and len(peer_coverage) >= 3:
            percentile = (sum(1 for p in peer_coverage if p <= pct_active) / len(peer_coverage)) * 100
            # Blend raw score (70%) with percentile (30%) to be fair
            coverage_score = pct_active * 0.7 + percentile * 0.3
            comparable_components["account_coverage_effectiveness"] = True
        else:
            # Not enough peers with similar assignment size - use raw score only
            coverage_score = pct_active
            comparable_components["account_coverage_effectiveness"] = "partial"
    else:
        # No assignment data available - mark as not comparable
        coverage_score = 50  # Neutral
        comparable_components["account_coverage_effectiveness"] = False
    
    component_scores["account_coverage_effectiveness"] = coverage_score
    
    # Calculate weighted total with DYNAMIC WEIGHT ADJUSTMENT
    # Base weights for fully comparable components (adjusted to include account coverage)
    base_weights = {
        "revenue_momentum": 0.13,
        "margin_discipline": 0.21,
        "customer_health": 0.21,
        "sales_efficiency": 0.17,
        "product_mix_quality": 0.13,
        "account_coverage_effectiveness": 0.15
    }
    
    # Adjust weights if some components are not fully comparable
    adjusted_weights = {}
    total_weight = 0
    
    for component, base_weight in base_weights.items():
        if comparable_components.get(component) == True:
            adjusted_weights[component] = base_weight
            total_weight += base_weight
        elif comparable_components.get(component) == "partial":
            # Partial comparability (e.g., only 1 of 2 metrics) - use half weight
            adjusted_weights[component] = base_weight * 0.5
            total_weight += base_weight * 0.5
        else:
            # Not comparable - zero weight
            adjusted_weights[component] = 0
    
    # Normalize weights to sum to 1.0
    if total_weight > 0:
        for component in adjusted_weights:
            adjusted_weights[component] = adjusted_weights[component] / total_weight
    
    # Calculate weighted total with adjusted weights
    total_score = (
        momentum_score * adjusted_weights.get("revenue_momentum", 0) +
        margin_score * adjusted_weights.get("margin_discipline", 0) +
        customer_health_score * adjusted_weights.get("customer_health", 0) +
        efficiency_score * adjusted_weights.get("sales_efficiency", 0) +
        product_mix_score * adjusted_weights.get("product_mix_quality", 0) +
        coverage_score * adjusted_weights.get("account_coverage_effectiveness", 0)
    )
    
    # Store adjusted weights in component scores for UI display
    component_scores["_weights"] = adjusted_weights
    component_scores["_peer_count"] = len(peer_names)
    
    return round(total_score, 1), component_scores


def calculate_account_coverage(
    rep_salesman_number: str,
    orders_df: pd.DataFrame,
    assignments_df: pd.DataFrame
) -> Dict:
    """Calculate account coverage effectiveness metrics.
    
    Measures how effectively a rep converts their assigned account-category responsibilities.
    
    Args:
        rep_salesman_number: Rep's salesman number for matching
        orders_df: Orders DataFrame (must have account_number, cost_center, line_item_slmn#)
        assignments_df: Account assignments from BILLSLMN (account_number, salesman_number, cost_center)
    
    Returns:
        Dict with:
        - total_assigned: Total assigned account-category pairs
        - active_with_rep: Count active with this rep
        - active_with_other: Count active but with other rep (leakage)
        - inactive: Count with no activity
        - pct_active_with_rep: % capture rate
        - pct_active_with_other: % leakage rate
        - pct_inactive: % inactive rate
        - revenue_leaked: Revenue generated by assigned accounts with other reps (if available)
    """
    # Get this rep's assignments
    rep_assignments = assignments_df[
        assignments_df["salesman_number"] == rep_salesman_number
    ].copy()
    
    if rep_assignments.empty:
        return {
            "total_assigned": 0,
            "active_with_rep": 0,
            "active_with_other": 0,
            "inactive": 0,
            "pct_active_with_rep": 0,
            "pct_active_with_other": 0,
            "pct_inactive": 0,
            "revenue_leaked": 0
        }
    
    # Classify each assigned account-category pair
    active_with_rep = 0
    active_with_other = 0
    inactive = 0
    revenue_leaked = 0
    
    for _, assignment in rep_assignments.iterrows():
        acct = assignment["account_number"]
        cost_ctr = assignment["cost_center"]
        
        # Find orders for this account-category pair
        matching_orders = orders_df[
            (orders_df["account_number"].astype(str) == str(acct)) &
            (orders_df["cost_center"].astype(str) == str(cost_ctr))
        ]
        
        if matching_orders.empty:
            # No activity - Inactive
            inactive += 1
        else:
            # Has activity - check who owns it
            # Check if this rep has any orders for this account-category
            rep_orders = matching_orders[
                matching_orders["line_item_slmn#"].astype(str) == str(rep_salesman_number)
            ]
            
            if not rep_orders.empty:
                # Active with this rep
                active_with_rep += 1
            else:
                # Active with other rep (leakage)
                active_with_other += 1
                # Calculate leaked revenue if revenue column exists
                if "line_revenue" in matching_orders.columns:
                    revenue_leaked += matching_orders["line_revenue"].sum()
    
    total_assigned = len(rep_assignments)
    
    return {
        "total_assigned": total_assigned,
        "active_with_rep": active_with_rep,
        "active_with_other": active_with_other,
        "inactive": inactive,
        "pct_active_with_rep": (active_with_rep / total_assigned * 100) if total_assigned > 0 else 0,
        "pct_active_with_other": (active_with_other / total_assigned * 100) if total_assigned > 0 else 0,
        "pct_inactive": (inactive / total_assigned * 100) if total_assigned > 0 else 0,
        "revenue_leaked": revenue_leaked
    }


def get_health_band(score: float) -> Tuple[str, str]:
    """Get health band label and color for a given score.
    
    Returns:
        Tuple of (band_name, color)
    """
    if score >= 80:
        return "Healthy", "#27AE60"
    elif score >= 60:
        return "Watch", "#F39C12"
    elif score >= 40:
        return "At Risk", "#E67E22"
    else:
        return "Critical", "#E74C3C"
