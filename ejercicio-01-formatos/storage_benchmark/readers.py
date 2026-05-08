import time
import tracemalloc
import pandas as pd
from storage_benchmark.writers import get_path

def _read_full(fmt, path):
    if fmt == 'csv':
        return pd.read_csv(path)
    elif fmt == 'jsonl':
        return pd.read_json(path, orient='records', lines=True)
    else:
        return pd.read_parquet(path)

def _read_selective(fmt, path):
    cols = ['amount', 'category']
    if fmt == 'csv':
        return pd.read_csv(path, usecols=cols)
    elif fmt == 'jsonl':
        return pd.read_json(path, orient='records', lines=True)[cols]
    else:
        return pd.read_parquet(path, columns=cols)

def benchmark_read(fmt, size, data_dir='data', repetitions=3):
    path = get_path(data_dir, fmt, size)

    # Lectura completa — mide tiempo y RAM
    full_times = []
    peak_mem = 0
    for _ in range(repetitions):
        tracemalloc.start()
        start = time.perf_counter()
        _read_full(fmt, path)
        elapsed = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        full_times.append(elapsed)
        peak_mem = max(peak_mem, peak)

    # Lectura selectiva — solo amount y category
    sel_times = []
    for _ in range(repetitions):
        start = time.perf_counter()
        _read_selective(fmt, path)
        sel_times.append(time.perf_counter() - start)

    return {
        'read_full_avg_s':      round(sum(full_times) / len(full_times), 4),
        'read_selective_avg_s': round(sum(sel_times)  / len(sel_times),  4),
        'peak_memory_mb':       round(peak_mem / 1024 / 1024, 2),
    }
