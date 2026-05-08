import argparse
import pandas as pd
import numpy as np
import uuid
from datetime import datetime, timedelta
from pathlib import Path

CATEGORIES = [
    'Food', 'Travel', 'Electronics', 'Health', 'Entertainment',
    'Retail', 'Transport', 'Education', 'Services', 'Other'
]
COUNTRIES = ['MX', 'CO', 'BR', 'AR', 'CL', 'PE', 'EC', 'VE', 'BO', 'PY', 'UY', 'CR', 'GT', 'PA', 'DO']

def parse_size(size_str):
    s = size_str.lower()
    if s.endswith('k'):
        return int(s[:-1]) * 1_000
    elif s.endswith('m'):
        return int(s[:-1]) * 1_000_000
    raise ValueError(f"Tamaño no válido: {size_str}. Usa 100k, 500k o 1m.")

def generate_transactions(n):
    now = datetime.now()
    one_year_ago = now - timedelta(days=365)
    total_seconds = int((now - one_year_ago).total_seconds())

    offsets = np.random.randint(0, total_seconds, size=n)
    timestamps = [one_year_ago + timedelta(seconds=int(s)) for s in offsets]

    return pd.DataFrame({
        'transaction_id': [str(uuid.uuid4()) for _ in range(n)],
        'timestamp':      timestamps,
        'user_id':        np.random.randint(1, 50_001, size=n),
        'merchant_id':    np.random.randint(1, 10_001, size=n),
        'amount':         np.round(np.random.uniform(0.01, 5_000.00, size=n), 2),
        'category':       np.random.choice(CATEGORIES, size=n),
        'country_code':   np.random.choice(COUNTRIES, size=n),
        'status':         np.random.choice(
                              ['completed', 'failed', 'pending'],
                              size=n, p=[0.85, 0.10, 0.05]
                          ),
    })

def main():
    parser = argparse.ArgumentParser(description='Genera dataset de transacciones')
    parser.add_argument('--size', required=True, help='Tamaño: 100k, 500k, 1m')
    args = parser.parse_args()

    n = parse_size(args.size)
    script_path = Path(__file__).resolve()
    output_dir = script_path.parent.parent / 'data'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'transactions_{args.size.lower()}.csv'

    print(f"Generando {n:,} transacciones...")
    df = generate_transactions(n)

    print(f"Guardando en {output_path}...")
    df.to_csv(output_path, index=False)
    print(f"Listo. ({output_path.stat().st_size / 1e6:.1f} MB)")

if __name__ == '__main__':
    main()
