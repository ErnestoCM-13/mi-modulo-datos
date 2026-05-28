import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT    PRIMARY KEY,
    timestamp      TEXT    NOT NULL,
    user_id        INTEGER NOT NULL,
    merchant_id    INTEGER NOT NULL,
    amount         REAL    NOT NULL,
    category       TEXT    NOT NULL,
    country_code   TEXT    NOT NULL,
    status         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_timestamp ON transactions(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_country_user   ON transactions(country_code, user_id);
"""

def load(rows: list[dict], db_path: str = 'data/pipeline.db') -> dict:
    """
    Inserta filas válidas en SQLite con INSERT OR IGNORE.
    Transaccional: si falla a mitad, no queda nada a medias.

    Devuelve {'inserted': N, 'duplicates': M}.
    """
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript(SCHEMA_SQL)

    total_before = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]

    values = [
        (
            r['transaction_id'], r['timestamp'], r['user_id'], r['merchant_id'],
            r['amount'], r['category'], r['country_code'], r['status'],
        )
        for r in rows
    ]

    with conn:
        conn.executemany(
            'INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?)',
            values,
        )

    total_after = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    conn.close()

    inserted   = total_after - total_before
    duplicates = len(rows) - inserted

    return {
        'inserted':   inserted,
        'duplicates': duplicates,
    }
