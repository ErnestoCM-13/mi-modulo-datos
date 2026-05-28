import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from data_source import generate_batch
from extract import extract
from transform import transform
from load import load

def run_pipeline(batch_size=500, error_rate=0.15, seed=None,
                 db_path='data/pipeline.db', quarantine_dir='quarantine'):
    """
    Ejecuta extract → transform → load y devuelve un reporte completo.
    """
    start = time.perf_counter()

    # --- Extract ───
    print(f"▶ Generando batch de {batch_size} transacciones (error_rate={error_rate})...")
    raw    = generate_batch(batch_size=batch_size, error_rate=error_rate, seed=seed)
    normalized = extract(raw)
    print(f"  Extraídas y normalizadas: {len(normalized)}")

    # --- Transform ───
    print("▶ Validando reglas de negocio...")
    valid, rejected_summary = transform(normalized, quarantine_dir=quarantine_dir)
    print(f"  Válidas: {len(valid)} | Rechazadas: {rejected_summary['total_rejected']}")
    if rejected_summary['by_type']:
        for error_type, count in sorted(rejected_summary['by_type'].items()):
            print(f"    {error_type}: {count}")

    # --- Load ───
    print(f"▶ Cargando en {db_path}...")
    load_result = load(valid, db_path=db_path)
    print(f"  Insertadas: {load_result['inserted']} | Duplicadas: {load_result['duplicates']}")

    elapsed = time.perf_counter() - start

    # --- Report ───
    report = {
        'timestamp':       datetime.now().isoformat(),
        'batch_size':      batch_size,
        'error_rate':      error_rate,
        'rows_extracted':  len(normalized),
        'rows_valid':      len(valid),
        'rows_rejected':   rejected_summary['total_rejected'],
        'rejected_by_type': rejected_summary['by_type'],
        'rows_inserted':   load_result['inserted'],
        'rows_duplicate':  load_result['duplicates'],
        'time_s':          round(elapsed, 3),
    }

    # --- Verification ---
    assert report['rows_extracted'] == report['rows_valid'] + report['rows_rejected'], \
        "Error: extracted != valid + rejected"
    assert report['rows_valid'] == report['rows_inserted'] + report['rows_duplicate'], \
        "Error: valid != inserted + duplicate"

    return report

def save_report(report: dict, results_dir: str = 'results'):
    """Guarda el reporte como results/run_YYYYMMDD_HHMMSS.json."""
    rdir = Path(results_dir)
    rdir.mkdir(exist_ok=True)
    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = rdir / f'run_{ts}.json'
    filename.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n✓ Reporte guardado en {filename}")
    return filename

def main():
    parser = argparse.ArgumentParser(description='Pipeline ETL de transacciones')
    parser.add_argument('--batch-size',    type=int,   default=500)
    parser.add_argument('--error-rate',    type=float, default=0.15)
    parser.add_argument('--seed',          type=int,   default=None)
    parser.add_argument('--db',            default='data/pipeline.db')
    parser.add_argument('--quarantine-dir', default='quarantine')
    parser.add_argument('--results-dir',   default='results')
    args = parser.parse_args()

    print(f"{'='*50}")
    print(f"  Pipeline ETL — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    report = run_pipeline(
        batch_size=args.batch_size,
        error_rate=args.error_rate,
        seed=args.seed,
        db_path=args.db,
        quarantine_dir=args.quarantine_dir,
    )

    save_report(report, results_dir=args.results_dir)

    print(f"\n  Tiempo total: {report['time_s']}s")
    print(f"  {report['rows_extracted']} extraídas → "
          f"{report['rows_valid']} válidas → "
          f"{report['rows_inserted']} insertadas")

if __name__ == '__main__':
    main()
