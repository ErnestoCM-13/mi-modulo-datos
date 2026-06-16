import os
import sqlite3
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

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

CHUNK_SIZE = 10_000

def main():
    db_path      = os.environ.get('SQLITE_PATH')
    parquet_path = os.environ.get('PARQUET_PATH')

    if not db_path:
        sys.exit("ERROR: SQLITE_PATH is required")
    if not parquet_path:
        sys.exit("ERROR: PARQUET_PATH is required")
    if not Path(parquet_path).exists():
        sys.exit(f"ERROR: Parquet not found at {parquet_path}")

    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    if db_file.exists():
        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
            if count > 0:
                print(f"Base ya existe con {count:,} registros. Nada que hacer.")
                conn.close()
                return
        except sqlite3.OperationalError:
            pass
        conn.close()

    print(f"Creando base SQLite en {db_path} desde {parquet_path}...")

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript(SCHEMA_SQL)

    parquet_file = pq.ParquetFile(parquet_path)
    total_rows   = parquet_file.metadata.num_rows
    inserted     = 0

    start = time.perf_counter()

    for batch in parquet_file.iter_batches(batch_size=CHUNK_SIZE):
        df = batch.to_pandas()
        df['timestamp'] = df['timestamp'].astype(str)
        with conn:
            conn.executemany(
                'INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?)',
                df.values.tolist(),
            )
        inserted += len(df)
        pct = inserted / total_rows * 100
        print(f"  {inserted:,} / {total_rows:,} ({pct:.1f}%)")

    elapsed = time.perf_counter() - start
    conn.close()

    print(f"\n✓ {inserted:,} registros cargados en {elapsed:.1f}s")

if __name__ == '__main__':
    main()
