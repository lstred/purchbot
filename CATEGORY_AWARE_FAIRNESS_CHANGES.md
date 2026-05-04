# Category-Aware Fairness Refinements

## Summary
Updated the Sales Rep Performance dashboard to use **category-aware comparisons** that ensure fair evaluation of reps with different product specializations. This prevents unfair comparisons between narrow specialists (high-value, focused portfolios) and broad generalists (wide product range).

## Problem Statement
- **Issue**: ~40 sales reps sell different product portfolios
- **Challenge**: Global averages were misleading when comparing specialists to generalists
- **Example**: A rep selling only high-value specialty items was penalized vs a rep selling many low-value commodity items
- **Result**: Health Score was biased against product specialization

## Changes Made

### 1. New Category-Aware Peer Grouping
**File**: `app/services/sales_rep_service.py`

Added `build_category_peer_groups()` function:
- Groups reps based on product category overlap (30%+ Jaccard similarity)
- Minimum 3 peers required for valid peer group
- Falls back to all reps if insufficient peers
- Ensures comparisons are made between reps selling similar products

**Logic**:
```python
similarity = (categories_in_common) / (total_unique_categories)
if similarity >= 0.3:  # 30% overlap threshold
    include_as_peer
```

### 2. Removed Average Order Value Metric
**Files**: `app/services/sales_rep_service.py`, `app/ui/dashboard.py`

**Rationale**: Not meaningful when comparing different product types
- High-value specialty items naturally have higher AOV
- Commodity products naturally have lower AOV
- Created unfair bias in comparisons

**Actions**:
- Removed from `calculate_rep_metrics()` return dictionary
- Removed from UI display (Section 5: Sales Efficiency)
- Removed from comparison table
- Removed from Health Score Sales Efficiency component

### 3. Added GP per Customer Metric
**Files**: `app/services/sales_rep_service.py`, `app/ui/dashboard.py`

**Rationale**: Customer-based efficiency is fairer than order-based
- Normalizes for different order patterns
- Accounts for high-value/low-frequency vs low-value/high-frequency sales
- Focuses on customer relationship value

**Calculation**:
```python
gp_per_customer = total_gross_profit / active_customers
```

**Added to**:
- `calculate_rep_metrics()` return dictionary
- UI Section 5: Sales Efficiency (3-column layout)
- Comparison table
- Health Score Sales Efficiency component (50% weight)

### 4. Category-Aware Sales Efficiency Component
**File**: `app/services/sales_rep_service.py` - `calculate_health_score()`

**Changes**:
- **GP per Customer (50%)**: Compared within category-similar peer group
- **GP per Order (50%)**: Compared within category-similar peer group
- **Dynamic Weight Adjustment**: If <3 peers, uses GP per Customer only (partial comparability)

**Before**:
```python
# Global comparison - unfair
aov_percentile = percentile_rank(avg_order_value, all_reps)
gpo_percentile = percentile_rank(avg_gp_per_order, all_reps)
```

**After**:
```python
# Category-aware comparison - fair
gpc_percentile = percentile_rank(gp_per_customer, peer_group)
gpo_percentile = percentile_rank(avg_gp_per_order, peer_group)
```

### 5. Category-Aware Product Mix Quality Component
**File**: `app/services/sales_rep_service.py` - `calculate_health_score()`

**Changes**:
- Evaluates margin performance **within each category** the rep sells
- Compares to peers who also sell the same category
- Weighted average by revenue in each category
- Falls back to margin discipline proxy if insufficient category peers

**Logic**:
```python
for category in rep_categories:
    peer_margins_in_category = [peer margins in this category]
    category_percentile = percentile_rank(rep_margin, peer_margins_in_category)
    
weighted_score = sum(category_percentile * category_revenue) / total_revenue
```

### 6. Dynamic Weight Adjustment
**File**: `app/services/sales_rep_service.py` - `calculate_health_score()`

**Purpose**: Adjust Health Score weights when components aren't fully comparable

**Logic**:
- Track comparability status for each component:
  - `True`: Fully comparable (normal weight)
  - `"partial"`: Partially comparable (50% weight)
  - `False`: Not comparable (0% weight)
- Redistribute weights proportionally to remaining comparable components
- Store adjusted weights in component_scores for UI display

**Example**:
```
Rep with only 2 category peers:
- Base Sales Efficiency weight: 20%
- Adjusted to "partial" (only GP/Customer comparable)
- New weight: 10% (50% of 20%)
- Remaining 10% redistributed to other components
```

### 7. UI Updates
**File**: `app/ui/dashboard.py`

**Section 5: Sales Efficiency Metrics**:
- Changed from 2-column to 3-column layout
- Removed "Average Order Value"
- Added "GP per Customer"
- Added "Revenue per Customer"
- Kept "Avg GP per Order" with updated tooltip

**Component Score Display**:
- Added category-aware peer count caption
- Dynamic weight display (shows adjusted % if non-comparable)
- Updated tooltips to explain category-scoped comparisons
- Clear labeling: "within CATEGORY-SIMILAR peer group"

**Comparison Table**:
- Removed "Avg Order Value" column
- Added "GP/Customer" column
- Added "GP/Order" column (renamed from avg_gp_per_order)

### 8. Updated Documentation
**File**: `app/ui/dashboard.py` - Health Score Expander

**Added**:
- Section on "Category-Aware Fairness" explaining the why and how
- Updated component descriptions to specify comparison scope:
  - "All reps" for universal metrics
  - "Category-similar peer group" for specialized metrics
  - "Category-specific" for per-category evaluations
- Clarified that Average Order Value was removed
- Explained GP per Customer as fairer alternative
- Added guidance on understanding peer groups

## Technical Details

### Peer Group Algorithm
**Jaccard Similarity**:
```
J(A, B) = |A ∩ B| / |A ∪ B|

Where:
- A = set of categories rep A sells
- B = set of categories rep B sells
- Threshold: 30% similarity to be considered peers
```

**Minimum Peers**: 3 (statistical significance)

### Percentile Calculation
Maintained consistent percentile ranking formula:
```python
percentile = (count_of_values <= this_value) / total_values * 100
```

### Weight Normalization
```python
adjusted_weights[component] = base_weight * comparability_factor
normalized_weight = adjusted_weight / sum(all_adjusted_weights)
```

## Impact Assessment

### Fairness Improvements
✅ **Specialists no longer penalized** for focused product portfolios
✅ **Generalists no longer advantaged** by volume-based metrics
✅ **Category context preserved** in margin evaluations
✅ **Customer-based efficiency** more accurate than order-based

### Scoring Changes Expected
- **Specialists**: Health scores likely to increase (especially Sales Efficiency and Product Mix)
- **Generalists**: Minimal change (already had good peer comparisons)
- **Edge Cases**: Reps with <3 category peers fall back to global comparisons (transparent via weight display)

### Backward Compatibility
⚠️ **Breaking Change**: Health Scores will recalculate with new logic
- Scores not directly comparable to pre-change scores
- Recommend treating this as a "reset" for trending analysis
- Component scores show different values due to peer group changes

## Files Modified

1. **app/services/sales_rep_service.py**
   - Added `build_category_peer_groups()` function (lines 11-55)
   - Modified `calculate_rep_metrics()` to remove avg_order_value, add gp_per_customer (lines 107-119)
   - Modified `calculate_health_score()` for category-aware comparisons (lines 309-540)

2. **app/ui/dashboard.py**
   - Updated Health Score explanation expander (lines 7000-7145)
   - Updated component score display with dynamic weights and peer count (lines 7280-7330)
   - Updated Sales Efficiency section to 3-column layout with new metrics (lines 7475-7502)
   - Updated comparison table columns (lines 7525-7548)

## Testing Recommendations

1. **Peer Group Validation**:
   - Check peer counts for each rep (displayed in UI caption)
   - Verify category overlap makes sense for your business
   - Adjust threshold (30%) if too strict or too loose

2. **Score Validation**:
   - Compare before/after scores for known specialists
   - Verify weight adjustments display correctly
   - Check that component scores use appropriate peer groups

3. **Edge Cases**:
   - Single-category reps (should fall back gracefully)
   - Reps with no category data (should use global comparisons)
   - New reps with limited history (need data accumulation)

## Configuration Options

### Tunable Parameters
All hardcoded for now, but could be made configurable:

```python
# In build_category_peer_groups()
min_peers = 3  # Minimum peers for valid comparison
similarity_threshold = 0.3  # 30% category overlap

# In calculate_health_score()
base_weights = {
    "revenue_momentum": 0.15,
    "margin_discipline": 0.25,
    "customer_health": 0.25,
    "sales_efficiency": 0.20,
    "product_mix_quality": 0.15
}
```

## Future Enhancements

1. **Configurable Thresholds**: Allow user to adjust similarity % and min peer count
2. **Peer Group Visualization**: Show category overlap heatmap
3. **Trend Analysis**: Track how peer groups change over time
4. **Category Weighting**: Allow strategic categories to have higher importance
5. **Custom Peer Groups**: Manual override to force specific reps into peer groups

## Validation Queries

To verify category data quality:
```sql
-- Check category distribution per rep
SELECT 
    salesperson,
    COUNT(DISTINCT product_category) as category_count,
    STRING_AGG(DISTINCT product_category, ', ') as categories
FROM sales_rep_orders
GROUP BY salesperson
ORDER BY category_count DESC

-- Check peer overlap potential
SELECT 
    a.salesperson as rep_a,
    b.salesperson as rep_b,
    COUNT(DISTINCT a.product_category) as shared_categories
FROM sales_rep_orders a
INNER JOIN sales_rep_orders b 
    ON a.product_category = b.product_category
    AND a.salesperson <> b.salesperson
GROUP BY a.salesperson, b.salesperson
HAVING COUNT(DISTINCT a.product_category) >= 2
ORDER BY shared_categories DESC
```

## Rollout Notes

- **Communication**: Inform reps that scoring methodology has changed
- **Expectation Setting**: Scores will shift - focus on relative ranking within new system
- **Training**: Explain category-aware peer groups to managers
- **Monitoring**: Watch first 2-4 weeks for unexpected peer groupings
- **Feedback Loop**: Collect rep feedback on fairness perception

---

**Document Version**: 1.0  
**Date**: January 2025  
**Author**: AI Assistant (GitHub Copilot)  
**Related Files**: SEASONALITY_FIXES_SUMMARY.md, SALES_REP_PERFORMANCE_README.md
