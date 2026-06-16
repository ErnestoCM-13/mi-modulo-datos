import os
import sys
import sqlite3
from pathlib import Path

import duckdb

_sqlite_conn = None
_duckdb_conn = None

def _require_env(name: str) -> str:
    """Lee una variable de entorno. Falla con mensaje claro si no existe."""
    value = os.environ.get(name)
    if not value:
        sys.exit(f"ERROR: la variable de entorno {name} es requerida. "
                 f"Revisa .env.example para los valores esperados.")
    return value

def init_sqlite():
    global _sqlite_conn
    db_path = _require_env('SQLITE_PATH')

    if not Path(db_path).exists():
        sys.exit(f"ERROR: base SQLite no encontrada en {db_path}. "
                 f"Ejecuta el servicio 'setup' primero.")

    _sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
    _sqlite_conn.row_factory = sqlite3.Row
    _sqlite_conn.execute('PRAGMA journal_mode=WAL')
    _sqlite_conn.execute('PRAGMA synchronous=NORMAL')

def init_duckdb():
    global _duckdb_conn
    parquet_path = _require_env('PARQUET_PATH')

    if not Path(parquet_path).exists():
        sys.exit(f"ERROR: archivo Parquet no encontrado en {parquet_path}. "
                 f"Verifica que el volumen está montado correctamente.")

    _duckdb_conn = duckdb.connect()
    _duckdb_conn.execute(
        f"CREATE VIEW transactions AS SELECT * FROM read_parquet('{parquet_path}')"
    )
    # Pre-warm
    _duckdb_conn.execute("SELECT COUNT(*) FROM transactions").fetchone()

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
