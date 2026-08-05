# Setup & Installation Guide

Everything you need to get the pipeline running, starting from a computer with
nothing installed.

---

## Step 1 — Install Python (3.10 or newer)

Check whether you already have it. Open a terminal / command prompt and run:

```bash
python --version
```

or on some systems:

```bash
python3 --version
```

If it prints `Python 3.10` or higher, skip to Step 2. Otherwise install it:

**Windows**
1. Go to https://www.python.org/downloads/
2. Download the latest Python 3 installer.
3. Run it — **tick "Add Python to PATH"** on the first screen (important).
4. Click "Install Now".

**Mac**
- Easiest: install from https://www.python.org/downloads/ (the .pkg installer), or
- With Homebrew: `brew install python`

**Linux (Ubuntu/Debian)**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

---

## Step 2 — Get the project folder

Unzip `woodstock_pipeline.zip` somewhere easy to find, e.g. your Desktop.
You should see this structure:

```
woodstock_pipeline/
├── config/          illinois.yml
├── src/             the Python code
├── data/illinois/   the source files (all 6 files)
├── output/          extracts land here
├── logs/            run logs land here
├── requirements.txt
└── README.md
```

Open a terminal **inside** that folder:
- **Windows:** open the folder, click the address bar, type `cmd`, press Enter.
- **Mac:** right-click the folder → Services → "New Terminal at Folder".
- **Linux:** right-click → "Open in Terminal".

---

## Step 3 — (Recommended) Create a virtual environment

This keeps the pipeline's packages separate from the rest of your system, so
nothing conflicts. Optional but good practice.

**Windows**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Mac / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)` at the start. (To leave it later, type
`deactivate`.)

---

## Step 4 — Install the packages

```bash
pip install -r requirements.txt
```

This installs pandas, openpyxl, PyYAML, pantab, and the Tableau Hyper API.
It may take a minute or two the first time. All packages are free and
open-source — no Tableau licence is needed to create `.hyper` files.

If `pip` isn't found, try `pip3` instead, or `python -m pip install -r requirements.txt`.

---

## Step 5 — Run the pipeline

```bash
python src/run_pipeline.py --config config/illinois.yml
```

You should see it load each file, merge them, run the safety checks, and write
`output/illinois_portal.hyper`. A summary report prints at the end.

Other useful commands:

```bash
# validate everything but don't write the extract
python src/run_pipeline.py --config config/illinois.yml --dry-run

# show detailed step-by-step logging
python src/run_pipeline.py --config config/illinois.yml --verbose
```

---

## Step 6 — Open the result in Tableau

1. Open Tableau Desktop.
2. Connect to data → select `output/illinois_portal.hyper`.
3. You'll see the `Combined` table plus the side tables (Bank Branches,
   Foreclosures, etc.) — already merged, nothing to join.
4. Build/refresh the dashboard, then **Save to Tableau Public**.

---

## Troubleshooting

**`python: command not found`**
Try `python3` instead. On Windows, you likely missed "Add Python to PATH"
during install — re-run the installer and tick it.

**`No module named pandas` (or pantab, yaml, etc.)**
The packages didn't install, or you're not in the virtual environment. Re-run
`pip install -r requirements.txt`. If you made a venv, make sure it's activated
(you should see `(.venv)` in your prompt).

**`Expected file not found: .../hmda_illinois_cleaned.csv`**
The HMDA file isn't in `data/illinois/`. The package includes a sample one — if
it's missing, or you want to use the real HMDA data, place the file there and
make sure its name matches the `file:` entry in `config/illinois.yml`.

**`pip install` fails on tableauhyperapi**
The Hyper API needs a 64-bit OS and, on Linux, a reasonably recent system. If it
fails, upgrade pip first: `python -m pip install --upgrade pip`, then retry.

**The pipeline stops on a "duplicate join keys" error**
That's the safety check working, not a crash. It found duplicate rows in a source
file (see the README's "Data quality issues" section). Read the message — it tells
you which keys and how to resolve it via the `on_duplicate` setting in the config.

**Excel file won't read / "Unsupported format"**
Make sure openpyxl installed correctly. Very old `.xls` files (not `.xlsx`) aren't
supported by openpyxl — re-save them as `.xlsx` if needed.
