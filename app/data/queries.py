from __future__ import annotations

from textwrap import dedent


ORDERS_BASE = dedent(
    """
    SELECT
        o.[ITEM_MFGR_COLOR_PAT]      AS sku,
        o.[QUANTITY_ORDERED]         AS quantity_ordered,
        o.[UNIT_OF_MEASURE]          AS unit_of_measure,
        o.[ORDER_SHIP_DATE]          AS order_ship_date,
        o.[INVOICE_SHIP_DATE]        AS invoice_ship_date,
        o.[ORDER#]                   AS order_number,
        o.[LINE#I]                   AS line_number,
        o.[ACCOUNT#I]                AS account_number,
        o.[BANK_NAME2]               AS bank_name2,
        o.[CUSTOMER_PO#]             AS customer_po,
        o.[ORDER_TYPE]               AS order_type,
        o.[RESTOCKING_CHARGE_P]      AS restocking_charge_p,
        o.[DISCOUNT_HANDLING_CHARGED]AS discount_handling_charged,
        o.[ENTENDED_PRICE_NO_FUNDS]  AS extended_price_no_funds,
        o.[ITEM_WIDTH_INCHES_IF_R]   AS item_width_inches,
        o.[N_NOT_INVENTORY]          AS not_inventory_flag,
        o.[ORDER_ENTRY_DATE_YYYYMMDD]AS order_entry_date_raw,
        o.[DETAIL_LINE_STATUS]       AS detail_line_status,
        o.[PO_ETA_DATE]              AS po_eta_date,
        o.[SUPPLIER#]                AS supplier_number,
        o.[USUAL_SUPPLIER]           AS usual_supplier,
        o.[INVOICE#]                 AS invoice_number,
        o.[SALESPERSON_DESC]         AS salesperson_desc,
        o.[COST_CENTER_DESC]         AS cost_center_desc,
        o.[CREDIT_TYPE_CODE]         AS credit_type_code,
        c.[CLDESC]                   AS credit_type_desc,
        o.[REASON_CODE]              AS reason_code,
        o.[ORDER_REASON_CODE_DESC]   AS order_reason_code_desc,
        o.[ORDER_DATE]               AS order_date,
        i.[ICCTR]                    AS cost_center,
        i.[IMFGR]                    AS item_mfgr,
        i.[IPRODL]                   AS item_prodline
    FROM dbo._ORDERS AS o
    INNER JOIN dbo.ITEM AS i
        ON i.[ItemNumber] = o.[ITEM_MFGR_COLOR_PAT]
    LEFT JOIN dbo.CLASSES AS c
        ON c.[CLCAT] = 'CC' AND c.[CLCODE] = o.[CREDIT_TYPE_CODE]
    WHERE o.[N_NOT_INVENTORY] = 'Y'
      AND i.[IINVEN] = 'Y'
    """
)


# Restocking fees recorded in OPENPO_M (flat fee lines)
OPENPO_M_RESTOCK_FEES = dedent(
    """
    SELECT
        m.[M@REF#]   AS order_number,
        m.[M@LINE]   AS line_number,
        m.[M@GL#]    AS gl_number,
        m.[M@MISP]   AS fee_amount
    FROM dbo.OPENPO_M AS m
    WHERE m.[M@GL#] = 9140
    """
)


# OPENPO_M lines (includes message lines for returns)
OPENPO_M_LINES = dedent(
    """
    SELECT
        m.[M@REF#]   AS order_number,
        m.[M@LINE]   AS line_number,
        m.[M@GL#]    AS gl_number,
        m.[M@MISP]   AS fee_amount,
        m.[M@MSG]    AS message_text
    FROM dbo.OPENPO_M AS m
    """
)


# Open Orders listing with fields required for the Open Orders UI section
OPEN_ORDERS_LIST = dedent(
    """
    SELECT
        o.[LINE_GPP_WITH_FUNDS]         AS line_gpp_with_funds,
        o.[ORDER_REFERENCE#]            AS order_reference,
        o.[ITEM_MFGR_COLOR_PAT]         AS item_mfgr_color_pat,
        o.[ITEM_DESC_1]                 AS item_desc_1,
        o.[QUANTITY_ORDERED]            AS quantity_ordered,
        o.[ORDER_SHIP_DATE]             AS order_ship_date,
        o.[PRICE_PER_UM]                AS price_per_um,
        o.[COST_PER_UM]                 AS cost_per_um,
        o.[UNIT_OF_MEASURE]             AS unit_of_measure,
        o.[ENTENDED_PRICE_NO_FUNDS]     AS extended_price_no_funds,
        o.[BANK_NAME2]                  AS bank_name2,
        o.[SALESPERSON_DESC]            AS salesperson_desc,
    o.[DETAIL_LINE_STATUS]          AS detail_line_status,
        o.[SUPPLIER#]                   AS supplier_number,
        o.[ACCOUNT#I]                   AS account_number,
        o.[ORDER_ENTRY_DATE_YYYYMMDD]   AS order_entry_date_raw,
        i.[ICCTR]                       AS cost_center
    FROM dbo._ORDERS AS o
    INNER JOIN dbo.ITEM AS i
        ON i.[ItemNumber] = o.[ITEM_MFGR_COLOR_PAT]
    WHERE o.[N_NOT_INVENTORY] = 'Y'
      AND i.[IINVEN] = 'Y'
    """
)


ITEMS = dedent(
    """
    SELECT
        [ItemNumber]        AS sku,
        [IPRCCD]            AS price_class,
        [ICCTR]             AS cost_center,
        [IPRODL]            AS product_line,
        [IMFGR]             AS manufacturer,
        [INAME]             AS sku_description,
        [IPATT]             AS item_pattern,
        [ISUPP#]            AS supplier_number,
        [IDELIV]            AS item_lead_time_days,
        [IWIDTH]            AS item_width_inches,
        [IINVEN]            AS inventory_flag,
        [IIXREF]            AS iixref
    FROM dbo.ITEM
    WHERE [IINVEN] = 'Y'
    """
)


PRICE_CLASSES = dedent(
    """
    SELECT
        [$PRCCD] AS price_class,
        [$DESC]  AS price_class_desc
    FROM dbo.PRICE
    WHERE [$LIST#] = 'LP'
    """
)


ITEMS_ALL = dedent(
    """
    SELECT
        [ItemNumber]        AS sku,
        [IPRCCD]            AS price_class,
        [ICCTR]             AS cost_center,
        [IPRODL]            AS product_line,
        [IMFGR]             AS manufacturer,
        [INAME]             AS sku_description,
        [IPATT]             AS item_pattern,
        [ISUPP#]            AS supplier_number,
        [IDELIV]            AS item_lead_time_days,
        [IWIDTH]            AS item_width_inches,
        [IINVEN]            AS inventory_flag,
        [IIXREF]            AS iixref,
        [IDISCD]            AS discontinued_flag
    FROM dbo.ITEM
    WHERE TRY_CONVERT(int, NULLIF(LTRIM(RTRIM([IDISCD])), '')) = 0
    """
)


PRODUCT_LINES = dedent(
    """
    SELECT
        [LPROD#] AS product_line,
        [LMFGR#] AS manufacturer,
        [LNAME]  AS product_line_desc,
        TRY_CONVERT(decimal(10, 2), NULLIF(LTRIM(RTRIM([LDELIV])), '')) AS product_line_lead_time_days
    FROM dbo.PRODLINE
    """
)


ITEMSTK = dedent(
    """
    SELECT
        [ItemNumber] AS sku,
        TRY_CONVERT(decimal(18, 2), NULLIF(LTRIM(RTRIM([JSTOCK])), '')) AS jstock
    FROM dbo.ITEMSTK
    """
)


ROLLS = dedent(
    """
    SELECT
        r.[ItemNumber] AS sku,
        r.[Available]  AS available_quantity,
        r.[RUM]        AS unit_of_measure,
        r.[RROLL#]     AS roll_number,
        r.[RLOC1]      AS location,
                r.[RCODE@]     AS status_code,
                r.[RLRCTD]     AS receive_date
    FROM dbo.ROLLS AS r
    WHERE r.[Available] > 0
      AND ISNULL(r.[RLOC1], '') <> 'REM'
      AND ISNULL(r.[RCODE@], '#') <> '#'
      AND r.[ItemNumber] IN (SELECT i.[ItemNumber] FROM dbo.ITEM AS i WHERE i.[IINVEN] = 'Y')
    """
)


OPEN_RECEIPTS = dedent(
    """
    SELECT
        [NREFTY] AS ref_type,
        [NDATE]  AS receipt_date,
        [NPO#]   AS purchase_order_number,
        [NRECEI] AS quantity_received,
        [NMFGR]  AS mfgr_part,
        [NCOLOR] AS color_part,
        [NPAT]   AS pattern_part
    FROM dbo.OPENIV
    WHERE [NREFTY] = 'R'
    """
)


PURCHASE_ORDERS = dedent(
    """
    SELECT
        o.[ITEM_MFGR_COLOR_PAT]      AS sku,
        o.[QUANTITY_ORDERED]         AS quantity_ordered,
        o.[UNIT_OF_MEASURE]          AS unit_of_measure,
        o.[PO_ETA_DATE]              AS eta_date,
        o.[ORDER#]                   AS order_number,
        o.[LINE#I]                   AS line_number,
        o.[ACCOUNT#I]                AS account_number,
        o.[ITEM_WIDTH_INCHES_IF_R]   AS item_width_inches,
        o.[N_NOT_INVENTORY]          AS not_inventory_flag,
        o.[ORDER_ENTRY_DATE_YYYYMMDD]AS order_entry_date_raw,
        o.[SUPPLIER#]                AS supplier_number,
        i.[ICCTR]                    AS cost_center
    FROM dbo._ORDERS AS o
    INNER JOIN dbo.ITEM AS i
        ON i.[ItemNumber] = o.[ITEM_MFGR_COLOR_PAT]
    WHERE o.[N_NOT_INVENTORY] = 'Y'
      AND o.[ACCOUNT#I] = 1
      AND i.[IINVEN] = 'Y'
      AND TRY_CONVERT(int, LTRIM(RTRIM(o.[ORDER#]))) > 0
    """
)


COST_CENTERS = dedent(
    """
    SELECT DISTINCT
        [ICCTR] AS cost_center
    FROM dbo.ITEM
    WHERE [IINVEN] = 'Y'
    ORDER BY [ICCTR]
    """
)


# Partially received POs from OPENPO_D
OPENPO_D_PARTIALS = dedent(
    """
    SELECT
        [D@MFGR] AS mfgr,
        [D@COLO] AS colo,
        [D@PATT] AS patt,
        [D@QTYO] AS qty_ordered,
        [D@QTYP] AS qty_posted,
        [D@ACCT] AS acct,
        [D@DEL8] AS del8
    FROM dbo.OPENPO_D
    WHERE TRY_CONVERT(int, NULLIF(LTRIM(RTRIM([D@ACCT])), '')) = 1
      AND ISNULL([D@DEL8], '') <> '#'
      AND TRY_CONVERT(decimal(18, 4), NULLIF(LTRIM(RTRIM([D@QTYP])), '')) > 0
    """
)

# Pending POs from OPENPO_D (all matching rows), with supplier filtering
OPENPO_D_PENDING = dedent(
        """
        SELECT
                [D@MFGR] AS mfgr,
                [D@COLO] AS colo,
                [D@PATT] AS patt,
                [D@QTYO] AS qty_ordered,
                [D@QTYP] AS qty_posted,
                [D@ACCT] AS acct,
                [D@DEL8] AS del8,
                [D@SUPP] AS supp
        FROM dbo.OPENPO_D
        WHERE TRY_CONVERT(int, NULLIF(LTRIM(RTRIM([D@ACCT])), '')) = 1
            AND ISNULL([D@DEL8], '') <> '#'
            AND LTRIM(RTRIM(ISNULL([D@SUPP], ''))) <> '001'
            AND TRY_CONVERT(int, LTRIM(RTRIM([D@REF#]))) > 0
        """
)

# Dropped items - items with DI in IPOL1, IPOL2, or IPOL3 fields
DROPPED_ITEMS = dedent(
    """
    SELECT
        [ItemNumber]        AS sku,
        [INAME]             AS sku_description,
        [IMFGR]             AS manufacturer,
        [IDISCD]            AS discontinued_date_raw,
        [ICCTR]             AS cost_center,
        [IPRCCD]            AS price_class,
        [IPRODL]            AS product_line,
        [ISUPP#]            AS supplier_number
    FROM dbo.ITEM
    WHERE (
        LTRIM(RTRIM(ISNULL([IPOL1], ''))) = 'DI'
        OR LTRIM(RTRIM(ISNULL([IPOL2], ''))) = 'DI'
        OR LTRIM(RTRIM(ISNULL([IPOL3], ''))) = 'DI'
    )
    AND TRY_CONVERT(int, NULLIF(LTRIM(RTRIM([IDISCD])), '')) > 0
    """
)

# Supplier Performance - sales by supplier with date and item details
SUPPLIER_PERFORMANCE = dedent(
    """
    SELECT
        o.[USUAL_SUPPLIER]              AS supplier_number,
        o.[ITEM_CLASS_1_DESC]           AS item_class_1_desc,
        o.[ITEM_CLASS_2_DESC]           AS item_class_2_desc,
        o.[ITEM_CLASS_3_DESC]           AS item_class_3_desc,
        o.[SALESPERSON_DESC]            AS salesperson_desc,
        o.[ITEM_MFGR_COLOR_PAT]         AS sku,
        o.[ITEM_DESC_1]                 AS item_description,
        o.[ENTENDED_PRICE_NO_FUNDS]     AS extended_price_usd,
        o.[LINE_GPD_WITHOUT_FUNDS]      AS gross_profit_usd,
        o.[INVOICE_DATE_YYYYMMDD]       AS invoice_date_raw,
        o.[INVOICE_SHIP_DATE]           AS invoice_ship_date,
        i.[ICCTR]                       AS cost_center,
        o.[COST_CENTER_DESC]            AS cost_center_desc,
        i.[IMFGR]                       AS manufacturer,
        i.[IPRCCD]                      AS price_class,
        i.[IINVEN]                      AS inventory_flag,
        p.[$DESC]                       AS price_class_desc,
        o.[BANK_NAME2]                  AS bank_name,
        o.[ACCOUNT#I]                   AS account_number
    FROM dbo._ORDERS AS o
    INNER JOIN dbo.ITEM AS i
        ON i.[ItemNumber] = o.[ITEM_MFGR_COLOR_PAT]
    LEFT JOIN dbo.PRICE AS p
        ON p.[$PRCCD] = i.[IPRCCD]
        AND p.[$LIST#] = 'LP'
    WHERE o.[USUAL_SUPPLIER] IS NOT NULL
      AND LTRIM(RTRIM(o.[USUAL_SUPPLIER])) <> ''
      AND TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(o.[INVOICE#])), '')) > 0
      AND TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(o.[ACCOUNT#I])), '')) > 1
    """
)

# Inventory costs for ROI calculation
INVENTORY_COSTS = dedent(
    """
    SELECT
        inv.[Item]                      AS sku,
        i.[IPRCCD]                      AS price_class,
        p.[$DESC]                       AS price_class_desc,
        TRY_CONVERT(decimal(18, 2), NULLIF(LTRIM(RTRIM(inv.[TotalCost])), '')) AS total_cost
    FROM dbo._INVENTORY AS inv
    INNER JOIN dbo.ITEM AS i
        ON i.[ItemNumber] = inv.[Item]
    LEFT JOIN dbo.PRICE AS p
        ON p.[$PRCCD] = i.[IPRCCD]
        AND p.[$LIST#] = 'LP'
    WHERE i.[IINVEN] = 'Y'
      AND TRY_CONVERT(decimal(18, 2), NULLIF(LTRIM(RTRIM(inv.[TotalCost])), '')) > 0
    """
)

# Sales Rep Performance - order-level data for rep analysis
SALES_REP_ORDERS = dedent(
    """
    SELECT
        o.[ORDER#]                                                      AS order_number,
        o.[LINE#I]                                                      AS line_number,
        o.[ORDER_DATE_MMDDYY]                                           AS order_date_mmddyy,
        o.[ACCOUNT#I]                                                   AS account_number,
        o.[BANK_NAME2]                                                  AS customer_name,
        o.[SALESPERSON_DESC]                                            AS salesperson,
        TRY_CONVERT(decimal(18, 2), o.[ENTENDED_PRICE_NO_FUNDS])       AS line_revenue,
        TRY_CONVERT(decimal(18, 2), o.[LINE_GPD_WITHOUT_FUNDS])        AS line_gross_profit,
        TRY_CONVERT(decimal(18, 4), o.[COST_PER_UM])                   AS line_cost_per_unit,
        TRY_CONVERT(decimal(18, 4), o.[QUANTITY_ORDERED])              AS quantity_ordered,
        o.[ITEM_MFGR_COLOR_PAT]                                         AS item_number,
        o.[ITEM_CLASS_1_DESC]                                           AS product_category,
        i.[IPRCCD]                                                      AS price_class,
        p.[$DESC]                                                       AS price_class_desc
    FROM dbo._ORDERS AS o
    INNER JOIN dbo.ITEM AS i
        ON i.[ItemNumber] = o.[ITEM_MFGR_COLOR_PAT]
    LEFT JOIN dbo.PRICE AS p
        ON p.[$PRCCD] = i.[IPRCCD]
        AND p.[$LIST#] = 'LP'
    WHERE TRY_CONVERT(int, o.[ORDER#]) IS NOT NULL
      AND TRY_CONVERT(int, o.[ORDER#]) > 0
      AND o.[SALESPERSON_DESC] IS NOT NULL
      AND LTRIM(RTRIM(ISNULL(o.[SALESPERSON_DESC], ''))) <> ''
      AND TRY_CONVERT(int, o.[ACCOUNT#I]) > 1
      AND TRY_CONVERT(decimal(18, 2), o.[ENTENDED_PRICE_NO_FUNDS]) IS NOT NULL
    """
)


# Account assignment data for coverage effectiveness metric
ACCOUNT_ASSIGNMENTS = dedent(
    """
    SELECT
        BSACCT  AS account_number,
        BSSLMN  AS salesman_number,
        BSCODE  AS cost_center
    FROM dbo.BILLSLMN
    WHERE BSACCT IS NOT NULL
      AND BSSLMN IS NOT NULL
      AND BSCODE IS NOT NULL
      AND LTRIM(RTRIM(BSACCT)) <> ''
      AND LTRIM(RTRIM(BSSLMN)) <> ''
      AND LTRIM(RTRIM(BSCODE)) <> ''
    """
)


# CCA account membership from BILL_CD (MP category)
CCA_ACCOUNT_GROUPS = dedent(
    """
    SELECT
        BCACCT AS account_number,
        BCCODE AS group_code,
        BCCAT  AS category_code
    FROM dbo.BILL_CD
    WHERE LTRIM(RTRIM(ISNULL(BCCAT, ''))) = 'MP'
      AND LTRIM(RTRIM(ISNULL(BCCODE, ''))) IN ('ACA', 'ACP', 'AC1')
      AND LTRIM(RTRIM(ISNULL(BCACCT, ''))) <> ''
    """
)


# CCA sales source (order-line sales) without inventory-only item filtering.
# This preserves historical sales lines that may no longer map to current inventory items.
CCA_SALES_ORDERS = dedent(
    """
    SELECT
        o.[ORDER#]                    AS order_number,
        o.[LINE#I]                    AS line_number,
        o.[ACCOUNT#I]                 AS account_number,
        o.[BANK_NAME2]                AS bank_name2,
        o.[SALESPERSON_DESC]          AS salesperson_desc,
        o.[ENTENDED_PRICE_NO_FUNDS]   AS extended_price_no_funds,
        o.[INVOICE#]                  AS invoice_number,
        o.[ORDER_ENTRY_DATE_YYYYMMDD] AS order_entry_date_raw,
        o.[ORDER_SHIP_DATE]           AS order_ship_date,
        o.[INVOICE_SHIP_DATE]         AS invoice_ship_date,
        o.[COST_CENTER_DESC]          AS cost_center_desc,
        i.[ICCTR]                     AS cost_center,
        o.[ITEM_MFGR_COLOR_PAT]       AS sku
    FROM dbo._ORDERS AS o
    LEFT JOIN dbo.ITEM AS i
        ON i.[ItemNumber] = o.[ITEM_MFGR_COLOR_PAT]
    WHERE TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(o.[ORDER#])), '')) > 0
      AND TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(o.[ACCOUNT#I])), '')) > 1
      AND TRY_CONVERT(decimal(18,2), NULLIF(LTRIM(RTRIM(o.[ENTENDED_PRICE_NO_FUNDS])), '')) IS NOT NULL
    """
)
