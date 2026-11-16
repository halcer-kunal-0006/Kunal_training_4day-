"""The loader rejects bad paths and malformed files with specific errors, streams
records lazily, and always closes the file."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import HEADER, CsvFactory

from ticket_pipeline import (
    EmptyDatasetError,
    InvalidPathError,
    MalformedFileError,
    SchemaMismatchError,
    open_ticket_csv,
    validate_input_path,
)

ROW = "T-1,billing,high,Charged twice,2,5,resolved\n"


# --- path validation -------------------------------------------------------------------


def test_validate_input_path_missing_file_raises_invalid_path(tmp_path: Path) -> None:
    with pytest.raises(InvalidPathError, match="does not exist") as caught:
        validate_input_path(tmp_path / "missing.csv")

    assert caught.value.path == tmp_path / "missing.csv"


def test_validate_input_path_directory_raises_invalid_path(tmp_path: Path) -> None:
    folder = tmp_path / "data.csv"
    folder.mkdir()

    with pytest.raises(InvalidPathError, match="is not a file"):
        validate_input_path(folder)


@pytest.mark.parametrize("name", ["tickets.txt", "tickets.xlsx", "tickets"])
def test_validate_input_path_non_csv_extension_raises_invalid_path(
    csv_factory: CsvFactory, name: str
) -> None:
    with pytest.raises(InvalidPathError, match="instead of '.csv'"):
        validate_input_path(csv_factory(ROW, name=name))


def test_validate_input_path_accepts_upper_case_extension_and_strings(
    csv_factory: CsvFactory,
) -> None:
    path = csv_factory(ROW, name="TICKETS.CSV")

    assert validate_input_path(str(path)) == path


def test_open_ticket_csv_os_error_is_wrapped_and_chained(
    csv_factory: CsvFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = csv_factory(ROW)

    def deny(*args: object, **kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "open", deny)  # boundary: the operating system

    with pytest.raises(InvalidPathError, match="cannot be opened") as caught, open_ticket_csv(path):
        pass  # pragma: no cover - never reached
    assert isinstance(caught.value.__cause__, PermissionError)


# --- malformed content -----------------------------------------------------------------


def test_empty_file_raises_empty_dataset_on_open(csv_factory: CsvFactory) -> None:
    path = csv_factory("", header="")

    with pytest.raises(EmptyDatasetError, match="no header row"), open_ticket_csv(path):
        pass  # pragma: no cover - never reached


def test_header_only_file_raises_empty_dataset_when_read(csv_factory: CsvFactory) -> None:
    with (
        open_ticket_csv(csv_factory("")) as reader,
        pytest.raises(EmptyDatasetError, match="no ticket records"),
    ):
        list(reader)


@pytest.mark.parametrize(
    ("body", "line", "found"),
    [
        (ROW + "T-2,billing,high,Has, a comma,2,5,open\n", 3, 8),  # unquoted comma
        (ROW + ROW + "T-3,billing,high\n", 4, 3),  # truncated row
        ("T-1,a,b,c,d,e,f,g,h\n", 2, 9),
    ],
    ids=["extra-field", "missing-fields", "first-row"],
)
def test_wrong_field_count_raises_malformed_with_line_number(
    csv_factory: CsvFactory, body: str, line: int, found: int
) -> None:
    with open_ticket_csv(csv_factory(body)) as reader, pytest.raises(MalformedFileError) as caught:
        list(reader)

    assert caught.value.line == line
    assert f"line {line}: expected 7 fields, found {found}" in str(caught.value)
    assert "double quotes" in str(caught.value)  # the hint


def test_non_utf8_file_raises_malformed_and_keeps_the_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "latin1.csv"
    path.write_bytes((HEADER + "T-1,billing,high,Caf\xe9,2,5,open\n").encode("latin-1"))

    # Decoding happens while the header is read, so the error can come from the open itself.
    with (
        pytest.raises(MalformedFileError, match="UTF-8") as caught,
        open_ticket_csv(path) as reader,
    ):
        list(reader)

    assert isinstance(caught.value.__cause__, UnicodeDecodeError)


def test_csv_parser_error_raises_malformed_and_keeps_the_csv_error(
    csv_factory: CsvFactory,
) -> None:
    path = csv_factory("T-1,billing,high," + "x" * 50 + ",2,5,open\n")
    old_limit = csv.field_size_limit(30)  # header fields fit; the 50-char field does not
    try:
        with open_ticket_csv(path) as reader, pytest.raises(MalformedFileError) as caught:
            list(reader)
    finally:
        csv.field_size_limit(old_limit)

    assert isinstance(caught.value.__cause__, csv.Error)


@pytest.mark.parametrize(
    "header",
    [
        HEADER.replace("status", "state"),
        HEADER.replace("ticket_id,", ""),
    ],
    ids=["renamed-column", "dropped-column"],
)
def test_schema_mismatch_is_raised_on_open_before_any_row(
    csv_factory: CsvFactory, header: str
) -> None:
    with pytest.raises(SchemaMismatchError), open_ticket_csv(csv_factory("", header=header)):
        pass  # pragma: no cover - never reached


# --- successful reads ------------------------------------------------------------------


def test_records_are_numbered_from_one_and_keyed_by_column(csv_factory: CsvFactory) -> None:
    with open_ticket_csv(csv_factory(ROW + ROW)) as reader:
        records = list(reader)

    assert [record.record_number for record in records] == [1, 2]
    assert records[0].values["ticket_id"] == "T-1"
    assert records[0].values["status"] == "resolved"


def test_blank_lines_are_skipped_but_line_numbers_stay_accurate(csv_factory: CsvFactory) -> None:
    with open_ticket_csv(csv_factory(ROW + "\n\n" + ROW)) as reader:
        records = list(reader)

    assert [(record.record_number, record.line) for record in records] == [(1, 2), (2, 5)]


def test_quoted_commas_and_line_breaks_stay_inside_one_field(csv_factory: CsvFactory) -> None:
    body = 'T-1,billing,high,"Two lines,\nwith a comma",2,5,open\n'

    with open_ticket_csv(csv_factory(body)) as reader:
        (record,) = list(reader)

    assert record.values["description"] == "Two lines,\nwith a comma"


def test_byte_order_mark_and_header_spaces_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "excel.csv"
    spaced_header = HEADER.replace(",", " , ")
    path.write_bytes(("﻿" + spaced_header + ROW).encode("utf-8"))

    with open_ticket_csv(path) as reader:
        assert reader.header[0] == "ticket_id"
        assert next(iter(reader)).values["ticket_id"] == "T-1"


def test_records_are_read_lazily(csv_factory: CsvFactory) -> None:
    # Line 3 is malformed, but reading only the first record must not touch it.
    with open_ticket_csv(csv_factory(ROW + "broken\n")) as reader:
        records: Iterator[object] = iter(reader)
        assert next(records) is not None


# --- resource safety -------------------------------------------------------------------


def test_file_is_closed_after_the_with_block(csv_factory: CsvFactory) -> None:
    with open_ticket_csv(csv_factory(ROW)) as reader:
        assert not reader.closed

    assert reader.closed


def test_file_is_closed_when_an_error_escapes_the_with_block(csv_factory: CsvFactory) -> None:
    with pytest.raises(MalformedFileError), open_ticket_csv(csv_factory("bad\n")) as reader:
        list(reader)

    assert reader.closed


def test_file_is_closed_when_the_reader_stops_early(csv_factory: CsvFactory) -> None:
    with open_ticket_csv(csv_factory(ROW * 3)) as reader:
        for _ in reader:
            break

    assert reader.closed
