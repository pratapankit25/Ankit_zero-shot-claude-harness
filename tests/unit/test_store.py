"""Analytics-store guardrails: read-only enforcement, timeouts, caps. No LLM."""
import pytest

from ingest import store
from ingest.loader import load_csv


@pytest.fixture
def small_table():
    loaded = load_csv(b"n,v\n" + b"".join(f"{i},{i * 2}\n".encode() for i in range(500)), "nums.csv")
    return loaded["table_name"]


@pytest.mark.parametrize("bad_sql", [
    "DELETE FROM t",
    "UPDATE t SET a=1",
    "INSERT INTO t VALUES (1)",
    "DROP TABLE t",
    "CREATE TABLE x (a)",
    "PRAGMA journal_mode=DELETE",
    "ATTACH DATABASE 'x' AS y",
    "SELECT 1; SELECT 2",
    "",
])
def test_non_select_rejected(bad_sql):
    with pytest.raises(store.QueryError):
        store.run_select(bad_sql)


def test_write_via_cte_blocked(small_table):
    # authorizer must block writes even if the validator were fooled
    with pytest.raises(store.QueryError):
        store.run_select(f'WITH x AS (SELECT 1) INSERT INTO "{small_table}" SELECT * FROM x')


def test_select_works_and_caps_rows(small_table):
    result = store.run_select(f'SELECT * FROM "{small_table}"', row_cap=200)
    assert result["row_count"] == 200
    assert result["truncated"] is True
    assert result["columns"] == ["n", "v"]


def test_aggregate_not_truncated(small_table):
    result = store.run_select(f'SELECT COUNT(*) AS total FROM "{small_table}"')
    assert result["rows"] == [[500]]
    assert result["truncated"] is False


def test_trailing_semicolon_tolerated(small_table):
    result = store.run_select(f'SELECT COUNT(*) FROM "{small_table}";')
    assert result["rows"][0][0] == 500


def test_sql_error_is_query_error(small_table):
    with pytest.raises(store.QueryError, match="SQL error"):
        store.run_select(f'SELECT missing_col FROM "{small_table}"')


def test_timeout_interrupts_runaway_query(small_table):
    # cartesian self-joins explode fast; 0.2s budget must interrupt it
    sql = f'SELECT COUNT(*) FROM "{small_table}" a, "{small_table}" b, "{small_table}" c, "{small_table}" d'
    with pytest.raises(store.QueryError, match="timed out"):
        store.run_select(sql, timeout_s=0.2)


def test_drop_table_guard():
    with pytest.raises(store.QueryError, match="Refusing"):
        store.drop_table("runs")  # only ds_<hex12> tables are droppable
