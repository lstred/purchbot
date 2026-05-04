from __future__ import annotations

import pandas as pd


def assign_sku_ratings(
    df: pd.DataFrame,
    value_column: str,
    rating_column: str = "sku_rating",
    count_column: str | None = None,
) -> pd.DataFrame:
    """Assign A-D ratings based on ordinal quartiles of the supplied metric."""

    if df.empty or value_column not in df.columns:
        df[rating_column] = pd.Series(dtype="object")
        if count_column and count_column in df.columns:
            df[count_column] = df[count_column].fillna(0).astype(int)
        return df

    metrics = pd.to_numeric(df[value_column], errors="coerce").fillna(0)

    # Force non-positive counts to D per spec, and compute quartiles only among positives
    positive_mask = metrics > 0
    if positive_mask.sum() == 0:
        df[rating_column] = "D"
        if count_column and count_column in df.columns:
            df[count_column] = df[count_column].fillna(0).astype(int)
        return df

    # Rank only the positive-count rows by descending value and assign ordinal quartiles
    pos_metrics = metrics[positive_mask]
    sorted_idx = pos_metrics.sort_values(ascending=False).index
    n_pos = len(sorted_idx)

    # Determine position cutoffs for quartiles using ceiling to ensure top item(s) get A
    import math
    a_cut = max(1, math.ceil(0.25 * n_pos))
    b_cut = max(a_cut, math.ceil(0.50 * n_pos))
    c_cut = max(b_cut, math.ceil(0.75 * n_pos))

    ratings = pd.Series("D", index=metrics.index, dtype="object")
    for position, idx in enumerate(sorted_idx, start=1):
        if position <= a_cut:
            rating = "A"
        elif position <= b_cut:
            rating = "B"
        elif position <= c_cut:
            rating = "C"
        else:
            rating = "D"
        ratings.loc[idx] = rating

    # Non-positive already default to D
    df[rating_column] = ratings.values
    if count_column and count_column in df.columns:
        df[count_column] = df[count_column].fillna(0).astype(int)
    return df
