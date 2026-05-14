import argparse
import json
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import duckdb

from engines import pandas_engine, duckdb_engine, polars_engine

QUERIES = ['q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8']

def measure(fn, *args, repetitions=3):
    """Ejecuta fn(*args) tres veces y devuelve (resultado, tiempo_promedio_s, pico_ram_mb)."""
    times    = []
    peak_mem = 0
    result   = None

    for _ in range(repetitions):
        tracemalloc.start()
        t0     = time.perf_counter()
        result = fn(*args)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        times.append(elapsed)
        peak_mem = max(peak_mem, peak)

    return result, round(sum(times) / len(times), 4), round(peak_mem / 1024 / 1024, 2)

def to_comparable(result) -> pd.DataFrame:
    """Convierte cualquier resultado a pandas y lo ordena para comparación consistente."""
    if isinstance(result, pl.DataFrame):
        result = result.to_pandas()
    return result.sort_values(by=list(result.columns)).reset_index(drop=True)

def validate(pd_result, ddb_result, pl_result):
    """
    Compara los resultados de los tres engines.
    Devuelve (True, []) si son equivalentes, o (False, [lista de problemas]) si no.
    """
    issues = []

    pd_norm  = to_comparable(pd_result)
    ddb_norm = to_comparable(ddb_result)
    pl_norm  = to_comparable(pl_result)

    # Primero verificar que tienen el mismo número de filas y columnas
    if pd_norm.shape != ddb_norm.shape:
        issues.append(f"pandas vs duckdb: formas distintas {pd_norm.shape} vs {ddb_norm.shape}")
    if pd_norm.shape != pl_norm.shape:
        issues.append(f"pandas vs polars: formas distintas {pd_norm.shape} vs {pl_norm.shape}")

    if issues:
        return False, issues

    # Comparar columnas numéricas con tolerancia del 0.1%
    for col in pd_norm.columns:
        if pd.api.types.is_numeric_dtype(pd_norm[col]):
            try:
                if not np.allclose(pd_norm[col].values, ddb_norm[col].values,
                                   rtol=1e-3, equal_nan=True):
                    issues.append(f"  columna '{col}': pandas vs duckdb no coinciden")
                if not np.allclose(pd_norm[col].values, pl_norm[col].values,
                                   rtol=1e-3, equal_nan=True):
                    issues.append(f"  columna '{col}': pandas vs polars no coinciden")
            except Exception as e:
                issues.append(f"  columna '{col}': error al comparar — {e}")

    return len(issues) == 0, issues

def main():
    parser = argparse.ArgumentParser(description='Benchmark de query engines')
    parser.add_argument('--parquet', default='../data/transactions_1m_none.parquet',
                        help='Ruta al Parquet de 1M transacciones del ejercicio 1')
    parser.add_argument('--output',  default='results/',
                        help='Directorio donde guardar los resultados JSON')
    args = parser.parse_args()

    parquet_path = Path(args.parquet)
    output_dir   = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    # ── Cargar datos una sola vez por engine ───────────────────────────────────
    print(f"Cargando datos desde {parquet_path}...")
    pd_df = pd.read_parquet(parquet_path)
    pl_df = pl.read_parquet(parquet_path)
    conn  = duckdb.connect()
    conn.execute(
        f"CREATE VIEW transactions AS SELECT * FROM read_parquet('{parquet_path}')"
    )
    print("Datos listos.\n")

    # ── Ejecutar benchmark para cada query ────────────────────────────────────
    results = {}

    for q_name in QUERIES:
        q_id = q_name.upper()
        print(f"▶ {q_id}...")

        pd_fn  = getattr(pandas_engine, q_name)
        ddb_fn = getattr(duckdb_engine, q_name)
        pl_fn  = getattr(polars_engine, q_name)

        pd_result,  pd_time,  pd_mem  = measure(pd_fn,  pd_df)
        ddb_result, ddb_time, ddb_mem = measure(ddb_fn, conn)
        pl_result,  pl_time,  pl_mem  = measure(pl_fn,  pl_df)

        equivalent, issues = validate(pd_result, ddb_result, pl_result)
        status = '✓' if equivalent else '✗'

        print(f"   pandas={pd_time}s | duckdb={ddb_time}s | polars={pl_time}s | equiv={status}")
        for issue in issues:
            print(f"   ⚠  {issue}")

        results[q_id] = {
            'pandas': {'time_avg_s': pd_time,  'peak_memory_mb': pd_mem},
            'duckdb': {'time_avg_s': ddb_time, 'peak_memory_mb': ddb_mem},
            'polars': {'time_avg_s': pl_time,  'peak_memory_mb': pl_mem},
            'equivalent': equivalent,
            'issues':     issues,
        }

    # ── Capturar EXPLAIN ANALYZE para Q3, Q5 y Q6 ────────────────────────────
    print("\n▶ Capturando EXPLAIN ANALYZE para Q3, Q5, Q6...")
    explain = {}
    for q_id in ['Q3', 'Q5', 'Q6']:
        explain[q_id] = duckdb_engine.explain_analyze(conn, q_id)
        print(f"   {q_id} ✓")

    # ── Guardar resultados en JSON ─────────────────────────────────────────────
    out_file = output_dir / 'results_1m.json'
    out_file.write_text(json.dumps(
        {'results': results, 'explain_analyze': explain},
        indent=2,
        default=str
    ))
    print(f"\nResultados guardados en {out_file}")

if __name__ == '__main__':
    main()
