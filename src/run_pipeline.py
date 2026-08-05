#!/usr/bin/env python3
"""
run_pipeline.py — Woodstock Institute Tableau extract builder.

WHAT THIS DOES
--------------

USAGE
-----
    python run_pipeline.py --config ../config/illinois.yml

    # dry run — validate everything without writing the extract
    python run_pipeline.py --config ../config/illinois.yml --dry-run

    # more detail in the logs
    python run_pipeline.py --config ../config/illinois.yml --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

# Make the sibling modules (loader, merger, hyper_writer) importable no matter
# how this file is launched — as a script, as a module, or from any working
# directory. Without this, `python -m src.run_pipeline` and some IDE run-buttons
# fail with "ModuleNotFoundError: No module named 'loader'".
sys.path.insert(0, str(Path(__file__).resolve().parent))

from loader import load_source
from merger import MergeError, merge_all
from hyper_writer import write_hyper


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
def setup_logging(verbose: bool, log_dir: Path | None = None) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s  %(levelname)-7s  %(message)s"
    datefmt = "%H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        handlers.append(logging.FileHandler(log_dir / f"pipeline_{stamp}.log"))

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)


log = logging.getLogger("pipeline")


# -----------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def filter_years(df: pd.DataFrame, start: int, end: int, name: str) -> pd.DataFrame:
    """Keep only the configured year range."""
    if "Year" not in df.columns:
        return df
    before = len(df)
    out = df[(df["Year"] >= start) & (df["Year"] <= end)].copy()
    dropped = before - len(out)
    if dropped:
        log.info("  [%s] dropped %s rows outside %d-%d", name, f"{dropped:,}", start, end)
    return out


def print_report(stats: dict, output: Path | None, side_tables: dict) -> None:
    """Human-readable summary — this is what someone checks after a run."""
    summary = stats.get("_summary", {})

    print()
    print("=" * 68)
    print("  PIPELINE REPORT")
    print("=" * 68)
    print(f"  HMDA rows in  : {summary.get('hmda_rows', 0):,}")
    print(f"  Final rows out: {summary.get('final_rows', 0):,}")
    print(f"  Final columns : {summary.get('final_columns', 0):,}")

    if summary.get("hmda_rows") == summary.get("final_rows"):
        print("  Row integrity : OK — no rows lost or duplicated")
    else:
        print("  Row integrity : *** MISMATCH — INVESTIGATE ***")

    print()
    print("  Joined tables:")
    for name, s in stats.items():
        if name.startswith("_"):
            continue
        rate = s["match_rate"]
        flag = "  " if rate >= 0.5 else " !"
        print(
            f"   {flag} {name:<28} {s['join_level']:<7} "
            f"on {'+'.join(s['keys']):<18} "
            f"{s['columns_added']:>3} cols  {rate:>6.1%} matched"
        )

    if side_tables:
        print()
        print("  Side tables (kept separate, not merged):")
        for name, df in side_tables.items():
            print(f"     {name:<28} {len(df):>8,} rows  {len(df.columns):>3} cols")

    print()
    if output:
        size_mb = output.stat().st_size / (1024 * 1024)
        print(f"  Extract: {output}  ({size_mb:.1f} MB)")
        print()
        print("  NEXT STEP (manual — Tableau Public has no API):")
        print("    1. Open the state workbook in Tableau Desktop")
        print("    2. Point its data source at the .hyper file above")
        print("    3. Refresh, then click 'Save to Tableau Public'")
    else:
        print("  DRY RUN — no extract written.")
    print("=" * 68)
    print()


# -----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a Tableau .hyper extract from Woodstock's source files."
    )
    ap.add_argument("--config", required=True, type=Path, help="Path to the state YAML config")
    ap.add_argument("--dry-run", action="store_true", help="Validate only; do not write the extract")
    ap.add_argument("--verbose", action="store_true", help="Show debug detail")
    args = ap.parse_args()

    cfg = load_config(args.config)

    # Paths in the config are relative to the PROJECT ROOT (the folder that
    # contains config/ and src/), not to the config file itself. This keeps the
    # config readable: "./data/illinois" rather than "../data/illinois".
    root = args.config.resolve().parent.parent
    log_dir = root / "logs"
    setup_logging(args.verbose, log_dir)

    state = cfg.get("state", "Unknown")
    log.info("=" * 60)
    log.info("Woodstock Tableau extract pipeline — %s", state)
    log.info("=" * 60)

    paths = cfg["paths"]
    input_dir = (root / paths["input_dir"]).resolve()
    output_dir = (root / paths["output_dir"]).resolve()
    output_path = output_dir / paths["output_name"]

    log.info("Input dir : %s", input_dir)
    log.info("Output    : %s", output_path)

    years = cfg.get("years", {})
    y_start = int(years.get("start", 2018))
    y_end = int(years.get("end", 2024))
    log.info("Year range: %d-%d", y_start, y_end)

    sources = cfg["sources"]
    validation = cfg.get("validation", {})

    # ---- 1. LOAD ----------------------------------------------------------
    log.info("")
    log.info("--- Step 1: loading source files ---")
    tables: dict[str, pd.DataFrame] = {}
    for name, spec in sources.items():
        try:
            df = load_source(input_dir, name, spec)
            df = filter_years(df, y_start, y_end, name)
            tables[name] = df
        except FileNotFoundError as e:
            log.error("%s", e)
            return 1
        except KeyError as e:
            log.error("%s", e)
            return 1

    # ---- 2. MERGE ---------------------------------------------------------
    log.info("")
    log.info("--- Step 2: merging onto the HMDA hub ---")
    try:
        merged, stats = merge_all(tables, sources, validation)
    except MergeError as e:
        log.error("MERGE FAILED: %s", e)
        return 1

    # ---- 3. COLLECT SIDE TABLES -------------------------------------------
    side_tables = {
        name: tables[name]
        for name, spec in sources.items()
        if spec.get("join_level") == "side_table" and name in tables
    }
    if side_tables:
        log.info("")
        log.info("--- Side tables (written separately, not merged) ---")
        for name, df in side_tables.items():
            log.info("  [%s] %s rows kept as its own table", name, f"{len(df):,}")

    # ---- 4. WRITE ---------------------------------------------------------
    written: Path | None = None
    if args.dry_run:
        log.info("")
        log.info("--- DRY RUN: skipping extract write ---")
    else:
        log.info("")
        log.info("--- Step 3: writing the Tableau extract ---")
        out_tables = {"Combined": merged}
        for name, df in side_tables.items():
            out_tables[name.replace("_", " ").title().replace(" ", "_")] = df
        written = write_hyper(out_tables, output_path)

    print_report(stats, written, side_tables)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
