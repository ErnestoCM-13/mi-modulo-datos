import sqlite3
import duckdb

_sqlite_conn = None
_duckdb_conn = None

def init_sqlite(db_path: str):
    global _sqlite_conn
    _sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
    _sqlite_conn.row_factory = sqlite3.Row

def init_duckdb(parquet_path: str):
    global _duckdb_conn
    _duckdb_conn = duckdb.connect()
    _duckdb_conn.execute(
        f"CREATE VIEW transactions AS SELECT * FROM read_parquet('{parquet_path}')"
    )

def get_sqlite() -> sqlite3.Connection:
    return _sqlite_conn

def get_duckdb() -> duckdb.DuckDBPyConnection:
    return _duckdb_conn

def close_all():
    global _sqlite_conn, _duckdb_conn
    if _sqlite_conn:
        _sqlite_conn.close()
        _sqlite_conn = None
    if _duckdb_conn:
        _duckdb_conn.close()
        _duckdb_conn = None
