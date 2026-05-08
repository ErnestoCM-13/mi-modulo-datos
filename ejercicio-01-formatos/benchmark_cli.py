import argparse
import json
from pathlib import Path
from generate_data import parse_size, generate_transactions
from storage_benchmark.writers import benchmark_write
from storage_benchmark.readers import benchmark_read

VALID_FORMATS = ['csv', 'jsonl', 'parquet_none', 'parquet_snappy', 'parquet_gzip']

def main():
    parser = argparse.ArgumentParser(description='Benchmark de formatos de almacenamiento')
    parser.add_argument('--size',    required=True, help='Tamaño: 100k, 500k, 1m')
    parser.add_argument('--formats', nargs='+', required=True,
                        choices=VALID_FORMATS,
                        help=f'Uno o más de: {", ".join(VALID_FORMATS)}')
    args = parser.parse_args()

    size = args.size.lower()
    n = parse_size(size)

    print(f"Generando {n:,} transacciones en memoria...")
    df = generate_transactions(n)
    print("Dataset listo.\n")

    results = {'scale': size}

    for fmt in args.formats:
        print(f"▶ Benchmarking {fmt}...")
        write_m = benchmark_write(df, fmt, size)
        read_m  = benchmark_read(fmt, size)
        results[fmt] = {**write_m, **read_m}
        print(f"   Write avg : {write_m['write_avg_s']}s")
        print(f"   Read full : {read_m['read_full_avg_s']}s")
        print(f"   Read sel  : {read_m['read_selective_avg_s']}s")
        print(f"   Disk size : {write_m['file_size_bytes'] / 1e6:.1f} MB")
        print(f"   Peak RAM  : {read_m['peak_memory_mb']} MB\n")

    current_dir = Path(__file__).resolve().parent
    output_dir = current_dir / 'results'
    output_dir.mkdir(exist_ok=True)
    out = output_dir / f'results_{size}.json'
    out.write_text(json.dumps(results, indent=2))
    print(f"Resultados guardados en {out}")

if __name__ == '__main__':
    main()
