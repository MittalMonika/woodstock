# Woodstock Tableau Extract Pipeline

Builds a single Tableau `.hyper` extract from the six source files for a state,
so Tableau no longer has to import and join them by hand.

```
Before:  6 files → import into Tableau → join by hand → build extract   (~1 hour/state)
After:   run this script → one .hyper file → open, refresh, publish     (~2 min/state)
```

---

## Quick start

```bash
pip install -r requirements.txt

# put the source files in data/illinois/
python src/run_pipeline.py --config config/illinois.yml
```

The extract appears at `output/illinois_portal.hyper`.

Then, in Tableau Desktop: open the state workbook → point its data source at the
`.hyper` file → Refresh → **Save to Tableau Public**.

> **Note:** publishing stays manual. Tableau Public has no API — nothing can push
> to it automatically. But that click takes ~2 minutes; it was the *joining and
> extract-building* that took the hour, and that is what this removes.

---

## Useful flags

```bash
# validate everything without writing the extract
python src/run_pipeline.py --config config/illinois.yml --dry-run

# show detailed logs
python src/run_pipeline.py --config config/illinois.yml --verbose
```

Every run also writes a timestamped log to `logs/`.

---

## Adding another state

1. Copy `config/illinois.yml` → `config/ohio.yml`
2. Change `state`, `paths.input_dir`, `paths.output_name`, and the six `file:` names
3. Run it

**You should not need to edit any Python.** All file names, sheet names, column
names, and join rules live in the config.

---

## What the data model actually is

The structure below was taken directly from Woodstock's live Tableau workbook
(`Illinois_Community_Lending_Data_Portal.twbx`), so the output mirrors what the
dashboards already expect.

**HMDA is the hub.** Every row of the merged table is an HMDA row.

| Table | How it's handled | Why |
|---|---|---|
| **HMDA** | The hub | Every other table joins onto it |
| **ACS** | Merged on `FIPS` + `Year` | Tract-level, one row per tract-year |
| **Small Business** | Merged on `FIPS` + `Year` | Tract-level, one row per tract-year |
| **Small Business by Top Lenders** | **Separate table** | One row *per lending institution* — 129,903 rows across only 612 county-years. Flattening it would destroy the lender detail |
| **Bank Branches** | **Separate table** | One row *per physical branch*, with address and lat/long. It's map data |
| **Foreclosures** | **Separate table** | Uses Chicago Community Areas, not FIPS. Chicago-only, and one Community Area spans many tracts |

All four tables are written into the **same `.hyper` file**, so Tableau sees them
as related tables — exactly as it does today.

---

## The safety checks (and why they matter)

The pipeline refuses to produce a corrupt extract. Two checks do the heavy lifting:

**1. Duplicate join keys.** If a lookup table has the same `FIPS + Year` twice,
joining it *duplicates* the matching HMDA rows and every dollar figure in the
dashboard silently doubles. The pipeline stops and tells you exactly which keys
are affected.

**2. Row count integrity.** The merged table must have exactly as many rows as
HMDA did. Fewer means rows were dropped; more means a join fanned out. Either
aborts the run.

Both are the kind of bug that *looks* like success and quietly publishes wrong
numbers — which is precisely what we cannot let happen on a public portal.

---

## ⚠️ Data quality issues found in the real Illinois data

These were surfaced by the checks above and **need a decision from Woodstock**.

### 1. Duplicate tract in Small Business data

`Portal_6YR_Illinois_Small_Business_Data_08_25_25.xlsx` has two duplicate keys:

| Tract | Year | Location | Issue |
|---|---|---|---|
| `17197881900` | 2019 | Joliet, Will Co. | Two **identical** rows — harmless, safely dropped |
| `17167003000` | 2019 | Springfield, Sangamon Co. | Two rows, **same key but different values** (e.g. 30 vs 47 loans under \$100K) |

The Springfield rows are a **genuine data problem**. They must either be summed
(if they're two partial records) or one corrected (if one is erroneous).

The config is currently set to `on_duplicate: sum`. **Please confirm this is right** —
change it in `config/illinois.yml` if not:

```yaml
on_duplicate: sum              # add the rows together      (current)
on_duplicate: drop_identical   # drop exact dupes, stop on the conflict
on_duplicate: first            # keep the first row only
```

### 2. Small Business matches 95.2%, not 100%

About 924 HMDA tract-years have no Small Business record. This may be expected
(no small-business lending in that tract that year) — worth a sanity check.

### 3. Bank Branches has no 2024 data

Everything else runs to 2024. Because all joins are LEFT joins from HMDA, 2024
rows are **not** dropped — but bank-branch values will be blank for 2024.

---

## Project layout

```
config/     illinois.yml       ← all paths, columns, and join rules
src/        run_pipeline.py    ← entry point
            loader.py          ← reads files, fixes types and whitespace
            merger.py          ← joins tables, enforces the safety checks
            hyper_writer.py    ← writes the .hyper extract
data/       illinois/          ← put the six source files here
output/     illinois_portal.hyper
logs/       pipeline_*.log
```

---

## Notes on the source data

The loader defensively fixes three real inconsistencies found in the files:

- **Trailing spaces in column names** — Small Business and Bank Branches use
  `"Year "`, ACS uses `"Year"`. Identical to a human, different to code.
- **Year stored as text** — Foreclosures stores `'2018'` as a string; everything
  else uses the number `2018`. Joining these matches zero rows, silently.
- **FIPS codes losing leading zeros** — FIPS are identifiers, not numbers. They
  are stored as fixed-width zero-padded strings (11 digits for tract, 5 for county).

County FIPS is derived from the first 5 digits of the tract FIPS, so no separate
lookup table is needed.
