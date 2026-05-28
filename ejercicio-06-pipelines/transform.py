import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

VALID_CATEGORIES = {
    'Food', 'Travel', 'Electronics', 'Health', 'Entertainment',
    'Retail', 'Transport', 'Education', 'Services', 'Other',
}
VALID_COUNTRIES = {
    'MX', 'CO', 'BR', 'AR', 'CL', 'PE', 'EC', 'VE', 'BO',
    'PY', 'UY', 'CR', 'GT', 'PA', 'DO',
}

def _validate_row(row: dict) -> list[str]:
    """
    Valida una fila contra las reglas de negocio.
    Devuelve una lista de motivos de rechazo (vacía si la fila es válida).
    """
    reasons = []

    tid = row.get('transaction_id')
    if tid is None:
        reasons.append('transaction_id is null')
    else:
        try:
            parsed = uuid.UUID(str(tid), version=4)
            if str(parsed) != str(tid).lower():
                reasons.append(f'transaction_id is not valid UUID4: {tid}')
        except ValueError:
            reasons.append(f'transaction_id is not valid UUID4: {tid}')

    amount = row.get('amount')
    if amount is None:
        reasons.append('amount is null')
    elif not isinstance(amount, (int, float)):
        reasons.append(f'amount is not numeric: {amount}')
    elif amount < 0.01 or amount > 5_000.00:
        reasons.append(f'amount out of range: {amount}')

    cat = row.get('category')
    if cat is None:
        reasons.append('category is null')
    elif cat not in VALID_CATEGORIES:
        reasons.append(f'invalid category: {cat}')

    cc = row.get('country_code')
    if cc is None:
        reasons.append('country_code is null')
    elif cc not in VALID_COUNTRIES:
        reasons.append(f'invalid country_code: {cc}')

    ts = row.get('timestamp')
    if ts is None:
        reasons.append('timestamp is null')
    else:
        try:
            dt = datetime.strptime(str(ts), '%Y-%m-%d %H:%M:%S')
            if dt > datetime.now() + timedelta(hours=1):
                reasons.append(f'timestamp is in the future: {ts}')
        except ValueError:
            reasons.append(f'timestamp has invalid format: {ts}')

    if row.get('user_id') is None:
        reasons.append('user_id is null')
    if row.get('merchant_id') is None:
        reasons.append('merchant_id is null')

    return reasons

def _write_quarantine(rejected: list[dict], quarantine_dir: str = 'quarantine'):
    """Escribe las filas rechazadas a quarantine/YYYY-MM-DD.jsonl."""
    if not rejected:
        return

    qdir = Path(quarantine_dir)
    qdir.mkdir(exist_ok=True)
    filename = qdir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    with open(filename, 'a') as f:
        for entry in rejected:
            f.write(json.dumps(entry, default=str) + '\n')

def transform(rows: list[dict], quarantine_dir: str = 'quarantine'):
    """
    Valida reglas de negocio. Devuelve (valid, rejected_summary).

    - valid: lista de filas que pasaron todas las validaciones
    - rejected_summary: dict con conteos por tipo de error
    """
    valid    = []
    rejected = []
    error_counts = {}

    for row in rows:
        reasons = _validate_row(row)

        if not reasons:
            valid.append(row)
        else:
            rejected.append({
                'row':     row,
                'reasons': reasons,
            })
            for reason in reasons:
                error_type = reason.split(':')[0].strip()
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

    _write_quarantine(rejected, quarantine_dir)

    return valid, {
        'total_rejected': len(rejected),
        'by_type':        error_counts,
    }
