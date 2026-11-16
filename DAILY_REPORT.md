# Day 04 Daily Report: Streamlit and Application Basics

**Program:** 30-Day ML/DL Foundation to GenAI Engineering
**Date:** 2026-11-16
**Project:** Internal ticket-data dashboard (`day4_ticket_dashboard`)

## Topics learned
- Streamlit's execution model: the whole script reruns on every interaction, and callbacks run before that rerun.
- `st.session_state` for keeping results between reruns, `st.form` for grouping inputs so they submit together, and widget keys (including resetting a `file_uploader` by changing its key).
- Application boundaries: UI layer, then service layer, then processing package, with dependencies pointing one way only.
- Upload validation and user-facing error messages; empty states.
- Headless UI testing with `streamlit.testing.v1.AppTest`, including `file_uploader.upload(...)`.

## What I can explain without notes
- Why the dashboard has a service layer, and why it never imports Streamlit.
- How an uploaded file reaches the Day 3 `TicketCsvReader` without being written to disk (`TextIOWrapper` over `BytesIO`).
- What each session-state key is for, and why `result` and `error` are never set together.
- Why the UI catches only `TicketPipelineError`.
- How the tests prove that the analytics agree with the dataset.

## Implementation completed
| Task | Done |
|---|---|
| A: Upload and preview | Upload in the sidebar form; Preview tab shows rows, columns, dimensions, inferred dtypes, non-null counts and the first 10 raw rows |
| B: Connect the processor | `ticket_dashboard.service.process_upload` calls the Day 3 reader, `clean_records`, `summarise` and `quality_summary`. No cleaning logic in the UI. Errors are shown as messages with hints. |
| C: Analytics view | Priority counts (chart and table); average resolution time and resolution rate by category; headline metrics; Data quality tab; download of the cleaned data |
| D: Test and document | 42 new tests (25 service, 17 UI), including valid, empty and malformed uploads; README with setup, run, assumptions and limitations; design doc; UI checklist |

## Tests and experiment results
- `pytest`: **228 passed** (186 Day 3 tests plus 42 Day 4 tests), in random order. See `results/test_results.txt`.
- Coverage: **99%** overall, 97% for `service.py`. See `results/coverage.txt`.
- `ruff check`, `ruff format --check`: clean. `mypy --strict` over `src`, `tests` and `app.py`: no issues.
- `streamlit run app.py`: server started, `/_stcore/health` returned `ok`, `GET /` returned 200. See `results/app_startup.log`.
- Analytics agreement: the dashboard's analytics equal Day 3 `run_pipeline` output for `data/tickets.csv`, and the priority counts equal an independent recount with the `csv` module.

## One bug or challenge and its root cause
**Symptom:** the UI test that uploads `wrong_ext.txt` failed with
`StreamlitAPIException: Invalid file extension: .txt. Allowed: ['.csv']` instead
of showing my "instead of '.csv'" message.

**Root cause:** I had written `st.file_uploader(..., type=["csv"])`. Streamlit
checks `type` on the server too, while it deserialises the widget value during
the rerun. That is before my code runs, so my `try/except` could not catch it,
and the user would see a traceback. In a browser the file picker normally hides
other file types, but a renamed or dragged file can still get through.

**Fix:** removed `type=` and kept the extension check in
`service.validate_upload`, which raises `UploadError` with a hint. I reran the
test (it passes) and the whole suite (228 passed). The before/after reproduction
is in `results/bug_uploader_type_filter.log`.

## One design decision and why
**Uploads go through the Day 3 `TicketCsvReader` instead of `pd.read_csv`.**
The reader already enforces the schema, field counts, encoding and the
empty-file rules, with specific errors. Parsing with pandas in the UI would
create a second set of rules that could disagree with the CLI. pandas is used
only for the raw preview, after the pipeline has accepted the file.

## Blocker and what I tried
The first attempt to copy the Day 3 package into the Day 4 folder was blocked by
the tool's permission check. I did not work around it; I asked for confirmation,
and the copy ran once it was approved. A second, smaller blocker:
`AppTest`'s `file_uploader` support was not available in older Streamlit
versions. I checked the installed 1.67 API before relying on it, which is what
made the end-to-end upload tests possible.

## Tomorrow's plan
- Capture the five screenshots listed in `docs/UI_TEST_CHECKLIST.md`.
- Consider caching the processing result with `st.cache_data` keyed on the file hash, if multiple users share a server.
- Continue with the Day 5 material.

## Pre-commit checks
Before committing, the repository was searched for drive-letter paths, user
folders, IP addresses and key-like strings (`api_key`, `secret`, `token`,
`password`). No real secret or local path was found. The only hits were the
documentation describing this rule, one sample ticket's text ("Unable to reset
password"), and Day 3 tests that check the word "secret" is redacted from logs.
Generated folders (`.venv`, caches, `output/`) are git-ignored.
