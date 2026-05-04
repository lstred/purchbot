# Sales Rep Performance PDF Export - Implementation Guide

## Overview
Added professional PDF export functionality to the Sales Rep Performance dashboard. The PDF generates a comprehensive report for **ALL sales reps** with driver insights, actionable recommendations, and easy-to-understand visualizations.

## Features Implemented

### 1. **PDF Download Button**
- Located at the top of the Sales Rep Performance tab
- Generates report for all reps in one click
- In-memory generation (no file management required)
- Professional filename: `sales_rep_performance_YYYYMMDD.pdf`

### 2. **Per-Rep Sections** (1-2 pages each)
Each rep gets a dedicated section with:

#### A) Header Section
- Rep name (prominent)
- Health Score (0-100) with color-coded status
- Health Band (Healthy/Watch/At Risk/Critical)
- Time window (12 closed ISO weeks)
- Peer group size (category-similar reps)

#### B) Simple Summary (3rd Grade Reading Level)
- Overall assessment: "Doing GREAT" / "Doing OK" / "NEED IMPROVEMENT" / "URGENT ATTENTION"
- Main issues identified (e.g., "revenue trend, customer concentration")
- Written in plain, non-technical language

#### C) Score Breakdown Table
- All 5 components with scores
- Simple explanations: "What This Means"
- Color-coded rows for readability

#### D) Driver Insights (The "Why")
Detailed explanations with actual numbers:

- **Revenue Momentum:**
  - Growth % over 12 weeks
  - Trend direction (Up/Down/Flat)
  - 12-week sparkline chart (visual)
  - Best and worst weeks identified

- **Customer Health:**
  - Active customer count
  - Top 1 and Top 3 concentration %
  - Risk level (Low/Medium/High)
  - Comparison to peer average

- **Margin Discipline:**
  - Average margin %
  - Consistency rating (Good/Watch/High Risk)
  - Standard deviation
  - Lowest margin customers/categories

- **Sales Efficiency:**
  - GP per customer (category-aware)
  - GP per order (category-aware)
  - Comparison to peer group

- **Product Mix:**
  - Top 5 categories by revenue
  - Margin % for each category
  - Bar chart visualization

#### E) Actionable Recommendations (3-5 bullets)
Data-driven, specific actions tied to insights:

Examples:
- "📈 URGENT: Your revenue dropped 12.5% over 12 weeks. Focus on reactivating dormant customers..."
- "⚠️ HIGH RISK: 68% of your revenue comes from just 3 customers. Grow 3-5 mid-sized customers..."
- "💰 Your margins vary widely (std dev: 15.2%). Review pricing consistency..."
- "💡 Customer #12345 has very low margin (7.3%). Consider repricing..."
- "✨ Your best category is 'Specialty Items' with 28.5% margin. Try to grow sales..."

### 3. **Visual Elements**

#### Charts (Matplotlib)
- **Revenue Sparkline:** 12-week line chart with fill
- **Category Margin Bars:** Color-coded by performance level
  - Green: >25% margin (good)
  - Orange: 15-25% margin (medium)
  - Red: <15% margin (needs attention)

#### Color Scheme
- **Professional & Printer-Friendly**
- Blue/teal primary colors (#2E86AB, #1F4788)
- Health band colors:
  - Green (#27AE60): Healthy
  - Orange (#F39C12): Watch
  - Orange-Red (#E67E22): At Risk
  - Red (#E74C3C): Critical
- Colorblind-friendly (always paired with text labels)

#### Layout
- Clean, modern design
- Consistent typography (Helvetica)
- Whitespace for readability
- Grid lines for tables
- Value labels on charts

### 4. **Definitions Page**
Final page with simple metric definitions:
- Health Score explanation
- Category-aware comparison definition
- 12 closed weeks explanation
- Each component definition
- Emphasis on fairness and peer grouping

## Technical Implementation

### Libraries Used
1. **ReportLab:** PDF generation with precise layout control
2. **Matplotlib:** Chart generation (sparklines, bar charts)
3. **Pandas/NumPy:** Data analysis
4. **BytesIO:** In-memory PDF buffering

### Key Functions

#### `_calculate_driver_insights()`
Extracts detailed metrics for explanations:
- Weekly revenue analysis
- Customer concentration metrics
- Margin volatility
- Category performance
- Peer comparisons

**Returns:** Dict with insights for all 5 components

#### `_generate_actionable_recommendations()`
Creates 3-5 specific recommendations based on:
- Component scores (prioritizes weakest areas)
- Driver insights (uses actual numbers)
- Risk levels (concentration, volatility)
- Peer comparisons

**Logic:**
- Sorts components by score
- Generates targeted advice for scores <60
- Includes specific data points (%, $, counts)
- Limits to top 5 most impactful actions

#### `_create_matplotlib_sparkline()`
Generates 12-week revenue line chart:
- 4" x 1.5" size (fits in PDF)
- Line + filled area under curve
- Grid lines for readability
- Axis labels
- 150 DPI for quality

#### `_create_matplotlib_category_bars()`
Generates category margin comparison:
- 5" x 2.5" size
- Color-coded bars by margin level
- Truncates long category names
- Value labels on bars
- 150 DPI for quality

#### `_generate_sales_rep_pdf()`
Main PDF generation function:

**Process:**
1. Create PDF document with ReportLab
2. Build cover page with date/description
3. Calculate peer groups (once)
4. Loop through all reps:
   - Calculate insights
   - Generate recommendations
   - Build rep section (header, summary, tables, charts, actions)
   - Add page break
5. Append definitions page
6. Return BytesIO buffer

**Parameters:**
- `all_reps_data`: List of rep metrics/scores
- `df`: Full dataframe for drill-down analysis
- `all_reps_metrics`: For peer comparison
- `all_reps_rolling`: For seasonally-adjusted metrics
- `company_avg_margin`: Benchmark
- `start_date`, `end_date`: Time window

### UI Integration

**Location:** Top of Sales Rep Performance tab

**Workflow:**
1. User clicks "📄 Download All Reps PDF" button
2. Spinner shows "Generating PDF report for all reps..."
3. System:
   - Recalculates metrics for all reps
   - Generates insights for each
   - Creates recommendations
   - Builds PDF with charts
4. Download button appears: "⬇️ Download PDF Report"
5. Success message: "✅ PDF generated successfully for X reps!"

**Error Handling:**
- Try/except around PDF generation
- Shows detailed error message if failure
- Falls back gracefully if ReportLab missing

## Category-Aware Fairness (Critical!)

### Why It Matters
- Reps sell different products (specialists vs generalists)
- Global averages are misleading
- Example: High-value specialty rep vs high-volume commodity rep

### How It's Implemented

#### Peer Grouping
```python
similarity = (categories_in_common) / (total_unique_categories)
if similarity >= 0.3:  # 30% overlap
    include_as_peer
```

#### Category-Aware Metrics
- **Sales Efficiency:** GP/customer and GP/order compared within peer group
- **Product Mix:** Margin evaluated per-category vs category-specific peers

#### What's NOT Category-Aware
- **Revenue Momentum:** Seasonality affects everyone equally
- **Margin Discipline:** Company margin targets are universal
- **Customer Health:** Customer diversification is universally important

### In the PDF
- Peer group size displayed in header
- Recommendations reference "similar reps"
- Definitions page explains fairness approach

## Data Requirements

### Required Columns in DataFrame
- `salesperson`: Rep name
- `order_date`: Transaction date
- `order_number`: Unique order ID
- `account_number`: Customer ID
- `line_revenue`: Line-level revenue
- `line_gross_profit`: Line-level GP
- `product_category`: Product category
- `price_class`: Price class (optional)

### Time Window Rules
- **12 Closed ISO Weeks:** Monday-Sunday weeks only
- **Exclude Current Week:** In-progress week not included
- **Minimum Data:** Need at least 4 weeks for sparkline

### Filter Compatibility
- Respects date range filters
- Respects category filters
- Uses filtered_df throughout

## Usage Instructions

### For Managers
1. Navigate to "Sales Rep Performance" tab
2. Set desired date range (default: last 6 months)
3. Optionally filter by product categories
4. Click "📄 Download All Reps PDF"
5. Wait for generation (10-30 seconds depending on rep count)
6. Click "⬇️ Download PDF Report"
7. Review PDF offline or print for meetings

### For Developers
**To install dependencies:**
```bash
pip install reportlab matplotlib
```

**To modify recommendations logic:**
Edit `_generate_actionable_recommendations()` in `app/ui/dashboard.py`

**To change chart styles:**
Edit `_create_matplotlib_sparkline()` and `_create_matplotlib_category_bars()`

**To adjust PDF layout:**
Edit `_generate_sales_rep_pdf()` - modify ReportLab styles and table structures

## Performance Considerations

### Generation Time
- Typical: 1-2 seconds per rep
- 40 reps: ~30-60 seconds
- Bottleneck: Chart generation (matplotlib)

### Optimization Tips
1. **Cache Peer Groups:** Built once per PDF
2. **Reuse Metrics:** Already calculated for UI
3. **Async Generation:** Could add background task (future)
4. **Chart Caching:** Could cache sparklines if data unchanged

### Memory Usage
- PDF held in BytesIO (in-memory)
- Charts generated/closed immediately
- ~2-5 MB for 40 reps
- Safe for typical Streamlit deployments

## Troubleshooting

### "PDF generation requires ReportLab library"
**Solution:** Run `pip install reportlab matplotlib`

### Charts not appearing in PDF
**Cause:** Matplotlib backend issue or data insufficient
**Solution:** 
- Check `weekly_revenue` has data
- Ensure `top_categories` not empty
- Charts fail gracefully (PDF still generates)

### "Error generating PDF: ..."
**Common Causes:**
1. Missing data columns
2. Division by zero in calculations
3. Special characters in rep names
4. Insufficient peer data

**Debug:**
- Check exception details in error message
- Verify data structure with `st.write(rep_metrics)`
- Test with single rep first

### Slow PDF generation
**Solutions:**
1. Reduce date range (fewer weeks = less data)
2. Filter to specific categories
3. Check database query performance
4. Consider caching metrics

## Future Enhancements

### Short-Term
1. **Email Export:** Send PDF via email from UI
2. **Single Rep PDF:** Option to export just one rep
3. **Custom Date Range:** Per-rep date range selection
4. **Chart Options:** Toggle which charts to include

### Medium-Term
1. **Trend Analysis:** Show score changes over time
2. **Peer Comparison:** Side-by-side rep comparisons
3. **Goal Setting:** Add target scores and progress
4. **Historical PDFs:** Archive and version tracking

### Long-Term
1. **Interactive PDF:** Forms with fillable coaching notes
2. **Multi-Language:** Translate simple summaries
3. **Custom Branding:** Upload company logos/colors
4. **Dashboard Integration:** Auto-generate and distribute weekly

## Code Structure

### File Organization
```
app/ui/dashboard.py
├── Imports (reportlab, matplotlib)
├── _calculate_driver_insights()      # Lines ~7000-7100
├── _generate_actionable_recommendations()  # Lines ~7100-7200
├── _create_matplotlib_sparkline()    # Lines ~7200-7250
├── _create_matplotlib_category_bars()  # Lines ~7250-7320
├── _generate_sales_rep_pdf()         # Lines ~7320-7640
└── _build_sales_rep_performance_tab()  # Lines ~7640+
    └── PDF Download Button           # Lines ~7920-7970
```

### Dependencies
- **Internal:** `app.services.sales_rep_service`
- **External:** `reportlab`, `matplotlib`, `pandas`, `numpy`
- **Standard:** `BytesIO`, `date`, `timedelta`

## Testing Checklist

### Functional Tests
- [ ] PDF downloads successfully
- [ ] All reps included in PDF
- [ ] Charts render correctly
- [ ] Recommendations are specific (not generic)
- [ ] Health bands match UI
- [ ] Dates/time windows correct

### Visual Quality Tests
- [ ] Text readable (not too small)
- [ ] Colors professional (not garish)
- [ ] Page breaks logical
- [ ] Tables aligned
- [ ] Charts clear and labeled
- [ ] Whitespace balanced

### Data Accuracy Tests
- [ ] Scores match UI
- [ ] Driver insights use correct data
- [ ] Peer groups make sense
- [ ] Category margins accurate
- [ ] Weekly revenue trend correct

### Edge Cases
- [ ] Single rep works
- [ ] Rep with no data handled
- [ ] Missing categories graceful
- [ ] Long rep names truncated
- [ ] Special characters in names
- [ ] Zero revenue/GP handled

## Summary

**What Was Added:**
- Professional PDF export for all sales reps
- Driver insights with actual data
- Actionable recommendations (3-5 per rep)
- Visual charts (sparklines, bar charts)
- Simple explanations (3rd grade level)
- Category-aware fairness throughout

**What Was NOT Changed:**
- Dashboard UI (unchanged)
- Scoring calculations (unchanged)
- Data loading (unchanged)
- Existing tabs (unchanged)

**User Benefit:**
- One-click comprehensive reports
- Offline review and sharing
- Print-ready for meetings
- Clear action items for coaching
- Fair evaluation across different product portfolios

---

**Document Version:** 1.0  
**Implementation Date:** January 2026  
**Related Files:** CATEGORY_AWARE_FAIRNESS_CHANGES.md, SEASONALITY_FIXES_SUMMARY.md
