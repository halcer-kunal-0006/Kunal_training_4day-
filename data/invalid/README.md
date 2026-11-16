# Invalid ticket files

Broken and messy ticket exports for trying out the dashboard's error detection.
Run `streamlit run app.py`, upload any file from this folder in the sidebar and
press **Process**. Each file has exactly one kind of problem, so you can see what
the app says about it.

Every file is also checked automatically by `tests/dashboard/test_invalid_data.py`,
through the service and through the real upload widget. That test fails if a file
is added here without an expected result, so keep this table and the test in step.

## Files the app rejects (red error box)

| File | What is wrong | Caught by | The message says |
|---|---|---|---|
| `empty.csv` | 0 bytes | `UploadError` | `is empty (0 bytes)` |
| `blank_lines_only.csv` | Only blank lines and spaces | `UploadError` | `contains only blank lines` |
| `tickets_export.txt` | Good data, but a `.txt` file | `UploadError` | `has the extension '.txt' instead of '.csv'` |
| `header_only.csv` | Header row but no tickets | `EmptyDatasetError` | `the file has a header row but no ticket records` |
| `missing_columns.csv` | No `customer_rating` or `status` column | `SchemaMismatchError` | `missing required column(s): customer_rating, status` |
| `renamed_columns.csv` | Columns named `id`, `type`, `urgency`, ... | `SchemaMismatchError` | `missing required column(s): ticket_id, ...` and lists the columns found |
| `duplicate_column.csv` | `status` appears twice in the header | `SchemaMismatchError` | `duplicated column(s): status` |
| `unquoted_comma.csv` | A description contains a comma without quotes | `MalformedFileError` | `line 4: expected 7 fields, found 8` |
| `missing_field.csv` | A row is one value short | `MalformedFileError` | `line 2: expected 7 fields, found 6` |
| `unclosed_quote.csv` | A quote is opened and never closed | `MalformedFileError` | `line 3: expected 7 fields, found 4` |
| `latin1_encoding.csv` | Saved as Latin-1 (`Café`), not UTF-8 | `MalformedFileError` | `the file is not valid UTF-8 text` |

## Files the app accepts, but flags problems in

| File | What is wrong | With **Keep first** | With **Reject** |
|---|---|---|---|
| `duplicate_ticket_ids.csv` | `T-101` appears twice | 3 clean tickets; Data quality shows 1 duplicate removed | Red error: `Ticket ID T-101 appears in record 1 and again in record 4` |
| `no_valid_ticket_ids.csv` | Every ticket ID is blank | Yellow warning: `No valid tickets remained after cleaning`; 2 rows dropped | Same |
| `dirty_values.csv` | One of each cleaning problem (see below) | 9 clean tickets, 8 invalid records | Red error: `Ticket ID T-101 appears in record 1 and again in record 10` |

`dirty_values.csv` holds one row for each data-quality rule:

| Row | Problem | Shown in Data quality as |
|---|---|---|
| `T-102` | Resolution time is `two hours` | `invalid_resolution_time_hours` |
| `T-103` | Resolution time is `-3` | `invalid_resolution_time_hours` |
| `T-104` | Rating `7` (above 1–5) | `invalid_customer_rating` |
| `T-105` | Rating `0` (below 1–5) | `invalid_customer_rating` |
| `T-106` | Priority `urgent` | `invalid_priority` |
| `T-107` | Category, priority and status empty | Filled in as `unknown` (counted as missing, not invalid) |
| `t-108 ` | Extra spaces and mixed case | Tidied to `T-108`, `billing`, `high`, `resolved` (not an error) |
| (blank ID) | No ticket ID | `missing_ticket_id`, row dropped |
| `T-101` again | Repeats the first ticket | `duplicate_ticket_id`, row dropped |
| `T-109` | Time `nan`, rating `inf` | `invalid_resolution_time_hours` and `invalid_customer_rating` |

Totals: 11 rows in, 9 clean tickets out, 8 invalid records, with these issue counts:
3 invalid times, 3 invalid ratings, 1 invalid priority, 1 missing ID and 1 duplicate.
