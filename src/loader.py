"""
loader.py — Reads source files and normalises them.

"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def _clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace from every column name.

    The raw files contain 'Year ' (with a trailing space) in Small Business and
    Bank Branches, but 'Year' in ACS. These look identical to a human and are
    completely different to pandas.
    """
    original = list(df.columns)
    df.columns = [str(c).strip() for c in df.columns]
    changed = [(o, n) for o, n in zip(original, df.columns) if str(o) != n]
    if changed:
        for old, new in changed:
            log.debug("  cleaned header: %r -> %r", old, new)
    return df


def normalise_year(series: pd.Series, source_name: str) -> pd.Series:
    """Force a Year column to a nullable integer.

    """
    before_dtype = series.dtype
    out = pd.to_numeric(series, errors="coerce").astype("Int64")

    n_bad = int(out.isna().sum() - series.isna().sum())
    if n_bad > 0:
        log.warning(
            "  [%s] %d Year values could not be parsed as numbers and became null",
            source_name,
            n_bad,
        )
    if str(before_dtype) != str(out.dtype):
        log.info("  [%s] Year: %s -> %s", source_name, before_dtype, out.dtype)
    return out


def normalise_fips(series: pd.Series, width: int, source_name: str) -> pd.Series:
    """
    width=11 for census-tract FIPS  (e.g. 17031010100)
    width=5  for county FIPS        (e.g. 17031)
    """
    # Convert via numeric first to strip any float artefacts (e.g. 17031.0)
    numeric = pd.to_numeric(series, errors="coerce")

    out = numeric.apply(
        lambda v: str(int(v)).zfill(width) if pd.notna(v) else pd.NA
    ).astype("string")

    # Any value that wasn't numeric at all — fall back to the raw string
    mask_failed = out.isna() & series.notna()
    if mask_failed.any():
        out[mask_failed] = (
            series[mask_failed].astype("string").str.strip().str.zfill(width)
        )

    n_null = int(out.isna().sum())
    if n_null:
        log.warning("  [%s] %d FIPS values are null", source_name, n_null)

    # Sanity check the width
    lengths = out.dropna().str.len().value_counts()
    if len(lengths) > 1:
        log.warning(
            "  [%s] FIPS codes have inconsistent lengths: %s",
            source_name,
            dict(lengths),
        )

    return out


def derive_county_fips(tract_fips: pd.Series) -> pd.Series:
    
    return tract_fips.str[:5].astype("string")


def load_source(
    input_dir: Path,
    name: str,
    spec: dict,
) -> pd.DataFrame:
    """Load one source file and normalise its keys.

    `spec` is the block from the YAML config describing this file.
    """
    path = input_dir / spec["file"]
    fmt = spec.get("format", "excel")

    if not path.exists():
        raise FileNotFoundError(
            f"[{name}] Expected file not found: {path}\n"
            f"        Check 'paths.input_dir' and the 'file' entry in the config."
        )

    log.info("Loading [%s] from %s", name, path.name)

    if fmt == "csv":
        # low_memory=False avoids pandas guessing dtypes differently per chunk,
        # which matters for the large HMDA file.
        df = pd.read_csv(path, low_memory=False)
    else:
        sheet = spec.get("sheet", 0)
        df = pd.read_excel(path, sheet_name=sheet)

    df = _clean_headers(df)
    log.info("  %s rows x %s cols", f"{len(df):,}", len(df.columns))

    # --- normalise the year key -------------------------------------------
    ycol = spec.get("year_column")
    if ycol:
        if ycol not in df.columns:
            raise KeyError(
                f"[{name}] Configured year_column {ycol!r} not found.\n"
                f"        Available columns: {list(df.columns)[:15]}"
            )
        df[ycol] = normalise_year(df[ycol], name)
        # Standardise the name so downstream code doesn't care what it was called
        if ycol != "Year":
            df = df.rename(columns={ycol: "Year"})

    # --- normalise the tract FIPS key -------------------------------------
    fcol = spec.get("fips_column")
    if fcol:
        if fcol not in df.columns:
            raise KeyError(
                f"[{name}] Configured fips_column {fcol!r} not found.\n"
                f"        Available columns: {list(df.columns)[:15]}"
            )
        df[fcol] = normalise_fips(df[fcol], width=11, source_name=name)
        if fcol != "FIPS":
            df = df.rename(columns={fcol: "FIPS"})

    # --- normalise the county FIPS key ------------------------------------
    ccol = spec.get("county_fips_column")
    if ccol:
        if ccol not in df.columns:
            raise KeyError(
                f"[{name}] Configured county_fips_column {ccol!r} not found.\n"
                f"        Available columns: {list(df.columns)[:15]}"
            )
        df[ccol] = normalise_fips(df[ccol], width=5, source_name=name)
        if ccol != "County_FIPS":
            df = df.rename(columns={ccol: "County_FIPS"})

    return df


def apply_prefix(df: pd.DataFrame, prefix: str, key_cols: list[str]) -> pd.DataFrame:
    """Prefix every non-key column to avoid name collisions after merging.

    Without this, ACS's 'Income' would overwrite HMDA's 'Income' (or pandas
    would create 'Income_x' / 'Income_y', which is confusing in Tableau).
    """
    if not prefix:
        return df
    renames = {
        c: f"{prefix}{c}" for c in df.columns if c not in key_cols
    }
    return df.rename(columns=renames)
