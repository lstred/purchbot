# Margin Discipline - Category-Aware Update

## Change Summary
Updated **Margin Discipline** component to use category-aware comparisons. Reps are now compared only to peers selling the same product categories, ensuring fair evaluation of margin performance.

## Why This Matters

### The Problem
- Different product categories have inherently different margin characteristics
- Example: Specialty equipment (25-35% typical margin) vs Commodity supplies (10-15% typical margin)
- A rep selling low-margin categories was unfairly penalized when compared to company-wide average
- Margin volatility standards also vary by category (high-value items have more negotiation variance)

### The Solution
- Compare margin % to **peer group average** (reps selling 30%+ overlapping categories)
- Compare margin volatility (std dev) to **peer group volatility**
- Label all comparisons explicitly: "compared to reps selling the same categories"

## What Changed

### 1. Calculation Logic (sales_rep_service.py)

**Before:**
```python
# Global company comparison (unfair)
margin_diff = avg_margin - company_avg_margin
volatility_penalty = min(20, margin_std * 2) if margin_std > 10 else 0
```

**After:**
```python
# Category-aware peer comparison (fair)
peer_avg_margin = average(peer_margins)  # Only similar reps
peer_avg_std = average(peer_std_devs)

margin_diff = avg_margin - peer_avg_margin
volatility_vs_peers = margin_std - peer_avg_std
volatility_penalty = min(20, volatility_vs_peers * 2) if volatility_vs_peers > 0 else 0
```

**Key Changes:**
- Peer average margin calculated from category-similar reps
- Volatility penalty based on peer group standards (not absolute 10% threshold)
- Falls back to company average if insufficient peers (<3)

### 2. Driver Insights (dashboard.py - PDF generation)

**Added to insights:**
- `peer_avg_margin`: Average margin of peer group
- `peer_avg_std`: Average volatility of peer group
- `vs_peer_margin`: Difference from peer average
- `consistency`: Rating based on peer comparison (not absolute)

**Consistency Rating Updated:**
```python
# Before: Absolute thresholds
"Good" if margin_std < 10 else "Watch" if margin_std < 15 else "High Risk"

# After: Peer-relative thresholds
"Good" if margin_std < peer_avg_std 
else "Watch" if margin_std < peer_avg_std * 1.5 
else "High Risk"
```

### 3. Recommendations (dashboard.py)

**Enhanced with peer context:**
```python
# Before (generic)
"💰 Your margins vary widely (std dev: 15.2%). Review pricing consistency..."

# After (specific with peer comparison)
"💰 Your margin (18.5%) is below similar reps (22.3% avg). Review pricing strategy for your product categories."

"💰 Your margin volatility (15.2%) is higher than similar reps (9.8%). Review pricing consistency within your product categories."
```

### 4. PDF Output

**Margin section now shows:**
```
Margin: Avg 18.5% vs 22.3% peer avg (-3.8%), 
consistency Watch (std dev 15.2% vs 9.8% peer avg).
Compared to reps selling the same categories.
```

**Before:**
```
Margin: Avg 18.5%, consistency Watch (std dev 15.2%).
```

### 5. UI Tooltips

**Updated component tooltip:**
```
Before: "Margin % vs company avg with volatility penalty. 100 = at/above avg with low volatility. Penalties applied for high order-level margin std dev."

After: "Margin % and consistency compared to CATEGORY-SIMILAR peer group. Compares reps selling the same product categories. Penalties for high volatility vs peers."
```

### 6. Documentation

**Health Score Explanation Updated:**

**Comparison Scope:**
- Changed from: "Company-wide average (margin targets are universal)"
- Changed to: "Category-similar peer group (30%+ product overlap)"

**Why It Matters:**
- Added: "Category-aware comparison ensures reps aren't penalized for selling categories with inherently different margin characteristics."

## Implementation Details

### Peer Group Calculation
Uses existing `peer_groups` from `build_category_peer_groups()`:
- 30% Jaccard similarity (category overlap)
- Minimum 3 peers required
- Falls back to company average if insufficient

### Margin Metrics Collected
From each peer:
- `avg_margin_pct`: Rep's average margin %
- `margin_std_dev`: Rep's order-level margin volatility

### Scoring Formula
```python
# Base score (peer-relative)
margin_diff = rep_margin - peer_avg_margin
margin_base = 50 + (margin_diff * 5)  # ±10% = ±50 points

# Volatility penalty (peer-relative)
excess_volatility = max(0, rep_std - peer_avg_std)
volatility_penalty = min(20, excess_volatility * 2)

# Final score
margin_score = max(0, margin_base - volatility_penalty)
```

### Fallback Logic
If peer group has <3 members:
- Use `company_avg_margin` (passed parameter)
- Use default peer_avg_std = 10%
- Still calculates score, but less contextualized

## Impact Assessment

### Fairness Improvements
✅ **Specialists selling low-margin categories:** No longer penalized vs company average
✅ **High-value product reps:** Volatility expectations aligned with peer norms
✅ **Generalists:** Still fairly evaluated within their peer group
✅ **Transparent:** All comparisons labeled "compared to reps selling same categories"

### Score Changes Expected
- **Low-margin category specialists:** Scores likely increase (no longer penalized vs high-margin reps)
- **High-volatility categories:** Volatility penalties more contextual
- **Consistent performers:** Minimal change if already aligned with peers
- **Edge cases:** Reps with <3 peers fall back to company comparison

## Testing Checklist

### Calculation Validation
- [ ] Peer average margin calculated correctly
- [ ] Peer average std dev calculated correctly
- [ ] Volatility penalty only applied when above peer average
- [ ] Fallback to company avg works when <3 peers

### UI/PDF Display
- [ ] Margin insights show peer comparisons
- [ ] "Compared to reps selling same categories" label visible
- [ ] Recommendations reference peer margins
- [ ] Tooltips updated to reflect category-aware logic

### Edge Cases
- [ ] Single-category rep (narrow peer group)
- [ ] Rep with unique category mix (fallback to company)
- [ ] Rep with 0 margin (handled gracefully)
- [ ] Negative margins (rare, but possible)

## Files Modified

1. **app/services/sales_rep_service.py** (Lines ~390-420)
   - Updated margin discipline calculation to use peer metrics
   - Added peer average margin and std dev calculation
   - Changed volatility penalty to peer-relative

2. **app/ui/dashboard.py** (Multiple sections)
   - **Driver insights** (~7050-7070): Added peer margin metrics
   - **Recommendations** (~7175-7195): Enhanced with peer comparisons
   - **PDF margin section** (~7590-7605): Shows peer comparison
   - **Component tooltip** (~8074-8079): Updated description
   - **Health Score explanation** (~7730-7750): Changed comparison scope
   - **PDF definitions** (~7650-7656): Updated margin definition

## Related Changes

### Already Category-Aware
- ✅ Sales Efficiency (GP/customer, GP/order)
- ✅ Product Mix Quality (per-category margin evaluation)
- ✅ **NEW:** Margin Discipline

### Universal Comparisons (Not Category-Aware)
- Revenue Momentum: Seasonality affects all reps equally
- Customer Health: Customer diversification is universally important

## Example Scenarios

### Scenario 1: Specialty Equipment Rep
**Before:**
- Rep margin: 28%
- Company avg: 20%
- Score: High (above company)
- Problem: Compared to wrong baseline (includes commodity reps)

**After:**
- Rep margin: 28%
- Peer avg (specialty reps): 32%
- Score: Medium (below peer group)
- Insight: "Your margin (28%) is below similar reps (32% avg). Review pricing strategy for your product categories."

### Scenario 2: High-Volatility Category
**Before:**
- Rep std dev: 18%
- Absolute threshold: >10% = penalty
- Problem: Penalized even though peers have similar volatility

**After:**
- Rep std dev: 18%
- Peer avg std dev: 16%
- Penalty: Minimal (only 2% above peer avg)
- Insight: "Your margin volatility (18%) is higher than similar reps (16%). Review pricing consistency within your product categories."

## Backward Compatibility

⚠️ **Breaking Change:** Margin Discipline scores will recalculate

**Implications:**
- Scores not directly comparable to pre-change scores
- Some reps will see scores increase (low-margin category specialists)
- Some reps may see scores decrease (were artificially high vs company avg)
- Recommend treating as "reset" for trending

**Communication:**
- Inform users scoring methodology changed
- Emphasize improved fairness
- Focus on relative ranking within new system

## Future Enhancements

### Short-Term
1. **Category Margin Targets:** Allow custom margin targets per category
2. **Weighted Category Importance:** Strategic categories could have higher weight
3. **Margin Trend Analysis:** Show margin improvement/decline over time

### Medium-Term
1. **Competitive Benchmarking:** External industry margin data by category
2. **Seasonality Adjustment:** Category-specific seasonal margin patterns
3. **Customer Profitability:** Link margin to customer health metrics

---

**Document Version:** 1.0  
**Date:** January 2026  
**Related Files:** CATEGORY_AWARE_FAIRNESS_CHANGES.md, SALES_REP_PDF_EXPORT_README.md
