import argparse
import uuid
import random
from datetime import datetime, timedelta

CATEGORIES = [
    'Food', 'Travel', 'Electronics', 'Health', 'Entertainment',
    'Retail', 'Transport', 'Education', 'Services', 'Other',
]
COUNTRIES = [
    'MX', 'CO', 'BR', 'AR', 'CL', 'PE', 'EC', 'VE', 'BO',
    'PY', 'UY', 'CR', 'GT', 'PA', 'DO',
]

def generate_batch(batch_size=500, error_rate=0.15, seed=None):
    """
    Genera un batch de transacciones. Un porcentaje (error_rate) tiene
    errores deliberados: montos negativos, categorías inválidas,
    timestamps futuros, campos nulos o UUIDs malformados.
    """
    if seed is not None:
        random.seed(seed)

    now = datetime.now()
    one_year_ago = now - timedelta(days=365)
    total_seconds = int((now - one_year_ago).total_seconds())

    rows = []
    for _ in range(batch_size):
        row = {
            'transaction_id': str(uuid.uuid4()),
            'timestamp':      (one_year_ago + timedelta(seconds=random.randint(0, total_seconds)))
                              .strftime('%Y-%m-%d %H:%M:%S'),
            'user_id':        random.randint(1, 50_000),
            'merchant_id':    random.randint(1, 10_000),
            'amount':         round(random.uniform(0.01, 5_000.00), 2),
            'category':       random.choice(CATEGORIES),
            'country_code':   random.choice(COUNTRIES),
            'status':         random.choices(
                                  ['completed', 'failed', 'pending'],
                                  weights=[85, 10, 5],
                              )[0],
        }

        # Inject a random error into a percentage rows
        if random.random() < error_rate:
            error_type = random.choice([
                'negative_amount',
                'invalid_category',
                'future_timestamp',
                'null_field',
                'bad_uuid',
            ])

            if error_type == 'negative_amount':
                row['amount'] = round(random.uniform(-500, -0.01), 2)
            elif error_type == 'invalid_category':
                row['category'] = random.choice(['Gambling', 'Crypto', 'InvalidCat', ''])
            elif error_type == 'future_timestamp':
                future = now + timedelta(days=random.randint(2, 30))
                row['timestamp'] = future.strftime('%Y-%m-%d %H:%M:%S')
            elif error_type == 'null_field':
                field = random.choice(['user_id', 'merchant_id', 'amount', 'category'])
                row[field] = None
            elif error_type == 'bad_uuid':
                row['transaction_id'] = 'not-a-valid-uuid'

        rows.append(row)

    return rows

def main():
    parser = argparse.ArgumentParser(description='Genera transacciones con errores')
    parser.add_argument('--batch-size', type=int, default=500)
    parser.add_argument('--error-rate', type=float, default=0.15,
                        help='Proporción de filas con errores (0.0-1.0)')
    parser.add_argument('--seed', type=int, default=None)
    args = parser.parse_args()

    batch = generate_batch(args.batch_size, args.error_rate, args.seed)
    print(f"Generadas {len(batch)} transacciones ({args.error_rate*100:.0f}% con errores)")
    return batch

if __name__ == '__main__':
    main()
