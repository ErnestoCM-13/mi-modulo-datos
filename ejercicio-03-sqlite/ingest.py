import argparse
import json
import sqlite3
import time
import pandas as pd
from pathlib import Path

def ingest(csv_path, db_path, schema_path, chunk_size, wal):
    """Carga el CSV a SQLite usando transacciones explícitas por chunk."""

    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if db_file.exists():
        db_file.unlink()

    conn = sqlite3.connect(db_path)

    if wal:
        conn.execute("PRAGMA journal_mode=WAL")

    # Leer schema y separar CREATE TABLE de CREATE INDEX
    with open(schema_path) as f:
        schema_sql = f.read()

    statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
    create_table   = statements[0]
    create_indexes = statements[1:]

    # Crear solo la tabla
    conn.execute(create_table)

    # Leer CSV completo en memoria
    df = pd.read_csv(csv_path)
    total_rows = len(df)

    # Insertar por chunks con transacciones explícitas
    start = time.perf_counter()

    for i in range(0, total_rows, chunk_size):
        chunk = df.iloc[i:i + chunk_size]
        with conn:
            conn.executemany(
                "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)",
                chunk.values.tolist()
            )

    # Crear índices despues de insertar todos los datos
    for idx_sql in create_indexes:
        conn.execute(idx_sql)
    conn.commit()

    elapsed = time.perf_counter() - start
    conn.close()

    return {
        'rows':       total_rows,
        'chunk_size': chunk_size,
        'wal':        wal,
        'time_s':     round(elapsed, 2),
        'db_size_mb': round(db_file.stat().st_size / 1e6, 1),
    }

def main():
    parser = argparse.ArgumentParser(description='Ingesta de CSV a SQLite')
    parser.add_argument('--csv',        default='../data/transactions_1m.csv',
                        help='Ruta al CSV de transacciones')
    parser.add_argument('--db',         default='data/transactions.db',
                        help='Ruta donde crear el archivo SQLite')
    parser.add_argument('--schema',     default='schema.sql',
                        help='Archivo SQL con el DDL')
    parser.add_argument('--chunk-size', type=int, default=10_000,
                        help='Filas por transacción (default: 10000)')
    parser.add_argument('--wal',        action='store_true', default=False,
                        help='Activar WAL mode')
    parser.add_argument('--no-wal',     dest='wal', action='store_false',
                        help='Desactivar WAL mode (default)')
    args = parser.parse_args()

    print(f"Ingesta de {args.csv} → {args.db}")
    print(f"Chunk size: {args.chunk_size} | WAL: {'sí' if args.wal else 'no'}")

    result = ingest(args.csv, args.db, args.schema, args.chunk_size, args.wal)

    print(f"\n✓ {result['rows']:,} filas insertadas en {result['time_s']}s")
    print(f"  Tamaño de la base: {result['db_size_mb']} MB")

    # Guardar resultado
    Path('results').mkdir(exist_ok=True)
    mode_label = 'wal' if args.wal else 'nowal'
    out = Path('results') / f'ingest_{mode_label}.json'
    out.write_text(json.dumps(result, indent=2))
    print(f"  Resultado guardado en {out}")

if __name__ == '__main__':
    main()
