# Day 4 Design: Ticket Dashboard

## Context and goal
Day 3 produced a tested, standard-library pipeline (`ticket_pipeline`) that reads,
validates, cleans and summarises a support-ticket CSV from the command line.
Day 4 puts it behind a small Streamlit interface. The UI must stay separate from
the processing logic, so that the cleaning rules exist in exactly one place.

## Layers

```
app.py ──► ticket_dashboard.service ──► ticket_pipeline
(UI)       (adapter + display shaping)   (rules, cleaning, metrics: Day 3, unchanged)
```

Dependencies point one way only. `ticket_pipeline` knows nothing about the
dashboard, and `ticket_dashboard` never imports Streamlit, so pytest can test
both without a browser.

## Decisions and trade-offs

### 1. Reuse the Day 3 reader for uploads instead of `pd.read_csv`
- **Decision:** wrap the uploaded bytes in `io.TextIOWrapper(BytesIO(data), encoding="utf-8-sig", newline="")` and pass the handle to `TicketCsvReader`.
- **Why:** the reader already checks the header, field counts, encoding, quoting and empty files, and raises specific errors with hints. A second parser in the UI would duplicate those rules, and the two would drift apart.
- **Trade-off:** pandas still reads the file once more, but only to build the preview of raw rows and types. The analytics never depend on pandas.

### 2. A service layer instead of calling the pipeline straight from `app.py`
- **Why:** it gives one testable entry point (`process_upload(name, bytes, policy)`), keeps Streamlit-free code testable with plain pytest, and puts the "bytes to text handle" adapter where it can be unit-tested.
- **Not chosen:** writing the upload to a temporary file and calling `run_pipeline`. That adds disk I/O and clean-up for no benefit, and leaves files behind if the app crashes. A test checks that `process_upload` writes nothing.

### 3. Mirror `pipeline._analyse` instead of calling it
`process_upload` builds the analytics as `{**summarise(tickets), **report.quality_summary()}`, the same expression `pipeline._analyse` uses. `_analyse` is private and wrapped in a logging decorator that is meant for the CLI. The two-function composition is public API.
`test_analytics_match_the_day3_pipeline_on_the_same_file` fails if the two ever differ.

### 4. Only expected errors are caught in the UI
`app.py` catches `TicketPipelineError` (including the new `UploadError`) and
shows its message. Anything else is a bug and should stay visible. A broad
`except Exception` would turn bugs into confusing "invalid file" messages.

### 5. The server checks file types, not Streamlit's `type=` filter
`st.file_uploader(type=["csv"])` raises `StreamlitAPIException` from inside widget-state handling when a non-CSV file arrives. The user sees a traceback, and no app code can catch it. The UI test with `wrong_ext.txt` found this; it is reproduced in `results/bug_uploader_type_filter.log`. The extension check therefore lives in `service.validate_upload`, which explains the problem to the user.

## Session-state design

| Problem | Design |
|---|---|
| Every widget change reruns the script | Inputs sit inside an `st.form`, so processing happens only when a submit button is pressed |
| Reruns would reprocess the same file | Results are stored in `st.session_state.result`, keyed by `sha256(bytes) + policy` (`source_key`) |
| A stale result next to a new error is confusing | `run_processing` stores either `result` or `error`, never both |
| A `file_uploader` cannot be emptied by assigning to it | The uploader key includes `uploader_v`, and **Clear** increases it |
| "Load sample data" outside the form would use the previously submitted policy | It is a second submit button inside the same form |

State changes happen in `on_click` callbacks, which run before the script
re-renders. The page therefore always draws the state after the click, without
an extra `st.rerun()`.

## Data flow for one upload

1. The user presses **Process**. `on_process` reads the uploader value from session state.
2. `run_processing` hashes the bytes. If they match `source_key`, it keeps the current result.
3. `process_upload` reduces the name to a bare file name, runs `validate_upload` (extension, empty, size), then `TicketCsvReader`, `clean_records`, `summarise` and `quality_summary`, then `build_preview`.
4. The result or the error message is stored in session state.
5. `main()` renders the error box, the empty state, or the four tabs.

## What is logged
The app calls Day 3's `configure_logging("INFO")`. Stage counts and data-quality
warnings go to the terminal running Streamlit. Ticket descriptions are never
logged: Day 3's `RedactingFilter` masks them. Calling `configure_logging` on
every rerun replaces its handler, so log lines are not duplicated.
