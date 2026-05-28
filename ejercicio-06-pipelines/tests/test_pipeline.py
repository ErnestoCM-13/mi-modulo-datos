import os
import sqlite3
import tempfile
import uuid

import pytest

from data_source import generate_batch
from extract import extract
from transform import transform
from load import load

def _make_valid_row(**overrides):
    """Genera una fila válida con valores por defecto."""
    row = {
        'transaction_id': str(uuid.uuid4()),
        'timestamp':      '2026-01-15 10:30:00',
        'user_id':        1,
        'merchant_id':    1,
        'amount':         100.50,
        'category':       'Food',
        'country_code':   'MX',
        'status':         'completed',
    }
    row.update(overrides)
    return row

# --- Extract ───

class TestExtract:
    def test_normalizes_country_code_to_uppercase(self):
        rows = [_make_valid_row(country_code='mx')]
        result = extract(rows)
        assert result[0]['country_code'] == 'MX'

    def test_rounds_amount_to_2_decimals(self):
        rows = [_make_valid_row(amount=123.456789)]
        result = extract(rows)
        assert result[0]['amount'] == 123.46

    def test_strips_whitespace(self):
        rows = [_make_valid_row(category='  Food  ', country_code=' mx ')]
        result = extract(rows)
        assert result[0]['category'] == 'Food'
        assert result[0]['country_code'] == 'MX'

# --- Transform ───

class TestTransform:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

    def test_valid_row_passes(self):
        rows = [_make_valid_row()]
        valid, summary = transform(rows, quarantine_dir=self.tmp_dir)
        assert len(valid) == 1
        assert summary['total_rejected'] == 0

    def test_rejects_negative_amount(self):
        rows = [_make_valid_row(amount=-10.0)]
        valid, summary = transform(rows, quarantine_dir=self.tmp_dir)
        assert len(valid) == 0
        assert summary['total_rejected'] == 1
        assert 'amount out of range' in summary['by_type']

    def test_rejects_amount_over_5000(self):
        rows = [_make_valid_row(amount=6000.00)]
        valid, summary = transform(rows, quarantine_dir=self.tmp_dir)
        assert len(valid) == 0
        assert summary['total_rejected'] == 1

    def test_rejects_invalid_category(self):
        rows = [_make_valid_row(category='Gambling')]
        valid, summary = transform(rows, quarantine_dir=self.tmp_dir)
        assert len(valid) == 0
        assert 'invalid category' in summary['by_type']

    def test_rejects_invalid_country(self):
        rows = [_make_valid_row(country_code='XX')]
        valid, summary = transform(rows, quarantine_dir=self.tmp_dir)
        assert len(valid) == 0
        assert 'invalid country_code' in summary['by_type']

    def test_rejects_future_timestamp(self):
        rows = [_make_valid_row(timestamp='2099-01-01 00:00:00')]
        valid, summary = transform(rows, quarantine_dir=self.tmp_dir)
        assert len(valid) == 0
        assert 'timestamp is in the future' in summary['by_type']

    def test_rejects_bad_uuid(self):
        rows = [_make_valid_row(transaction_id='not-a-uuid')]
        valid, summary = transform(rows, quarantine_dir=self.tmp_dir)
        assert len(valid) == 0
        assert 'transaction_id is not valid UUID4' in summary['by_type']

    def test_rejects_null_amount(self):
        rows = [_make_valid_row(amount=None)]
        valid, summary = transform(rows, quarantine_dir=self.tmp_dir)
        assert len(valid) == 0
        assert 'amount is null' in summary['by_type']

# --- Load ───

class TestLoad:
    def setup_method(self):
        self.tmp_db = os.path.join(tempfile.mkdtemp(), 'test.db')

    def test_inserts_valid_rows(self):
        rows = [_make_valid_row()]
        result = load(rows, db_path=self.tmp_db)
        assert result['inserted'] == 1
        assert result['duplicates'] == 0

    def test_idempotency(self):
        rows = [_make_valid_row()]
        result1 = load(rows, db_path=self.tmp_db)
        result2 = load(rows, db_path=self.tmp_db)
        assert result1['inserted'] == 1
        assert result2['inserted'] == 0
        assert result2['duplicates'] == 1

        conn = sqlite3.connect(self.tmp_db)
        count = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        conn.close()
        assert count == 1

# --- Pipeline end-to-end ───

class TestPipelineEndToEnd:
    def test_numbers_add_up(self):
        raw   = generate_batch(batch_size=200, error_rate=0.2, seed=42)
        normd = extract(raw)

        tmp_q  = tempfile.mkdtemp()
        tmp_db = os.path.join(tempfile.mkdtemp(), 'test.db')

        valid, rejected_summary = transform(normd, quarantine_dir=tmp_q)
        load_result = load(valid, db_path=tmp_db)

        assert len(normd) == len(valid) + rejected_summary['total_rejected']

        assert len(valid) == load_result['inserted'] + load_result['duplicates']
