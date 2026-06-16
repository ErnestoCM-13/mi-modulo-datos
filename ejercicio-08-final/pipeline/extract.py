from datetime import datetime

def extract(raw_rows: list[dict]) -> list[dict]:
    """
    Normaliza formatos sin validar reglas de negocio.

    - timestamp → ISO 8601
    - country_code → mayúsculas
    - amount → redondeado a 2 decimales
    - strings → strip de espacios
    """
    normalized = []

    for row in raw_rows:
        clean = {}

        tid = row.get('transaction_id')
        clean['transaction_id'] = tid.strip() if isinstance(tid, str) else tid

        ts = row.get('timestamp')
        if isinstance(ts, str):
            ts = ts.strip()
            try:
                dt = datetime.fromisoformat(ts)
                clean['timestamp'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                clean['timestamp'] = ts
        else:
            clean['timestamp'] = ts

        clean['user_id']     = row.get('user_id')
        clean['merchant_id'] = row.get('merchant_id')

        amount = row.get('amount')
        if isinstance(amount, (int, float)):
            clean['amount'] = round(float(amount), 2)
        else:
            clean['amount'] = amount

        cat = row.get('category')
        clean['category'] = cat.strip() if isinstance(cat, str) else cat

        cc = row.get('country_code')
        clean['country_code'] = cc.strip().upper() if isinstance(cc, str) else cc

        st = row.get('status')
        clean['status'] = st.strip() if isinstance(st, str) else st

        normalized.append(clean)

    return normalized
