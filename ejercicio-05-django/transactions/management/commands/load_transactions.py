import time
import pyarrow.parquet as pq
from django.core.management.base import BaseCommand
from transactions.models import Transaction

class Command(BaseCommand):
    help = 'Load transactions from a Parquet file using real I/O chunking'

    def add_arguments(self, parser):
        parser.add_argument(
            '--parquet', required=True,
            help='Path to Parquet file (ej: ../data/transactions_1m_none.parquet)',
        )
        parser.add_argument(
            '--chunk-size', type=int, default=10_000,
            help='Rows per insertion batch (default: 10000)',
        )

    def handle(self, *args, **options):
        parquet_path = options['parquet']
        chunk_size   = options['chunk_size']

        # Open the Parquet without loading it completely into memory
        parquet_file = pq.ParquetFile(parquet_path)
        total_rows   = parquet_file.metadata.num_rows

        self.stdout.write(f"Loading {total_rows:,} transactions from {parquet_path}")
        self.stdout.write(f"Chunk size: {chunk_size:,}")

        inserted = 0
        start    = time.perf_counter()

        for batch in parquet_file.iter_batches(batch_size=chunk_size):
            df   = batch.to_pandas()
            objs = [
                Transaction(
                    transaction_id=row.transaction_id,
                    timestamp=row.timestamp,
                    user_id=row.user_id,
                    merchant_id=row.merchant_id,
                    amount=row.amount,
                    category=row.category,
                    country_code=row.country_code,
                    status=row.status,
                )
                for row in df.itertuples(index=False)
            ]

            Transaction.objects.bulk_create(objs, ignore_conflicts=True)
            inserted += len(objs)

            pct = inserted / total_rows * 100
            self.stdout.write(f"  {inserted:,} / {total_rows:,} ({pct:.1f}%)", ending='\r')

        elapsed = time.perf_counter() - start
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(f"✓ {inserted:,} rows loaded in {elapsed:.1f}s")
        )
