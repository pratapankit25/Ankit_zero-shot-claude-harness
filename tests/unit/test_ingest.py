"""CSV ingest — parsing tolerance, full-data loading, profiling. No LLM."""
import pytest

from ingest import store
from ingest.loader import IngestError, load_csv
from tests_helpers import read_sample


def _load(name_or_bytes, filename="test.csv"):
    data = name_or_bytes if isinstance(name_or_bytes, bytes) else name_or_bytes.encode("utf-8")
    return load_csv(data, filename)


def test_full_fixture_loads_every_row():
    loaded = _load(read_sample("fir_records.csv"), "fir_records.csv")
    assert loaded["row_count"] == 3200
    # full-data check: a sampled/truncated load would fail this exact count
    result = store.run_select(f'SELECT COUNT(*) AS n FROM "{loaded["table_name"]}"')
    assert result["rows"][0][0] == 3200


def test_column_types_and_profile():
    loaded = _load(read_sample("personnel.csv"), "personnel.csv")
    cols = {c["name"]: c for c in loaded["columns"]}
    assert cols["sanctioned_strength"]["type"] == "integer"
    assert cols["district"]["type"] == "text"
    assert "Lucknow" in cols["district"]["top_values"] or cols["district"]["distinct_count"] == 8


def test_date_column_detected_and_iso():
    loaded = _load(read_sample("fir_records.csv"), "fir_records.csv")
    cols = {c["name"]: c for c in loaded["columns"]}
    assert cols["fir_date"]["type"] == "date"
    r = store.run_select(f'SELECT MAX(fir_date) FROM "{loaded["table_name"]}"')
    assert str(r["rows"][0][0]).startswith("2025-06")


def test_messy_headers_and_duplicates():
    csv_text = "District,District,,FIR Count\nLucknow,LKO,x,10\nAgra,AGR,y,5\n"
    loaded = _load(csv_text)
    names = [c["name"] for c in loaded["columns"]]
    assert names[0] == "district" and names[1] == "district_2"
    assert loaded["row_count"] == 2
    assert any("Duplicate header" in w for w in loaded["profile"]["warnings"])


def test_headerless_numeric_file():
    csv_text = "1,2024-01-05,100\n2,2024-01-06,200\n3,2024-01-07,300\n"
    loaded = _load(csv_text)
    assert [c["name"] for c in loaded["columns"]] == ["col_1", "col_2", "col_3"]
    assert loaded["row_count"] == 3
    assert any("No header row" in w for w in loaded["profile"]["warnings"])


def test_devanagari_content_survives():
    csv_text = "जिला,fir_count\nलखनऊ,10\nआगरा,5\n"
    loaded = _load(csv_text)
    result = store.run_select(f'SELECT * FROM "{loaded["table_name"]}" ORDER BY fir_count DESC')
    assert result["rows"][0][0] == "लखनऊ"


def test_cp1252_encoding_tolerated():
    data = "name,amount\nRam’s shop,5\n".encode("cp1252")
    loaded = load_csv(data, "win.csv")
    assert loaded["row_count"] == 1


def test_semicolon_delimiter_sniffed():
    loaded = _load("a;b;c\n1;2;3\n4;5;6\n")
    assert loaded["row_count"] == 2
    assert len(loaded["columns"]) == 3


def test_binary_file_rejected():
    with pytest.raises(IngestError, match="binary|Excel"):
        load_csv(b"PK\x03\x04\x00\x00fakexlsx" + b"\x00" * 100, "book.xlsx")


def test_empty_file_rejected():
    with pytest.raises(IngestError, match="empty"):
        load_csv(b"", "empty.csv")


def test_delete_drops_table():
    loaded = _load("a,b\n1,2\n")
    table = loaded["table_name"]
    store.drop_table(table)
    with pytest.raises(store.QueryError):
        store.run_select(f'SELECT * FROM "{table}"')
