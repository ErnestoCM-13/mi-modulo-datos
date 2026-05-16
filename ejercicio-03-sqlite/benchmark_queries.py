import argparse
import json
import sqlite3
import time
import duckdb
from pathlib import Path
from datetime import datetime, timedelta

REPETITIONS = 10

# ── Helpers ──

def measure(fn, repetitions=REPETITIONS):
    """Ejecuta fn() varias veces y devuelve (resultado, tiempo_promedio_s)."""
    times  = []
    result = None
    for _ in range(repetitions):
        t0     = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return result, round(sum(times) / len(times), 6)

def explain(conn, sql, params=()):
    """Captura el EXPLAIN QUERY PLAN de SQLite."""
    rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    return [row[3] for row in rows]

def get_test_values(conn):
    """Obtiene valores reales de la base para usar en las queries."""
    txn_id = conn.execute(
        "SELECT transaction_id FROM transactions LIMIT 1"
    ).fetchone()[0]

    user_id = conn.execute(
        "SELECT user_id FROM transactions GROUP BY user_id "
        "ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()[0]

    max_ts = conn.execute(
        "SELECT MAX(timestamp) FROM transactions"
    ).fetchone()[0]

    max_dt = datetime.fromisoformat(max_ts)
    one_month_ago    = (max_dt - timedelta(days=30)).isoformat()
    three_months_ago = (max_dt - timedelta(days=90)).isoformat()

    return {
        'transaction_id':   txn_id,
        'user_id':          user_id,
        'max_timestamp':    max_ts,
        'one_month_ago':    one_month_ago,
        'three_months_ago': three_months_ago,
        'country_code':     'MX',
        'min_transactions': 5,
    }

# ── Patrones SQLite ──

def run_sqlite_patterns(conn, tv):
    """Ejecuta los 5 patrones sobre SQLite y devuelve tiempos + EXPLAIN."""

    patterns = {}

    # P1 — Buscar por transaction_id exacto
    sql_p1 = "SELECT * FROM transactions WHERE transaction_id = ?"
    _, t = measure(lambda: conn.execute(sql_p1, (tv['transaction_id'],)).fetchone())
    patterns['P1'] = {
        'time_avg_s': t,
        'explain':    explain(conn, sql_p1, (tv['transaction_id'],)),
    }

    # P2 — Últimas 20 transacciones de un user_id
    sql_p2 = ("SELECT * FROM transactions WHERE user_id = ? "
              "ORDER BY timestamp DESC LIMIT 20")
    _, t = measure(lambda: conn.execute(sql_p2, (tv['user_id'],)).fetchall())
    patterns['P2'] = {
        'time_avg_s': t,
        'explain':    explain(conn, sql_p2, (tv['user_id'],)),
    }

    # P3 — Transacciones de un user_id en rango de fechas
    sql_p3 = ("SELECT * FROM transactions WHERE user_id = ? "
              "AND timestamp BETWEEN ? AND ?")
    params_p3 = (tv['user_id'], tv['three_months_ago'], tv['max_timestamp'])
    _, t = measure(lambda: conn.execute(sql_p3, params_p3).fetchall())
    patterns['P3'] = {
        'time_avg_s': t,
        'explain':    explain(conn, sql_p3, params_p3),
    }

    # P4 — Suma de amount de un user_id en el último mes
    sql_p4 = ("SELECT SUM(amount) FROM transactions WHERE user_id = ? "
              "AND timestamp >= ?")
    params_p4 = (tv['user_id'], tv['one_month_ago'])
    _, t = measure(lambda: conn.execute(sql_p4, params_p4).fetchone())
    patterns['P4'] = {
        'time_avg_s': t,
        'explain':    explain(conn, sql_p4, params_p4),
    }

    # P5 — Usuarios de un country_code con más de N transacciones
    sql_p5 = ("SELECT user_id, COUNT(*) AS cnt FROM transactions "
              "WHERE country_code = ? GROUP BY user_id HAVING cnt > ?")
    params_p5 = (tv['country_code'], tv['min_transactions'])
    _, t = measure(lambda: conn.execute(sql_p5, params_p5).fetchall())
    patterns['P5'] = {
        'time_avg_s': t,
        'explain':    explain(conn, sql_p5, params_p5),
    }

    return patterns

# ── Patrones DuckDB ──

def run_duckdb_patterns(parquet_path, tv):
    """Ejecuta los 5 patrones sobre DuckDB + Parquet."""
    conn = duckdb.connect()
    conn.execute(
        f"CREATE VIEW transactions AS SELECT * FROM read_parquet('{parquet_path}')"
    )

    patterns = {}

    # P1
    _, t = measure(lambda: conn.execute(
        "SELECT * FROM transactions WHERE transaction_id = ?",
        [tv['transaction_id']]
    ).fetchone())
    patterns['P1'] = {'time_avg_s': t}

    # P2
    _, t = measure(lambda: conn.execute(
        "SELECT * FROM transactions WHERE user_id = ? "
        "ORDER BY timestamp DESC LIMIT 20",
        [tv['user_id']]
    ).fetchall())
    patterns['P2'] = {'time_avg_s': t}

    # P3
    _, t = measure(lambda: conn.execute(
        "SELECT * FROM transactions WHERE user_id = ? "
        "AND timestamp BETWEEN ? AND ?",
        [tv['user_id'], tv['three_months_ago'], tv['max_timestamp']]
    ).fetchall())
    patterns['P3'] = {'time_avg_s': t}

    # P4
    _, t = measure(lambda: conn.execute(
        "SELECT SUM(amount) FROM transactions WHERE user_id = ? "
        "AND timestamp >= ?",
        [tv['user_id'], tv['one_month_ago']]
    ).fetchall())
    patterns['P4'] = {'time_avg_s': t}

    # P5
    _, t = measure(lambda: conn.execute(
        "SELECT user_id, COUNT(*) AS cnt FROM transactions "
        "WHERE country_code = ? GROUP BY user_id HAVING cnt > ?",
        [tv['country_code'], tv['min_transactions']]
    ).fetchall())
    patterns['P5'] = {'time_avg_s': t}

    conn.close()
    return patterns

# ── Main ──

def main():
    parser = argparse.ArgumentParser(description='Benchmark de patrones de acceso')
    parser.add_argument('--db',      default='data/transactions.db',
                        help='Ruta a la base SQLite')
    parser.add_argument('--parquet', default='../data/transactions_1m_none.parquet',
                        help='Ruta al Parquet para comparación con DuckDB')
    parser.add_argument('--output',  default='results/',
                        help='Directorio de resultados')
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    conn = sqlite3.connect(args.db)
    tv   = get_test_values(conn)

    print(f"Valores de prueba:")
    print(f"  transaction_id: {tv['transaction_id'][:20]}...")
    print(f"  user_id:        {tv['user_id']}")
    print(f"  country_code:   {tv['country_code']}")
    print()

    # ── Con índices ──
    print("▶ SQLite CON índices...")
    with_idx = run_sqlite_patterns(conn, tv)
    for p, data in with_idx.items():
        ms = data['time_avg_s'] * 1000
        print(f"   {p}: {ms:.2f}ms  |  {', '.join(data['explain'])}")

    # ── Sin índices ──
    print("\n▶ Eliminando índices personalizados...")
    conn.execute("DROP INDEX IF EXISTS idx_user_timestamp")
    conn.execute("DROP INDEX IF EXISTS idx_country_user")
    conn.close()

    conn = sqlite3.connect(args.db)

    print("▶ SQLite SIN índices...")
    without_idx = run_sqlite_patterns(conn, tv)
    for p, data in without_idx.items():
        ms = data['time_avg_s'] * 1000
        print(f"   {p}: {ms:.2f}ms  |  {', '.join(data['explain'])}")

    # ── Restaurar índices ──
    print("\n▶ Restaurando índices...")
    conn.execute("CREATE INDEX idx_user_timestamp ON transactions(user_id, timestamp)")
    conn.execute("CREATE INDEX idx_country_user ON transactions(country_code, user_id)")
    conn.close()

    # ── DuckDB sobre Parquet ──
    print("\n▶ DuckDB sobre Parquet...")
    duckdb_results = run_duckdb_patterns(args.parquet, tv)
    for p, data in duckdb_results.items():
        ms = data['time_avg_s'] * 1000
        print(f"   {p}: {ms:.2f}ms")

    # ── Guardar resultados ──
    results = {
        'test_values':        tv,
        'sqlite_with_idx':    with_idx,
        'sqlite_without_idx': without_idx,
        'duckdb_parquet':     duckdb_results,
    }

    out_file = output_dir / 'benchmark_queries.json'
    out_file.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n✓ Resultados guardados en {out_file}")

if __name__ == '__main__':
    main()
