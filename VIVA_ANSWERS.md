# Day 4 Technical Viva: Draft Answers

Each answer uses examples from this project.

## 1. Why should data-cleaning logic not live entirely in the UI file?
- **One source of truth.** The CLI and the dashboard must clean data identically. If the rules sat in `app.py`, the CLI would need a copy, and the two copies would drift. Here both call `ticket_pipeline`, and a test (`test_analytics_match_the_day3_pipeline_on_the_same_file`) proves they agree.
- **Testability.** Logic in a Streamlit script runs only inside Streamlit. `ticket_dashboard.service` and `ticket_pipeline` never import Streamlit, so 211 of the 228 tests are plain, fast pytest tests.
- **Reruns.** Streamlit reruns the whole script on every click. Keeping heavy logic behind one function call (`process_upload`) makes it easy to skip work with session state or caching.
- **Replaceability.** The UI could become an API or a different framework without touching the rules.

## 2. What does Streamlit session state solve?
Every interaction reruns the script from the top, so ordinary variables are
lost. `st.session_state` is a per-browser-session dictionary that survives
reruns. In this app it:
- keeps the processed `result`, so switching tabs or pressing a button does not lose it or reprocess it (`source_key` is a hash of the bytes and the policy);
- keeps the last `error`, and is never set together with `result`, so stale analytics are not shown next to a new error;
- lets **Clear** reset the uploader by changing its key (`uploader_v`).

`st.form` is the complementary tool: it groups inputs so the app reacts once,
on submit, and not on every widget change.

## 3. How should uploaded files be validated?
In layers, cheapest first, and on the server. The browser's file-picker filter
is a convenience, not a check.
1. **The upload itself** (`validate_upload`): the extension is `.csv`; the file is not empty or blank; it is within the size limit (5 MB, matched by `server.maxUploadSize`).
2. **Encoding and structure** (Day 3 `TicketCsvReader`): valid UTF-8 (an Excel BOM is allowed); balanced quotes; every row has the header's field count.
3. **Schema** (`check_schema`): every required column appears exactly once.
4. **Values** (`clean_records`): numbers in range and valid priorities. Bad values become missing and are *reported*; they do not reject the file.

Every failure raises a specific error that names the file (never a server path)
and says how to fix it. The UI catches that error family and shows the message.

## 4. What should happen when a user submits an empty file?
The app should explain what is wrong and how to fix it. It should not crash and
should not show an empty dashboard. This app does so as follows:
- A 0-byte file shows "Upload 'empty.csv' is empty (0 bytes). Export the data again and re-upload it."
- A file of blank lines shows "... contains only blank lines."
- A header-only file shows "... has a header row but no ticket records."
- A file whose rows are all invalid (no ticket IDs) is processed, but a warning says that no valid tickets remained, and the analytics are empty instead of misleading.
- Pressing **Process** with no file chosen shows "No file selected ...".

In every case the previous result is cleared, so old numbers are never shown
for a new, empty file. The UI tests check each case.
