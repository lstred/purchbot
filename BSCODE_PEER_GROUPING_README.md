# BSCODE-Based Peer Grouping Implementation

## Overview

The sales rep health scoring system now uses **BSCODE (cost center) assignments** from the `BILLSLMN` table as the primary basis for peer grouping, replacing the previous revenue-based category overlap approach. This provides more accurate and stable peer comparisons based on official product category responsibilities rather than transient sales patterns.

## Problem Solved

**Previous Approach:** Peer grouping based on revenue_by_category with 30% Jaccard similarity threshold
- **Issue:** Too loose - treated reps as comparable when they sold very different product portfolios
- **Example:** A rep selling 30% hardware and 70% software would be grouped with a rep selling 30% hardware and 70% plumbing supplies
- **Root cause:** Used realized sales data instead of official assignment data

**New Approach:** Peer grouping based on dominant BSCODE profiles with 60% Jaccard similarity threshold
- **Source of truth:** `BILLSLMN` table (official account-to-salesperson-to-cost-center assignments)
- **Accuracy:** Compares reps based on their official product category responsibilities
- **Stability:** Assignment data changes less frequently than sales patterns

## Algorithm Details

### Step 1: Build Dominant BSCODE Profiles

For each sales rep (BSSLMN), extract their dominant cost centers (BSCODE) from `BILLSLMN` assignments:

```python
def compute_dominant_bscode_profile(rep_assignments):
    # Count accounts per BSCODE
    bscode_account_counts = count_accounts_per_bscode(rep_assignments)
    total_accounts = count_unique_accounts(rep_assignments)
    
    dominant_bscodes = set()
    for bscode, account_count in bscode_account_counts:
        pct_of_accounts = account_count / total_accounts
        
        # Include BSCODE if it meets BOTH thresholds
        if pct_of_accounts >= 0.15 AND account_count >= 3:
            dominant_bscodes.add(bscode)
    
    return dominant_bscodes
```

**Dominance Thresholds:**
- **Percentage threshold:** 15% of assigned accounts (default)
- **Count threshold:** ≥3 distinct accounts (default)
- **Logic:** BOTH conditions must be met to filter out incidental/edge-case assignments

**Rationale:**
- 15% threshold: Captures secondary specializations while filtering noise
- 3 account threshold: Prevents single-account anomalies from distorting profiles
- Adjustable via function parameters for different business contexts

### Step 2: Calculate BSCODE Similarity

Compare reps using **Jaccard similarity** on their dominant BSCODE sets only:

```python
def calculate_bscode_similarity(rep_a_bscodes, rep_b_bscodes):
    intersection = len(rep_a_bscodes & rep_b_bscodes)
    union = len(rep_a_bscodes | rep_b_bscodes)
    similarity = intersection / union if union > 0 else 0
    return similarity
```

**Similarity Threshold:** 60% (default, stricter than old 30%)
- Reps with ≥60% BSCODE overlap are considered peers
- Example: Rep A has {BSCODE1, BSCODE2, BSCODE3}, Rep B has {BSCODE2, BSCODE3, BSCODE4}
  - Intersection = {BSCODE2, BSCODE3} = 2 items
  - Union = {BSCODE1, BSCODE2, BSCODE3, BSCODE4} = 4 items
  - Similarity = 2/4 = 50% → NOT peers (below 60% threshold)

### Step 3: Form Peer Groups

For each rep, collect all reps with similarity ≥ threshold:

```python
def build_peer_groups(rep_profiles, min_peers=3, similarity_threshold=0.60):
    peer_groups = {}
    
    for rep_name, rep_bscodes in rep_profiles:
        peers = [other_rep for other_rep, other_bscodes in rep_profiles
                 if jaccard_similarity(rep_bscodes, other_bscodes) >= similarity_threshold]
        
        # Only use peer group if large enough for statistical stability
        if len(peers) >= min_peers:
            peer_groups[rep_name] = peers
        else:
            # Fallback: use all reps to avoid penalizing unique specializations
            peer_groups[rep_name] = list(rep_profiles.keys())
    
    return peer_groups
```

**Minimum Peers Requirement:** 3 (default)
- Prevents statistically unstable comparisons from small peer groups
- Reps with <3 similar peers fall back to all-reps comparison (no penalty for uniqueness)

## Metrics Using BSCODE-Based Peers

The following health score components now use BSCODE-based peer grouping:

1. **Margin Discipline (21% weight)**
   - Compares avg margin % to peer group average
   - Applies volatility penalty relative to peer volatility
   - Rationale: Margin expectations vary by product category

2. **Sales Efficiency (17% weight)**
   - GP per customer percentile within peer group
   - GP per order percentile within peer group
   - Rationale: Efficiency benchmarks depend on product mix

3. **Product Mix Quality (13% weight)**
   - Margin performance by category compared to peers
   - Rationale: Directly category-scoped by definition

4. **Account Coverage Effectiveness (15% weight)**
   - Normalized against peers with similar assignment portfolio sizes
   - Rationale: Coverage expectations scale with responsibility scope

**Not using BSCODE peers:**
- **Revenue Momentum (13%):** Seasonality affects all reps equally, uses broader comparison
- **Customer Health (21%):** Diversification principles are universal, not category-specific

## Data Sources

### Input Tables

1. **BILLSLMN** (Account Assignments)
   - `BSACCT` → account_number
   - `BSSLMN` → salesman_number
   - `BSCODE` → cost_center (product category responsibility)

2. **_ORDERS** (Sales History)
   - Used for rep name mapping (salesman_number → salesperson name)
   - Not used for peer grouping logic

### Data Pipeline

```
BILLSLMN → load_account_assignments() → DataFrame
    ↓
    └─> build_bscode_peer_groups() → Dict[rep_name → List[peer_names]]
            ↓
            └─> calculate_health_score() → Uses peers for component calculations
```

## Configuration Parameters

All thresholds are adjustable via function parameters:

| Parameter | Default | Purpose | Tuning Guidance |
|-----------|---------|---------|----------------|
| `dominance_pct_threshold` | 0.15 (15%) | Min % of accounts for BSCODE to be "dominant" | Lower = more BSCODEs included (noisier), Higher = fewer BSCODEs (stricter) |
| `dominance_count_threshold` | 3 | Min account count for BSCODE to be "dominant" | Lower = more sensitive to small assignments, Higher = more conservative |
| `similarity_threshold` | 0.60 (60%) | Min Jaccard similarity for peer inclusion | Lower = larger peer groups (looser), Higher = smaller groups (stricter) |
| `min_peers` | 3 | Min peer group size before fallback | Higher = more stable but more fallback cases |

**Recommended Starting Points:**
- **Standard business:** Use defaults (15%, 3 accounts, 60% similarity, 3 min peers)
- **Highly specialized reps:** Lower similarity_threshold to 0.50 (50%)
- **Noisy assignment data:** Raise dominance thresholds (20%, 5 accounts)
- **Small sales team:** Lower min_peers to 2

## Edge Cases Handled

1. **Rep with <5 total accounts:**
   - May have no dominant BSCODEs (all below thresholds)
   - Falls back to all-reps comparison
   - UI note: "Limited comparison group due to small assignment portfolio"

2. **Rep with multiple dominant BSCODEs:**
   - All qualifying BSCODEs are included in profile
   - Compared to other multi-category reps with similar BSCODE sets
   - Example: Rep selling both hardware (50%) and software (40%) → {HW, SW}

3. **Very small peer group (<3 reps):**
   - Automatically falls back to all-reps comparison
   - Prevents penalizing reps with unique specializations
   - Peer count shown as context only (not used for scoring)

4. **No BSCODE assignments in BILLSLMN:**
   - Falls back to legacy category-based peer grouping
   - Uses revenue_by_category from sales data
   - Logs warning for data quality investigation

5. **Rep not found in BILLSLMN:**
   - Falls back to all-reps comparison for that rep only
   - Other reps use BSCODE grouping normally
   - May indicate new rep or data sync issue

## Benefits of BSCODE-Based Approach

1. **Accuracy:** Uses official assignment data as source of truth
2. **Stability:** Assignments change less frequently than sales patterns
3. **Fairness:** Prevents apples-to-oranges comparisons between reps with different responsibilities
4. **Explainability:** Peer groups based on documented business structure
5. **Maintainability:** Single source of truth (BILLSLMN) for all peer logic
6. **Auditability:** Easy to verify "why are these reps grouped together?"

## Migration Notes

### Backward Compatibility

The system maintains the legacy `build_category_peer_groups()` function for backward compatibility:
- Marked as **DEPRECATED** in docstring
- Used automatically if BILLSLMN data is unavailable
- Falls back gracefully without breaking existing functionality

### Testing Checklist

Before deploying to production:

- [ ] Verify BILLSLMN data quality (no missing BSCODEs for active reps)
- [ ] Compare old vs new peer groups for each rep (document changes)
- [ ] Test edge cases (small teams, unique specializations, missing data)
- [ ] Validate health scores remain in reasonable ranges (0-100)
- [ ] Confirm peer counts are displayed but not used for scoring
- [ ] Check UI/PDF text uses "reps with similar product category responsibilities" wording
- [ ] Run for full sales team for at least one period
- [ ] Spot-check 5-10 reps: do their peer groups make business sense?

### Monitoring Recommendations

Monitor these metrics after deployment:

1. **Peer group size distribution:** How many reps have 3-5, 6-10, 10+ peers?
2. **Fallback frequency:** How often do reps fall back to all-reps comparison?
3. **Health score volatility:** Do scores become more stable week-over-week?
4. **Outlier detection:** Any reps with surprising peer groups?
5. **Data quality:** Any reps with no BILLSLMN assignments?

## Implementation Files

- **`app/services/sales_rep_service.py`:**
  - `build_bscode_peer_groups()` - Main peer grouping function
  - `build_category_peer_groups()` - Legacy fallback (deprecated)
  - `calculate_health_score()` - Updated to accept BSCODE peer data

- **`app/data/loaders.py`:**
  - `load_account_assignments()` - Loads and normalizes BILLSLMN data

- **`app/data/queries.py`:**
  - `ACCOUNT_ASSIGNMENTS` - SQL query for BILLSLMN table

- **`app/ui/dashboard.py`:**
  - Updated to load assignments_df and pass to health score calculations
  - Three call sites updated with new parameters

## Example Usage

```python
# Load data
assignments_df = loaders.load_account_assignments(connection_string)
salesman_map = {"123": "John Smith", "456": "Jane Doe", ...}

# Build peer groups
peer_groups = build_bscode_peer_groups(
    assignments_df=assignments_df,
    salesman_map=salesman_map,
    min_peers=3,
    dominance_pct_threshold=0.15,
    dominance_count_threshold=3,
    similarity_threshold=0.60
)

# Result: {"John Smith": ["John Smith", "Jane Doe", "Bob Johnson"], ...}

# Use in health score calculation
health_score, components = calculate_health_score(
    rep_metrics=rep_metrics,
    rolling_metrics=rolling_metrics,
    all_reps_metrics=all_reps_metrics,
    all_reps_rolling=all_reps_rolling,
    company_avg_margin=company_avg_margin,
    assignments_df=assignments_df,
    salesman_map=salesman_map
)
```

## Future Enhancements

Potential improvements for future iterations:

1. **Weighted BSCODE similarity:** Weight BSCODEs by revenue or account count
2. **Temporal peer grouping:** Adjust peer groups by season or time period
3. **Hierarchical BSCODEs:** Group related product categories (e.g., all hardware types)
4. **Multi-tier peers:** Primary peers (strict) + secondary peers (broader) for different metrics
5. **Peer group visualization:** Show BSCODE overlap diagram in UI/PDF
6. **Assignment quality scoring:** Flag reps with inconsistent sales-vs-assignment patterns

## Questions or Issues?

For questions about the BSCODE-based peer grouping implementation:
1. Review this document first
2. Check the inline comments in `sales_rep_service.py`
3. Verify data quality in BILLSLMN table
4. Test with different threshold parameters to find optimal values for your business
