# Sales Rep Performance Dashboard

## Overview

A comprehensive sales representative performance analysis dashboard built using industry-standard distributor metrics. This feature provides real-time insights into rep effectiveness, customer health, and sales efficiency.

## Key Features

### 1. Rep Health Score (0-100)
A weighted composite score that evaluates rep performance across 5 dimensions:

- **Revenue Momentum (25%)**: 3-month rolling revenue growth vs prior period
- **Margin Discipline (25%)**: Average margin % vs company average, with penalty for high volatility
- **Customer Health (20%)**: Active customer count, revenue per customer, and concentration risk
- **Sales Efficiency (15%)**: Average order value and gross profit per order
- **Product Mix Quality (15%)**: Currently uses margin discipline as proxy (can be enhanced with category-specific benchmarks)

### Health Bands
- **80-100**: Healthy (Green)
- **60-79**: Watch (Orange)
- **40-59**: At Risk (Orange-Red)
- **<40**: Critical (Red)

### 2. Core Metrics

**Financial Performance**
- Total Revenue
- Total Gross Profit
- Average Margin %
- Orders Count

**Customer Insights**
- Active Customer Count
- Revenue per Customer
- Gross Profit per Customer
- New vs Existing Customer Revenue Mix (90-day window)

**Growth Trends**
- 3-Month Rolling Revenue Trend
- 3-Month Rolling Margin Trend
- Month-over-Month Growth Rates

**Risk Indicators**
- Customer Concentration Risk (Top 1 & Top 3)
- Margin Consistency (Standard Deviation)

**Sales Efficiency**
- Average Order Value
- Average Gross Profit per Order

**Product Mix**
- Revenue by Product Category
- Margin by Product Category

### 3. Dashboard Sections

#### A. Rep Health Overview
- Health score with component breakdown
- Key financial metrics
- Visual indicators for performance bands

#### B. Trend Diagnostics
- 3-month rolling revenue chart
- 3-month rolling margin chart
- Growth metrics and customer acquisition stats

#### C. Customer Risk & Concentration
- Customer count and revenue metrics
- Concentration risk indicators
- Margin consistency analysis

#### D. Product Mix & Margin Quality
- Revenue distribution by category
- Category-level margin performance
- Visual bar charts with color-coded margins

#### E. Sales Efficiency
- Order value metrics
- Profitability per transaction

#### F. All Reps Comparison
- Sortable table with all rep metrics
- Health score rankings
- Downloadable CSV export
- Automatic flagging of at-risk reps

## Data Requirements

### Critical Data Rules

1. **Order Validity Filter**
   - Excludes records where ORDER# is NULL, blank, or equals 0
   - Filter applied before any aggregation

2. **Order vs Line Logic**
   - Uses order-level data for revenue and margin calculations
   - Order lines used only for product/SKU detail

3. **Date Handling**
   - ORDER_DATE_MMDDYY stored as numeric MMDDYY value
   - Automatically converted to proper date format
   - All metrics grouped by calendar month
   - Supports rolling 3-month windows

4. **Sales Rep Attribution**
   - Rep from _Orders.SALESPERSON_DESC
   - One rep per order (transactional truth)

5. **Customer Identification**
   - Customer ID = _Orders.ACCOUNT#I
   - BANK_NAME2 used for display names

6. **Margin Handling**
   - Order-level margin is source of truth
   - Line-level margin only for product/category analysis

### Database Tables Used

**_Orders**
- ORDER#, LINE#I
- ORDER_DATE_MMDDYY
- ACCOUNT#I, BANK_NAME2
- SALESPERSON_DESC
- ENTENDED_PRICE_NO_FUNDS (Revenue)
- LINE_GPD_WITHOUT_FUNDS (Gross Profit)
- COST_PER_UM, QUANTITY_ORDERED
- ITEM_MFGR_COLOR_PAT (Item Number)
- ITEM_CLASS_1_DESC (Product Category)

**ITEM**
- ItemNumber
- IPRCCD (Price Class)

**PRICE**
- $PRCCD (Price Class Code)
- $DESC (Price Class Description)

## Usage

### Accessing the Dashboard
1. Navigate to the "Sales Rep Performance" tab in the main dashboard
2. Select a sales rep from the sidebar dropdown
3. Choose a date range (default: last 6 months)
4. Optionally filter by product categories

### Interpreting Results

**Health Score Components**
- Review each component score to identify strengths and weaknesses
- Scores below 50 in any component indicate areas needing attention

**Trend Analysis**
- Upward trends in revenue and margin are positive indicators
- Flat or declining trends warrant investigation

**Customer Concentration**
- Top customer >40% of revenue = high risk
- Top 3 customers >60% of revenue = high concentration risk

**Margin Consistency**
- Std Dev <5% = Excellent consistency
- Std Dev 5-15% = Moderate consistency
- Std Dev >15% = High volatility (pricing review needed)

### Best Practices

1. **Regular Monitoring**
   - Review health scores weekly
   - Track month-over-month trends
   - Monitor at-risk reps (score <60)

2. **Coaching Opportunities**
   - Low margin discipline: Review pricing strategy
   - Low customer health: Focus on customer acquisition
   - Low efficiency: Analyze order patterns and product mix

3. **Comparative Analysis**
   - Use "All Reps Comparison" to identify top performers
   - Benchmark against company averages
   - Share best practices from high-scoring reps

4. **Data Export**
   - Download comparison data for offline analysis
   - Track historical health scores over time
   - Create custom reports for management

## Technical Implementation

### Files Modified/Created

1. **app/data/queries.py**
   - Added SALES_REP_ORDERS query

2. **app/data/loaders.py**
   - Added load_sales_rep_orders() function
   - Handles MMDDYY date conversion

3. **app/services/sales_rep_service.py** (NEW)
   - calculate_rep_metrics()
   - calculate_rolling_metrics()
   - calculate_new_vs_existing_customers()
   - calculate_health_score()
   - get_health_band()

4. **app/ui/dashboard.py**
   - Added "Sales Rep Performance" tab
   - _build_sales_rep_performance_tab() function
   - Comprehensive visualizations and metrics

### Dependencies

All required packages are already included in the project:
- pandas: Data manipulation
- numpy: Numerical calculations
- streamlit: Dashboard UI
- plotly: Interactive charts

## Assumptions & Edge Cases

### Partial Months
- Metrics calculated for full date range specified
- Rolling windows require minimum 1 month of data

### New Reps
- Health score components normalize against all reps
- Reps with <3 months data may show incomplete rolling trends
- Customer health percentile calculated only if multiple reps exist

### Low-Volume Reps
- Metrics still calculated but may be less meaningful
- Health score components handle zero/null values gracefully
- Concentration risk may appear high for reps with few customers

### Data Gaps
- Missing dates handled by pandas datetime functions
- Zero revenue/GP orders excluded from margin calculations
- Empty product categories handled with fallback logic

## Future Enhancements

1. **Product Mix Quality**
   - Implement category-specific margin benchmarks
   - Compare rep's category mix to company averages
   - Weight by strategic product importance

2. **Predictive Analytics**
   - Forecast future health scores based on trends
   - Alert on deteriorating performance patterns
   - Recommend corrective actions

3. **Goal Setting**
   - Allow custom health score targets by rep
   - Track progress toward goals
   - Incentive alignment tracking

4. **Historical Tracking**
   - Store health scores over time
   - Year-over-year comparisons
   - Trend analysis beyond rolling windows

5. **Drill-Down Analysis**
   - Click-through to customer-level detail
   - Order-level margin variance analysis
   - Product-level performance within rep

## Support

For questions or issues with the Sales Rep Performance dashboard, please contact the development team or refer to the main README.md for general troubleshooting steps.
