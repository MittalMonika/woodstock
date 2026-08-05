# Woodstock Presentation — Speaker Notes

Your goal tomorrow: show them the solution works, get three decisions from them,
and set expectations honestly. Keep it conversational — you know this cold now.

Total time target: ~20–25 min talking, rest for discussion.

---

## Opening (2 min) — frame the win

> "We built and tested a working pipeline against your real Illinois data. It
> takes your six source files, merges them automatically, and produces a single
> Tableau extract — so the joining step that takes about an hour per portal
> becomes a couple of minutes. It costs nothing in new software. And along the
> way it caught a couple of data issues in your files that we should talk about."

Set the two honest expectations up front so nothing feels oversold:
- The **publishing click stays manual** — Tableau Public has no automation API.
  What we removed is the *joining and extract-building*, which was the actual hour.
- We need **three small decisions** from them to finalise.

---

## Part 1 — The problem, in their words (2 min)

Recap so they know you understood them:
- 5 public state portals, each built in Tableau, published to Tableau Public.
- Each portal = 6 data files that currently get joined *by hand* inside Tableau,
  every refresh cycle, from scratch. ~1 hour each, twice a year.
- Their goal: one consolidated dataset, update once, room to add states.
- Tableau Cloud ruled out — it charges per viewer, and portals are public.

> "Nothing we're proposing changes how the public sees the portals, or what you
> pay Tableau. The links stay the same."

---

## Part 2 — Why we're NOT changing the platform (2 min)

Pre-empt the "should we switch to Power BI / pay for Cloud" question:
- Every cloud BI tool charges per viewer for private hosting — same problem.
- The free public path (Tableau Public) already fits, and you've built on it.
- Switching platforms = rebuilding all 5 dashboards from scratch. Not worth it.

> "The smart move isn't a new tool. It's automating the one manual step inside
> the tool you already have."

---

## Part 3 — The solution, in plain terms (4 min)

Draw the flow (or show the diagram):

```
Your R pipeline → cleaned files on OneDrive
        +
Sukriti's supplementary files
        ↓
   [ our Python script ]  ← the new piece
        ↓
   one .hyper extract on OneDrive
        ↓
Tableau Desktop → open, refresh, click "Save to Tableau Public"
        ↓
   same public links, fresh data
```

Key points to land:
- A `.hyper` file **is** a finished Tableau extract. Tableau opens it instantly —
  nothing to import, nothing to join.
- The script runs with **one command**. Adding a new state = copy a config file,
  change the filenames. No code editing.
- We **don't touch your cleaning scripts.** This is a separate pipeline that
  starts from already-cleaned data — exactly as Yufei wanted.
- This is literally the Parquet→Hyper idea Yufei already raised. We built it out.

> "We tested this against your actual Illinois files. It runs, and it produces a
> valid extract with 19,306 merged rows and no data loss."

---

## Part 4 — What we learned from your real data (5 min) ← the substance

This is where you show depth. Two things: a modeling correction, and data issues.

### The modeling correction (shows you understood their data)

> "When we first looked, we assumed all six files were equal tables joined
> together. Reading your live Tableau workbook showed us it's actually more
> nuanced — and getting this right matters."

- **HMDA is the hub.** ACS and Small Business join onto it cleanly on FIPS + Year.
- **Top Lenders and Bank Branches are NOT county summaries** — Top Lenders is one
  row per *lending institution* (130,000 rows), Bank Branches is one row per
  *physical branch* with addresses and map coordinates. Flattening them would
  destroy exactly the detail those views need. So we keep them as their own
  tables inside the same extract — which is what your workbook does today.
- **Foreclosures uses Chicago Community Areas, not FIPS** — Chicago-only, and one
  Community Area covers many census tracts. Also kept separate, joined on year,
  matching your current setup.

### The data issues (this is genuinely valuable to them)

> "Our safety checks caught a real issue in the Small Business file that would
> have silently made some numbers wrong in the dashboard."

- **Springfield, tract 17167003000, 2019** appears **twice with different lending
  numbers** (30 vs 47 loans under $100K). Not a harmless copy — a genuine conflict.
  If this went through Tableau unnoticed, Springfield's totals would double.
  **→ We need you to tell us: should those two rows be added together, or is one
  a mistake?**
- (A second duplicate — Joliet — is a harmless exact copy; we drop it automatically.)
- **Bank Branches data stops at 2023** while everything else goes to 2024. We
  handle this safely (2024 rows survive with blank branch data) but you should know.
- **Small Business covers 95% of tract-years** — the missing 5% may be legitimate
  (no lending there) but worth a sanity check on your end.

> "The point isn't that your data is bad — it's that this pipeline catches these
> things *before* they reach the public, which the manual process can't."

---

## Part 5 — The three decisions we need (2 min)

Be crisp. These are the asks:

1. **The Springfield duplicate** — sum the two rows, or is one wrong?
2. **The HMDA output columns** — confirm Yufei's cleaned HMDA CSV names its key
   columns `FIPS` and `Year` (or tell us what they're called). One-line change.
3. **Foreclosures display** — happy to keep it as a separate year-level table
   (as today), or do you want it shown differently?

---

## Part 6 — What's next (2 min)

- Our team is reviewing the code now (5 of us, one module each) before we finalise.
- Once you confirm the three items above, we plug in the real HMDA file and it's
  ready for the first real extract.
- Then we validate one portal end-to-end (Illinois), and roll the same pattern
  out to the other four states.
- Phase 2 (future / optional): automate the production of the supplementary files
  themselves — out of scope for now, documented for later.

Close:
> "Net result: the ~10 hours a year of manual extract-building drops to minutes,
> nothing changes for the public, you pay nothing new, and you get a safety net
> that flags bad data before it's published."

---

## Anticipated tough questions — have these ready

**"Can't the whole thing be automated, including publishing?"**
> Not to Tableau Public — it has no API, by design; it's a free consumer product.
> The publish click stays manual, but it's ~2 minutes once the extract is built.
> Full automation would mean paid hosting, which reintroduces the per-viewer cost
> you ruled out.

**"Why Python and not R, since our pipeline is R?"**
> Two reasons: Tableau's extract-writing library (pantab/Hyper API) is Python, and
> both Sukriti and Yufei already work in Python. It's also deliberately a *separate*
> system from your cleaning, so the language choice doesn't affect your R code.

**"What happens when the data schema changes next year?"**
> The config holds all the column names in one place, so a rename is a one-line
> edit, not a code change. And the pipeline fails *loudly* with a clear message if
> a column goes missing — it won't silently produce wrong data.

**"Who maintains this after the engagement?"**
> That's a fair and important question — worth discussing. The code is documented
> and the config is designed for non-coders, but someone comfortable running a
> script will need to own it. Let's talk about who that is on your side.

**"How do we know the merged numbers are correct?"**
> Two built-in guarantees: the row count can't change (catches dropped or
> duplicated rows), and duplicate keys stop the run. We can also validate one
> published dashboard against your current one, number for number, before rollout.

**"Is our data safe / where does it go?"**
> Everything runs locally on your machine, files stay on your OneDrive, nothing is
> uploaded anywhere new. The extract is written right back to the same folder
> Tableau already uses.

---

## One-line summary if you only have 30 seconds

> "We automated the hour-long manual merge into a one-command script that outputs a
> ready-to-use Tableau extract — tested on your real data, zero new cost, and it
> even caught data errors your current process would miss. We need three small
> confirmations from you to finalise it."
