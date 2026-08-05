# Code Review Assignment — Woodstock Tableau Pipeline

Each person owns **one file**. Read it, run the questions below against it, and
write your findings in a shared doc under your name. Aim for 30–45 minutes.

You don't need to be a Python expert. Most of the value is in checking the
**logic and the assumptions**, not the syntax. If something isn't obvious from
the comments, that's itself worth flagging — the code should be readable by the
next person who inherits it.

---

## How the pieces fit together (read this first, everyone)

```
run_pipeline.py   → the conductor. Reads the config, calls the other 3 in order.
      │
      ├── loader.py       → reads each file, fixes messy columns/types
      ├── merger.py       → joins the tables, runs the safety checks
      └── hyper_writer.py → writes the final .hyper extract for Tableau

config/illinois.yml → the control panel. All filenames, column names,
                      and join rules live here — no code editing needed.
```

Data flows: **6 source files → loader → merger → hyper_writer → one .hyper file.**
HMDA is the "hub" — every row of the final merged table is an HMDA row, with the
other tables' columns attached.

---

## Reviewer 1 — `config/illinois.yml` (166 lines)

**You own the control panel.** Everyone else's code reads from this file, so if
it's wrong or unclear, everything downstream breaks.

Check:
- [ ] Are the six source files all listed, with correct sheet names?
- [ ] For each file, does `join_level` make sense? (`hub`, `tract`, `side_table`)
- [ ] Read the comments on **Top Lenders**, **Bank Branches**, and **Foreclosures**
      explaining why they're `side_table`. Do the reasons convince you?
- [ ] The `on_duplicate: sum` setting on Small Business — is the comment above it
      clear about *why* a human has to decide this? Would Woodstock understand it?
- [ ] Could someone add a new state by copying this file, without touching code?
      Try mentally walking through it for "Ohio."
- [ ] Are the column-name notes (trailing spaces, `FIPS` vs `FIPS Code`) accurate
      to what you'd expect?

**The big question:** if you handed this file to someone at Woodstock who knew
their data but not Python, could they maintain it?

---

## Reviewer 2 — `src/loader.py` (199 lines)

**You own data cleaning.** This file reads each file and fixes three real bugs we
found: trailing spaces in column names, Year stored as text, and FIPS codes
losing their leading zeros.

Check:
- [ ] `_clean_headers` — does stripping whitespace from column names look correct?
- [ ] `normalise_year` — it forces Year to a number. What happens to a value like
      `"2019 "` or `"N/A"`? Trace it through.
- [ ] `normalise_fips` — this zero-pads FIPS codes to a fixed width (11 for tract,
      5 for county). Is the logic sound? What if a FIPS is already text?
- [ ] `derive_county_fips` — it takes the first 5 characters of the tract FIPS.
      Is that a safe assumption? (It is standard, but confirm you understand why.)
- [ ] `apply_prefix` — it prefixes columns (e.g. `acs_`) to avoid clashes. Does it
      correctly skip the join-key columns?
- [ ] Error messages — if a configured column is missing, is the error helpful?

**The big question:** are there any messy-data cases these functions would let
through silently? Think about blanks, mixed types, unexpected formats.

---

## Reviewer 3 — `src/merger.py` (306 lines) ← the most important file

**You own the joins and the safety checks.** This is where wrong numbers would
come from if anything is off, so it's the highest-stakes review.

Check:
- [ ] `merge_all` — walk through the join loop. HMDA is the base; each table is
      LEFT joined onto it. Why must it be a *left* join and not inner? (Hint:
      Bank Branches has no 2024 data.)
- [ ] `_resolve_duplicates` — this is the key safety function. It splits duplicates
      into "identical" (safe) and "conflicting" (needs a human). Does that split
      logic look right?
- [ ] The four `on_duplicate` policies (`fail`, `drop_identical`, `sum`, `first`) —
      does each do what its name says?
- [ ] The two big safety checks: **row count must not change**, and **keys must be
      unique in the lookup**. Convince yourself these actually catch the "silently
      doubled numbers" bug. Can you think of a way bad data could still slip past?
- [ ] `validate="many_to_one"` on the merge call — do you understand what that
      guarantees?
- [ ] Read the big comment block at the bottom explaining why Foreclosures isn't
      merged. Does it hold up?

**The big question:** is there ANY path through this code where the final extract
could contain inflated or dropped numbers without the pipeline stopping? That's
the whole thing we're protecting against.

---

## Reviewer 4 — `src/hyper_writer.py` (93 lines)

**You own the output.** This turns the merged data into the `.hyper` file Tableau
opens. Shortest file — so also spend time actually *running* the pipeline (see
below) and confirming the output.

Check:
- [ ] `_prepare_for_hyper` — it converts `object`-type columns to strings. Why is
      that needed for Hyper but not for Excel? (Hint: Hyper is strongly typed.)
- [ ] The duplicate-column-name check — would it give a clear error if two sources
      forgot their prefixes?
- [ ] `write_hyper` — it deletes any existing extract first. Why is that safer than
      appending? What could go wrong if it didn't?
- [ ] It writes multiple tables into one `.hyper` (Combined + the 3 side tables).
      Confirm you understand how Tableau will see those.
- [ ] Run the pipeline yourself (instructions below) and open the log. Do the row
      counts in the output match what the report claims?

**The big question:** does the output file faithfully represent the merged data,
with nothing lost or mistyped in the conversion?

---

## Reviewer 5 — `src/run_pipeline.py` (241 lines)

**You own the conductor and the user experience.** This is what someone actually
runs. If the flow or the messages are confusing, the tool won't get used.

Check:
- [ ] Trace the `main()` flow: load → merge → collect side tables → write → report.
      Does the order make sense?
- [ ] Path handling — paths in the config are relative to the *project root*. Is
      that resolved correctly? (We had a bug here; check it's right.)
- [ ] `filter_years` — does it correctly keep only the configured year range?
- [ ] `--dry-run` and `--verbose` flags — do they do what you'd expect?
- [ ] `print_report` — is the final summary clear? Would a non-technical person
      understand "matched 95.2%" or "row integrity OK"?
- [ ] The "NEXT STEP" message about manual publishing — is it accurate and clear?
- [ ] Error handling — if a file is missing, does the program fail *gracefully*
      with a helpful message, or crash with a stack trace?

**The big question:** could someone at Woodstock run this, read the output, and
know whether it worked — without asking us?

---

## Everyone: actually run it once

```bash
pip install -r requirements.txt

# put the 6 source files in data/illinois/  (ask [you] for them)
python src/run_pipeline.py --config config/illinois.yml --verbose

# also try the dry run
python src/run_pipeline.py --config config/illinois.yml --dry-run
```

Watch it stop on the Springfield duplicate if you set `on_duplicate: fail`. That's
the safety check working — make sure you understand why it fires.

---

## What to write up

For your file, note:
1. **Bugs / risks** — anything that could produce wrong output
2. **Clarity** — anything a future maintainer (or Woodstock) wouldn't understand
3. **Questions** — anything you're unsure about or want to discuss
4. **One thing you'd change** — even small

We'll go through everyone's findings together before we finalise and hand it to
Woodstock.
