"""
hyper_writer.py — Writes the merged data to a Tableau .hyper extract.

"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pantab

log = logging.getLogger(__name__)


def _prepare_for_hyper(df: pd.DataFrame) -> pd.DataFrame:
    """Make a dataframe safe to write to Hyper.

    """
    out = df.copy()

    for col in out.columns:
        dtype = out[col].dtype

        # pandas 'object' columns are the risky ones — they can hold anything.
        if dtype == "object":
            out[col] = out[col].astype("string")

        # Hyper cannot store pandas' nullable-boolean cleanly in all versions;
        # convert to a plain string representation to be safe.
        elif str(dtype) == "boolean":
            out[col] = out[col].astype("string")

    # Hyper does not allow duplicate column names.
    if out.columns.duplicated().any():
        dupes = out.columns[out.columns.duplicated()].tolist()
        raise ValueError(
            f"Cannot write .hyper — duplicate column names found: {dupes}. "
            f"Add a 'prefix' for the offending source in the config."
        )

    return out


def write_hyper(
    tables: dict[str, pd.DataFrame],
    output_path: Path,
) -> Path:
    """Write one or more dataframes into a single .hyper file.

   
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove any previous extract so we never silently append to stale data.
    if output_path.exists():
        log.info("Removing existing extract: %s", output_path.name)
        output_path.unlink()

    prepared = {}
    for name, df in tables.items():
        log.info(
            "Preparing table '%s' for Hyper: %s rows x %s cols",
            name,
            f"{len(df):,}",
            len(df.columns),
        )
        prepared[name] = _prepare_for_hyper(df)

    log.info("Writing extract -> %s", output_path)
    pantab.frames_to_hyper(prepared, output_path)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    log.info("Extract written successfully (%.1f MB)", size_mb)
    log.info("Tables inside the extract: %s", list(prepared.keys()))

    return output_path
