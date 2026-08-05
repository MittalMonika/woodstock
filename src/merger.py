"""
merger.py — Joins the source tables together.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


class MergeError(RuntimeError):
    """Raised when a join would corrupt the data."""


def _resolve_duplicates(
    df: pd.DataFrame,
    keys: list[str],
    name: str,
    policy: str,
) -> pd.DataFrame:
    """Confirm the join keys uniquely identify rows — and handle it if they don't.

    This is THE check that prevents silently inflated numbers. If 'FIPS + Year'
    appears twice in a lookup table, joining it to HMDA duplicates every matching
    HMDA row, and the dashboard totals silently become wrong.

    There are two very different kinds of duplicate, and they need different
    treatment:

      * IDENTICAL duplicates  — the exact same row entered twice. Harmless to
        drop; the data is unchanged.

      * CONFLICTING duplicates — the same tract and year but DIFFERENT values.
        This is a genuine data-quality problem. We cannot know whether the rows
        should be summed, or whether one is erroneous. Only Woodstock can decide.

    Policy (set per-source in the config as `on_duplicate`):
      "fail"           — stop the run (default; safest)
      "drop_identical" — drop exact duplicates, but still fail on conflicting ones
      "sum"            — add the numeric columns together
      "first"          — keep the first occurrence
    """
    dupe_mask = df.duplicated(subset=keys, keep=False)
    n_dupe_rows = int(dupe_mask.sum())

    if n_dupe_rows == 0:
        log.info("  [%s] key check passed — %s uniquely identifies rows", name, keys)
        return df

    dupes = df[dupe_mask].sort_values(keys)

    # Split into identical vs conflicting
    identical_mask = df.duplicated(keep=False) & dupe_mask  # duplicated across ALL columns
    n_identical_groups = int(
        df[identical_mask].drop_duplicates(subset=keys).shape[0]
    )
    conflicting = dupes[~dupes.index.isin(df[identical_mask].index)]
    conflict_keys = conflicting.drop_duplicates(subset=keys)[keys]
    n_conflicting = len(conflict_keys)

    log.warning("")
    log.warning("  [%s] DUPLICATE JOIN KEYS FOUND — %d rows affected", name, n_dupe_rows)
    if n_identical_groups:
        log.warning("    - %d key(s) have IDENTICAL duplicate rows (safe to drop)", n_identical_groups)
    if n_conflicting:
        log.warning("    - %d key(s) have CONFLICTING rows (same key, DIFFERENT values):", n_conflicting)
        for _, row in conflict_keys.head(5).iterrows():
            log.warning("        %s", " | ".join(f"{k}={row[k]}" for k in keys))
        log.warning("      ^ These need a decision from Woodstock: sum them, or is one wrong?")
    log.warning("")

    if policy == "fail":
        raise MergeError(
            f"\n[{name}] Join keys {keys} are not unique ({n_dupe_rows} rows affected).\n"
            f"Joining as-is would DUPLICATE HMDA rows and inflate dashboard numbers.\n\n"
            f"Fix the source data, or set `on_duplicate` for this source in the config:\n"
            f"    on_duplicate: drop_identical   # drop exact dupes, fail on conflicts\n"
            f"    on_duplicate: sum              # add the numeric columns together\n"
            f"    on_duplicate: first            # keep the first row\n"
        )

    if policy == "drop_identical":
        out = df.drop_duplicates()
        still_dupe = int(out.duplicated(subset=keys).sum())
        if still_dupe:
            raise MergeError(
                f"\n[{name}] Dropped identical duplicates, but {still_dupe} CONFLICTING "
                f"duplicate key(s) remain (same key, different values).\n"
                f"These cannot be resolved automatically — Woodstock must decide whether "
                f"to sum them or correct the source.\n"
                f"To proceed anyway, set `on_duplicate: sum` or `on_duplicate: first`.\n"
            )
        log.info("  [%s] dropped %d identical duplicate rows", name, len(df) - len(out))
        return out

    if policy == "sum":
        numeric = df.select_dtypes(include="number").columns.difference(keys)
        agg = {c: "sum" if c in numeric else "first" for c in df.columns if c not in keys}
        out = df.groupby(keys, as_index=False, dropna=False).agg(agg)
        log.warning("  [%s] summed %d duplicate rows into %d", name, n_dupe_rows, len(out) - (len(df) - n_dupe_rows))
        return out

    if policy == "first":
        out = df.drop_duplicates(subset=keys, keep="first")
        log.warning("  [%s] kept first of each duplicate — dropped %d rows", name, len(df) - len(out))
        return out

    raise MergeError(f"[{name}] Unknown on_duplicate policy: {policy!r}")


def _report_match_rate(
    merged: pd.DataFrame,
    lookup_cols: list[str],
    name: str,
    min_rate: float,
) -> float:
    """Report what fraction of HMDA rows actually found a match.

    A very low match rate usually means the keys are formatted differently
    between the two tables (the classic FIPS-as-number vs FIPS-as-text bug).
    """
    if not lookup_cols:
        return 1.0

    probe = lookup_cols[0]
    matched = int(merged[probe].notna().sum())
    total = len(merged)
    rate = matched / total if total else 0.0

    msg = f"  [{name}] matched {matched:,} / {total:,} HMDA rows ({rate:.1%})"
    if rate < min_rate:
        log.warning("%s  <-- LOW MATCH RATE", msg)
        log.warning(
            "  [%s] A low match rate usually means the join keys are formatted "
            "differently between tables. Check FIPS padding and Year types.",
            name,
        )
    else:
        log.info(msg)
    return rate


def merge_all(
    tables: dict[str, pd.DataFrame],
    specs: dict[str, dict],
    validation: dict,
) -> tuple[pd.DataFrame, dict]:
    """Merge every tract/county table onto the HMDA hub.

    Returns the merged dataframe and a dict of statistics for the run report.
    """
    if "hmda" not in tables:
        raise MergeError("No 'hmda' table found — it is the hub and is required.")

    base = tables["hmda"].copy()
    start_rows = len(base)
    log.info("Starting merge from HMDA hub: %s rows", f"{start_rows:,}")

    # HMDA gives us the tract FIPS. Derive the county FIPS from it so that
    # county-level tables have something to join against.
    if "FIPS" in base.columns:
        from loader import derive_county_fips

        base["County_FIPS"] = derive_county_fips(base["FIPS"])
        log.info("  derived County_FIPS from tract FIPS (first 5 digits)")

    stats: dict[str, dict] = {}
    min_rate = float(validation.get("min_match_rate", 0.5))

    for name, spec in specs.items():
        level = spec.get("join_level")

        # The hub itself and side tables are not merged here.
        if level in ("hub", "side_table", None):
            continue
        if name not in tables:
            log.warning("  [%s] configured but not loaded — skipping", name)
            continue

        lookup = tables[name]

        # ---- decide the join keys based on the geographic level -----------
        if level == "tract":
            keys = ["FIPS", "Year"]
        elif level == "county":
            keys = ["County_FIPS", "Year"]
        else:
            raise MergeError(f"[{name}] Unknown join_level {level!r}")

        missing = [k for k in keys if k not in lookup.columns]
        if missing:
            raise MergeError(
                f"[{name}] Missing join key column(s) {missing} after normalisation. "
                f"Has: {list(lookup.columns)[:12]}"
            )

        # ---- SAFETY CHECK 1: keys must be unique in the lookup ------------
        policy = spec.get("on_duplicate", "fail")
        lookup = _resolve_duplicates(lookup, keys, name, policy)

        # ---- apply prefix so columns don't collide ------------------------
        from loader import apply_prefix

        prefix = spec.get("prefix", "")
        lookup = apply_prefix(lookup, prefix, key_cols=keys)

        value_cols = [c for c in lookup.columns if c not in keys]

        # ---- the join itself: ALWAYS a left join from HMDA ----------------
        before = len(base)
        base = base.merge(lookup, on=keys, how="left", validate="many_to_one")
        after = len(base)

        # ---- SAFETY CHECK 2: row count must not change --------------------
        if after != before:
            raise MergeError(
                f"[{name}] Row count changed during join: {before:,} -> {after:,}. "
                f"This means the join fanned out and duplicated data. Aborting."
            )

        rate = _report_match_rate(base, value_cols, name, min_rate)
        stats[name] = {
            "join_level": level,
            "keys": keys,
            "lookup_rows": len(tables[name]),
            "columns_added": len(value_cols),
            "match_rate": rate,
        }

    # ---- final validation --------------------------------------------------
    end_rows = len(base)
    if validation.get("fail_on_row_loss", True) and end_rows < start_rows:
        raise MergeError(
            f"Merged table LOST rows: {start_rows:,} -> {end_rows:,}. "
            f"HMDA rows were dropped, which should never happen with left joins."
        )
    if validation.get("fail_on_row_gain", True) and end_rows > start_rows:
        raise MergeError(
            f"Merged table GAINED rows: {start_rows:,} -> {end_rows:,}. "
            f"A join duplicated data — dashboard numbers would be inflated."
        )

    log.info(
        "Merge complete: %s rows x %s columns (row count unchanged ✓)",
        f"{end_rows:,}",
        len(base.columns),
    )

    stats["_summary"] = {
        "hmda_rows": start_rows,
        "final_rows": end_rows,
        "final_columns": len(base.columns),
    }
    return base, stats


# -----------------------------------------------------------------------------
# FORECLOSURES IS NOT MERGED
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
