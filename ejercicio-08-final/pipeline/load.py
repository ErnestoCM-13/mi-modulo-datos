import sqlite3

def load(rows: list[dict], conn: sqlite3.Connection) -> dict:
    """
    Inserta filas válidas en SQLite con INSERT OR IGNORE.
    Usa la conexión de la app (no abre una nueva).
    """
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
    inserted   = total_after - total_before
    duplicates = len(rows) - inserted

    return {'inserted': inserted, 'duplicates': duplicates}
