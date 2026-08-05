# Code Review Assignment — Woodstock Tableau Pipeline


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

