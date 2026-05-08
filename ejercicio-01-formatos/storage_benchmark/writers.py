import time
import pandas as pd
from pathlib import Path

def get_path(data_dir, fmt, size):
    names = {
        'csv':            f'transactions_{size}.csv',
        'jsonl':          f'transactions_{size}.jsonl',
        'parquet_none':   f'transactions_{size}_none.parquet',
        'parquet_snappy': f'transactions_{size}_snappy.parquet',
        'parquet_gzip':   f'transactions_{size}_gzip.parquet',
    }
    return Path(data_dir) / names[fmt]

WRITERS = {
    'csv':            lambda df, p: df.to_csv(p, index=False),
    'jsonl':          lambda df, p: df.to_json(p, orient='records', lines=True),
    'parquet_none':   lambda df, p: df.to_parquet(p, compression=None,    index=False),
    'parquet_snappy': lambda df, p: df.to_parquet(p, compression='snappy', index=False),
    'parquet_gzip':   lambda df, p: df.to_parquet(p, compression='gzip',   index=False),
}

def benchmark_write(df, fmt, size, data_dir='data', repetitions=3):
    path = get_path(data_dir, fmt, size)
    write_fn = WRITERS[fmt]

    times = []
    for _ in range(repetitions):
        start = time.perf_counter()
        write_fn(df, path)
        times.append(time.perf_counter() - start)

    return {
        'write_avg_s':    round(sum(times) / len(times), 4),
        'file_size_bytes': path.stat().st_size,
        'path':           str(path),
    }
