# Support Ticket Dashboard: Day 4

**Streamlit and application basics**

An internal dashboard where a user uploads a support-ticket CSV and sees:

- a **preview** of the raw file (rows, columns, dimensions and inferred data types)
- **analytics** (ticket counts by priority, resolution time by category, headline metrics)
- a **data-quality summary** (missing and invalid values, dropped and duplicate rows)
- the **cleaned data**, which can be downloaded

The dashboard adds no cleaning rules of its own. Every rule comes from the
Day 3 `ticket_pipeline` package, reached through a small service layer.

| Day 4 goal | Where it is met |
|---|---|
| App starts using documented instructions | [Setup](#2-setup) and [Run](#3-run-the-app); evidence in `results/app_startup.log` |
| UI calls reusable business logic | `app.py` → `ticket_dashboard.service` → `ticket_pipeline` ([section 4](#4-how-it-works)) |
| Invalid uploads do not crash the app without explanation | [Error table](#6-what-the-user-sees-for-each-upload); 9 invalid fixtures tested through the real widget |
| Analytics agree with the underlying dataset | 3 agreement tests ([section 7](#7-tests)) |
| No secrets or local-only paths are committed | [section 9](#9-secrets-and-local-paths) |

---

## Contents
1. [Requirements](#1-requirements)
2. [Setup](#2-setup)
3. [Run the app](#3-run-the-app)
4. [How it works](#4-how-it-works)
5. [Using the dashboard](#5-using-the-dashboard)
6. [What the user sees for each upload](#6-what-the-user-sees-for-each-upload)
7. [Tests](#7-tests)
8. [Quality checks](#8-quality-checks)
9. [Secrets and local paths](#9-secrets-and-local-paths)
10. [Project structure](#10-project-structure)
11. [Assumptions](#11-assumptions)
12. [Known limitations](#12-known-limitations)
13. [Further documents](#13-further-documents)

---

## 1. Requirements

- Python 3.10 or newer (developed and tested on Python 3.15.2, Windows 11)
- Runtime packages: `streamlit` and `pandas`, installed by the setup below
- The `ticket_pipeline` package itself uses only the standard library

## 2. Setup

Run these from the project folder (the folder that contains this README).

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

`-e` installs the project in editable mode, so both `ticket_pipeline` and
`ticket_dashboard` can be imported from anywhere. `[dev]` adds pytest, ruff and mypy.
If you only want to run the app, use `pip install -e .`.

## 3. Run the app

```bash
streamlit run app.py
```

Open <http://localhost:8501>. Press **Load sample data** to see a full
dashboard straight away, using the bundled `data/tickets.csv`.

Stop the server with `Ctrl+C`.

Settings live in `.streamlit/config.toml`: the upload limit is 5 MB, the server
does not open a browser by itself, and usage statistics are off.

The pipeline's command-line tool from Day 3 still works:
```bash
ticket-pipeline --input data/tickets.csv --output-dir output
```

## 4. How it works

```
┌──────────────────────────────┐   name + bytes   ┌──────────────────────────────┐
│ app.py  (Streamlit UI)       │ ───────────────► │ ticket_dashboard/service.py  │
│ widgets, session state,      │                  │ validate_upload  (size, ext, │
│ layout, error display        │ ◄─────────────── │                  empty)      │
└──────────────────────────────┘  DashboardResult │ process_upload               │
                                  or an error     │ build_preview  (display only)│
                                                  │ *_frame helpers (reshaping)  │
                                                  └──────────────┬───────────────┘
                                                                 │ calls
                                                  ┌──────────────▼───────────────┐
                                                  │ ticket_pipeline  (Day 3)     │
                                                  │ TicketCsvReader → schema,    │
                                                  │   encoding, field checks     │
                                                  │ clean_records → cleaning     │
                                                  │ summarise → metrics          │
                                                  │ CleaningReport.quality_summary│
                                                  └──────────────────────────────┘
```

| Layer | Responsibility | Never does |
|---|---|---|
| `app.py` | Widgets, `st.session_state`, tabs, charts, error messages | Parse CSV, clean values, compute metrics |
| `ticket_dashboard.service` | Upload checks; adapts bytes to the pipeline reader; reshapes results into tables | Define cleaning rules or metrics; import Streamlit |
| `ticket_pipeline` | Reading, validation, cleaning, analytics | Know about the UI |

**How an upload reaches the Day 3 reader.** Day 3's `TicketCsvReader(handle, path)`
reads from any text handle. The service wraps the uploaded bytes as
`io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline="")`. An
upload therefore goes through the same encoding, header, field-count and
empty-file checks as a file on disk, and nothing is written to disk.

**Session state** (all keys are set in `init_state()` in `app.py`):

| Key | Purpose |
|---|---|
| `result` | The `DashboardResult` currently on screen, or `None` |
| `error` | The last error message the user can fix, or `None`. It is never set at the same time as `result`, so stale analytics are never shown next to an error. |
| `source_key` | SHA-256 of the processed bytes plus the duplicate policy. Pressing a button again with the same input does not reprocess the file. |
| `uploader_v` | Part of the uploader's widget key. **Clear** increases it, which is the supported way to empty a `file_uploader`. |
| `policy` | The duplicate-ID policy chosen in the form |

The upload, the policy and both submit buttons are inside one `st.form`. Changing
a widget therefore does not trigger processing, and **Load sample data** always
uses the policy currently selected.

See [docs/DESIGN.md](docs/DESIGN.md) for the design decisions and trade-offs.

## 5. Using the dashboard

1. In the sidebar, choose a CSV file. Optionally choose the duplicate-ID policy:
   - **Keep first** reports later copies of an ID and drops them.
   - **Reject** stops on the first repeated ID.
2. Press **Process**, or press **Load sample data**.
3. Read the four tabs:
   - **Preview:** row and column counts, each column's inferred type and non-null count, and the first 10 raw rows.
   - **Analytics:** clean tickets, unresolved tickets and average rating; priority counts (chart and table); average resolution time and resolution rate by category.
   - **Data quality:** source rows, invalid records, rows dropped for a missing ID, duplicates removed; missing and invalid values per column; issue counts.
   - **Cleaned data:** the cleaned tickets, with a **Download cleaned CSV** button.
4. Press **Clear** to return to the empty state.

The file needs these columns (extra columns are ignored):
`ticket_id, category, priority, description, resolution_time_hours, customer_rating, status`

## 6. What the user sees for each upload

Every case below has a fixture in `tests/fixtures/uploads/` and is tested
through the real upload widget in `tests/dashboard/test_app.py`.

| Upload | Raised by | Message shown (red error box) |
|---|---|---|
| `valid.csv` | — | Green "Processed valid.csv: 4 clean tickets", then the tabs |
| `empty.csv` (0 bytes) | `UploadError` | `Upload 'empty.csv' is empty (0 bytes). Export the data again and re-upload it.` |
| `blank_lines.csv` | `UploadError` | `... contains only blank lines. ...` |
| `wrong_ext.txt` | `UploadError` | `... has the extension '.txt' instead of '.csv'. Export the ticket data as CSV ...` |
| more than 5 MB | `UploadError` | `... is N MB, above the 5 MB limit. Split the export into smaller files.` (Streamlit's own 5 MB limit usually stops it first.) |
| `header_only.csv` | `EmptyDatasetError` | `'header_only.csv': the file has a header row but no ticket records. ...` |
| `malformed.csv` | `MalformedFileError` | `'malformed.csv' line 3: expected 7 fields, found 8. Check that values containing commas are wrapped in double quotes.` |
| `bad_quotes.csv` | `MalformedFileError` | `'bad_quotes.csv' line 2: expected 7 fields, found 4. ...` |
| `bad_encoding.csv` (Latin-1) | `MalformedFileError` | `'bad_encoding.csv': the file is not valid UTF-8 text (...). Re-save the file with UTF-8 encoding.` |
| `wrong_columns.csv` | `SchemaMismatchError` | `... missing required column(s): ticket_id, ... Found columns: id, type, urgency, text. Fix the header row ...` |
| Sample file with the **Reject** policy | `DuplicateTicketError` | `Ticket ID T-002 appears in record 2 and again in record 23. Remove or renumber the duplicate, or run with the keep_first duplicate policy.` |
| `no_valid_ids.csv` | — (valid file) | Yellow warning "No valid tickets remained after cleaning, so analytics are empty." |
| Process pressed with no file | — | `No file selected. Choose a CSV file, then press Process.` |

The UI catches only `TicketPipelineError`, the base class of all of these.
Any other exception is a real bug, so it is not hidden.

Messages show only the file name, never a folder path from the server.

## 7. Tests

```bash
pytest                          # all 228 tests, in random order (pytest-randomly)
pytest tests/dashboard          # only the Day 4 tests (42)
pytest -m ui                    # only the Streamlit AppTest UI tests (17)
pytest --cov                    # with branch coverage
```

| Test file | Count | What it proves |
|---|---|---|
| `tests/dashboard/test_service.py` | 25 | Valid uploads (BOM, CRLF, zero valid tickets); every invalid fixture raises a specific error naming the file and leaking no path; size limit at and above the boundary; `RAISE` policy; **analytics agreement**; nothing written to disk |
| `tests/dashboard/test_app.py` | 17 | App starts with the empty state and no exception; each fixture uploaded through `st.file_uploader` shows results or an explanation (never a traceback); sample data; the no-file case; session state is reused on rerun; an error replaces a stale result; Clear resets |
| `tests/unit`, `tests/integration` | 186 | The Day 3 pipeline tests, copied unchanged and still passing |

**How the "analytics agree with the dataset" criterion is tested.** Three independent checks:
1. `test_analytics_match_the_day3_pipeline_on_the_same_file`: the dashboard's analytics dictionary equals `run_pipeline(...).analytics` for `data/tickets.csv`.
2. `test_priority_counts_match_an_independent_count_of_the_raw_file`: re-counts priorities straight from the raw CSV with the `csv` module, applying the documented rules by hand.
3. `test_display_tables_carry_the_same_numbers_as_the_analytics`: every table and chart frame shown in the UI contains the same numbers as the analytics dictionary. The `test_load_sample_...` UI test also checks the rendered `st.metric` values.

**Results** (saved output in `results/`):

| Check | Result | File |
|---|---|---|
| pytest | **228 passed** | `results/test_results.txt` |
| Coverage | **99%** overall; `ticket_dashboard/service.py` 97% | `results/coverage.txt` |
| ruff check and format | All checks passed | `results/ruff.txt` |
| mypy `--strict` | No issues in 33 files | `results/mypy.txt` |
| App start-up | Server started; `/_stcore/health` → `ok`; `GET /` → 200 | `results/app_startup.log` |
| Bug reproduction | `type=["csv"]` crash, before and after the fix | `results/bug_uploader_type_filter.log` |

The two lines that coverage misses in `service.py` are the `pd.read_csv`
failure branch in `build_preview`. It is a safety net: the pipeline's reader has
already rejected any file pandas could not parse before the preview is built.

The manual browser checklist is in [docs/UI_TEST_CHECKLIST.md](docs/UI_TEST_CHECKLIST.md).

## 8. Quality checks

```bash
ruff check .
ruff format --check .
mypy            # strict mode over src/, tests/ and app.py
```

## 9. Secrets and local paths

- The app needs no secrets, API keys or credentials. `.streamlit/secrets.toml`
  and `.env` are listed in `.gitignore` in case one is ever added.
- Paths in code are relative to the file that uses them, for example
  `Path(__file__).parent / "data" / "tickets.csv"`.
- Saved evidence in `results/` had machine-specific paths replaced with
  `<project>` / `<python>`, and the startup log had network and public IP lines
  removed.
- Before each commit the repository was searched for drive-letter paths, user
  folders and key-like strings (see `DAILY_REPORT.md`).

## 10. Project structure

```
day4_ticket_dashboard/
├── app.py                         Streamlit UI (widgets, state, layout only)
├── pyproject.toml                 dependencies + pytest/coverage/mypy/ruff config
├── .streamlit/config.toml         upload limit, headless, no usage stats
├── data/tickets.csv               25-row sample dataset
├── src/
│   ├── ticket_dashboard/          Day 4 service layer
│   │   ├── __init__.py
│   │   └── service.py
│   └── ticket_pipeline/           Day 3 processing package (unchanged)
├── tests/
│   ├── conftest.py                shared fixtures (from Day 3)
│   ├── dashboard/                 Day 4 tests: test_service.py, test_app.py
│   ├── fixtures/uploads/          valid and invalid upload files
│   ├── unit/  integration/        Day 3 tests
├── results/                       saved outputs of tests, coverage, lint, types, start-up
├── docs/
│   ├── DESIGN.md
│   ├── UI_TEST_CHECKLIST.md
│   └── screenshots/
├── DAILY_REPORT.md
└── VIVA_ANSWERS.md
```

## 11. Assumptions

- Uploads are UTF-8 CSV files, with or without the byte-order mark that Excel adds.
- The cleaning rules are the Day 3 rules (summarised in the Day 3 README, section
  11). The dashboard adds only upload-level checks: extension, size and empty file.
- A ticket counts as resolved only when its status is `resolved` or `closed`.
- The dashboard is internal and used by one person at a time on a trusted
  network, so there is no login.
- The preview shows the **raw** file. Types are inferred by pandas: a numeric
  column that contains a bad value such as `abc` shows as `str`/`object`, which
  is useful for spotting problems.

## 12. Known limitations

- **One file at a time**, held in memory. The 5 MB limit keeps memory use small.
- **One malformed row rejects the whole file.** This is Day 3 behaviour, chosen
  so that shifted columns never produce silently wrong analytics.
- **The `Reject` duplicate policy reports only the first repeated ID.**
- **The file is parsed twice:** once by the pipeline (the source of truth) and
  once by pandas for the type preview. This is cheap at 5 MB, but it means the
  preview's inferred types are pandas' view of the file, not the pipeline's.
- **No login and no persistence.** Results live in the browser session and are
  lost when the tab is closed.
- **Screenshots** are not generated automatically. The UI behaviour is verified
  by the 17 AppTest tests instead. To add screenshots, follow
  `docs/UI_TEST_CHECKLIST.md` and save them in `docs/screenshots/`.

## 13. Further documents

- [docs/DESIGN.md](docs/DESIGN.md): layer boundaries, design decisions, state design
- [docs/UI_TEST_CHECKLIST.md](docs/UI_TEST_CHECKLIST.md): manual UI test cases and their results
- [DAILY_REPORT.md](DAILY_REPORT.md): Day 4 daily report
- [VIVA_ANSWERS.md](VIVA_ANSWERS.md): answers to the technical viva questions
