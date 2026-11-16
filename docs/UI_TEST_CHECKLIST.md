# UI Test Checklist

Manual checks for the dashboard. Each upload file is in `tests/fixtures/uploads/`.

**How to run:** `streamlit run app.py`, open <http://localhost:8501>, and for each
row upload the file in the sidebar and press **Process**. Pass means the expected
result appears and no red traceback ("Exception" box) appears.

Each row is also automated in `tests/dashboard/test_app.py` using Streamlit's
`AppTest`, which pushes the file through the real `st.file_uploader` widget and
runs `app.py` headlessly. The **Automated** column shows the result of that run
(`results/test_results.txt`, 2026-11-16).

## Start-up and empty state

| # | Step | Expected | Automated |
|---|---|---|---|
| 1 | Run `streamlit run app.py` | Server starts; the page loads at `localhost:8501` | Pass (`results/app_startup.log`: health `ok`, HTTP 200) |
| 2 | Open the page with no file | Title "Support ticket dashboard"; blue info box asking for an upload; list of required columns; no error | Pass (`test_app_starts_without_exceptions_and_shows_the_empty_state`) |
| 3 | Press **Process** with no file chosen | Red: "No file selected. Choose a CSV file, then press Process." | Pass (`test_process_without_a_file_explains_what_to_do`) |

## Valid data

| # | Upload | Expected | Automated |
|---|---|---|---|
| 4 | `valid.csv` | Green "Processed valid.csv: 4 clean tickets"; Preview shows Rows 4, Columns 7; four tabs | Pass (`test_valid_upload_through_the_widget_shows_results`) |
| 5 | **Load sample data** | Preview 25 × 7; Clean tickets 23; Unresolved 10; Average rating 4.00; Invalid records 5 | Pass (`test_load_sample_shows_tabs_and_metrics_that_match_the_service`) |
| 6 | `no_valid_ids.csv` | Yellow warning "No valid tickets remained after cleaning ..."; no crash | Pass (`test_upload_with_no_valid_tickets_warns_instead_of_crashing`) |
| 7 | **Cleaned data** tab → **Download cleaned CSV** | Downloads `cleaned_tickets.csv`; re-uploading it gives 0 invalid records | Pass (service round-trip test `test_cleaned_table_round_trips_through_the_pipeline`) |

## Invalid uploads: each must explain, never crash

| # | Upload | Expected red message contains | Automated |
|---|---|---|---|
| 8 | `empty.csv` | "is empty (0 bytes)" | Pass |
| 9 | `blank_lines.csv` | "contains only blank lines" | Pass |
| 10 | `header_only.csv` | "header row but no ticket records" | Pass |
| 11 | `malformed.csv` | "line 3: expected 7 fields, found 8" | Pass |
| 12 | `bad_quotes.csv` | "expected 7 fields, found 4" | Pass |
| 13 | `bad_encoding.csv` | "not valid UTF-8 ... Re-save the file with UTF-8 encoding" | Pass |
| 14 | `wrong_columns.csv` | "missing required column(s)" and the columns that were found | Pass |
| 15 | `wrong_ext.txt` | "has the extension '.txt' instead of '.csv'" | Pass (failed at first; see "Bug found" below) |
| 16 | Sample data with policy **Reject** | "Ticket ID T-002 appears in record 2 and again in record 23" | Pass (`test_pipeline_error_is_shown_as_a_message_not_a_traceback`) |

Rows 8–15 are the parametrised `test_invalid_upload_shows_an_explanation_not_a_crash`.
Each run also checks that no tabs are drawn and that `result` is `None`.

## State behaviour

| # | Step | Expected | Automated |
|---|---|---|---|
| 17 | Load sample, then press Load sample again | Same result kept; no reprocessing | Pass (`test_rerun_keeps_the_result_without_reprocessing`) |
| 18 | Load sample (success), switch to **Reject**, Load sample | Old analytics disappear; only the error shows | Pass (`test_error_after_success_replaces_the_old_result`) |
| 19 | Press **Clear** | Back to the empty state; the uploader is emptied | Pass (`test_clear_resets_to_the_empty_state`) |
| 20 | Change the policy without pressing a button | Nothing reprocesses (the inputs are inside a form) | By design (`st.form`); check manually |

## Bug found by this checklist
Row 15 first failed with `StreamlitAPIException: Invalid file extension: .txt`.
The uploader had `type=["csv"]`, and Streamlit enforces that on the server by
raising an exception the app cannot catch. **Fix:** remove `type=` and rely
on `service.validate_upload`. The reproduction is in
`results/bug_uploader_type_filter.log`.

## Screenshots
Save browser screenshots in `docs/screenshots/` with these names:
`01_empty_state.png`, `02_sample_analytics.png`, `03_data_quality.png`,
`04_malformed_error.png`, `05_wrong_columns_error.png`.
They are shown, with the expected result and a pass/fail line, in
[`SCREENSHOTS.md`](SCREENSHOTS.md).
No screenshots were captured in this session because no browser automation
was available. The automated column above is the verification evidence.
