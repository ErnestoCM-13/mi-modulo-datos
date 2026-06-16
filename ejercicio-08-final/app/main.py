import csv
import io
import json
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, UploadFile, File

from app.db import init_sqlite, init_duckdb, close_all, get_sqlite, get_duckdb
from app.cache import cache
from app.models import TransactionIn
from pipeline.extract import extract
from pipeline.transform import transform
from pipeline.load import load

START_TIME = None

# --- JSON logging ---

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'timestamp': self.formatTime(record, self.datefmt),
            'level':     record.levelname,
            'message':   record.getMessage(),
        })

logger = logging.getLogger('api')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --- Lifespan ---

@asynccontextmanager
async def lifespan(app):
    global START_TIME
    START_TIME = time.time()
    logger.info("Inicializando conexiones...")
    init_sqlite()
    init_duckdb()
    logger.info("Servidor listo.")
    yield
    logger.info("Cerrando conexiones...")
    close_all()

app = FastAPI(title="Fintech Transaction Monitor", lifespan=lifespan)

# --- GET /health ---

@app.get("/health")
def health():
    conn = get_sqlite()
    tx_count = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    return {
        'status':           'ok',
        'uptime_s':         round(time.time() - START_TIME, 1),
        'cache_hit_rate':   cache.hit_rate(),
        'transaction_count': tx_count,
        'connections': {
            'sqlite': get_sqlite() is not None,
            'duckdb': get_duckdb() is not None,
        },
    }

# --- GET /analytics/summary ---

@app.get("/analytics/summary")
def analytics_summary():
    cached = cache.get('analytics:summary')
    if cached is not None:
        return cached

    conn = get_duckdb()

    totals = conn.execute("""
        SELECT COUNT(*) AS total_count, SUM(amount) AS total_amount,
               AVG(amount) AS avg_amount
        FROM transactions
    """).fetchone()

    by_country = conn.execute("""
        SELECT country_code, COUNT(*) AS count, SUM(amount) AS total
        FROM transactions GROUP BY country_code ORDER BY total DESC
    """).fetchall()

    by_category = conn.execute("""
        SELECT category, COUNT(*) AS count, SUM(amount) AS total
        FROM transactions GROUP BY category ORDER BY total DESC
    """).fetchall()

    result = {
        'total_count':  totals[0],
        'total_amount': round(totals[1], 2),
        'avg_amount':   round(totals[2], 2),
        'by_country': [
            {'country_code': r[0], 'count': r[1], 'total_amount': round(r[2], 2)}
            for r in by_country
        ],
        'by_category': [
            {'category': r[0], 'count': r[1], 'total_amount': round(r[2], 2)}
            for r in by_category
        ],
    }

    cache.set('analytics:summary', result, ttl=60)
    logger.info("analytics/summary computed (cold)")
    return result

# --- GET /analytics/top-merchants ---

@app.get("/analytics/top-merchants")
def top_merchants(
    limit:   int = Query(10, ge=1, le=100),
    country: str = Query(None),
):
    cache_key = f'analytics:top-merchants:{limit}:{country}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    conn = get_duckdb()

    if country:
        rows = conn.execute("""
            SELECT merchant_id, COUNT(*) AS transaction_count,
                   SUM(amount) AS total_volume
            FROM transactions WHERE country_code = ?
            GROUP BY merchant_id ORDER BY total_volume DESC LIMIT ?
        """, [country, limit]).fetchall()
    else:
        rows = conn.execute("""
            SELECT merchant_id, COUNT(*) AS transaction_count,
                   SUM(amount) AS total_volume
            FROM transactions
            GROUP BY merchant_id ORDER BY total_volume DESC LIMIT ?
        """, [limit]).fetchall()

    result = [
        {'merchant_id': r[0], 'transaction_count': r[1], 'total_volume': round(r[2], 2)}
        for r in rows
    ]

    cache.set(cache_key, result, ttl=60)
    return result

# --- GET /users/{user_id}/transactions ---

@app.get("/users/{user_id}/transactions")
def user_transactions(
    user_id:   int,
    date_from: str = Query(None, description="Filtrar desde (YYYY-MM-DD)"),
    date_to:   str = Query(None, description="Filtrar hasta (YYYY-MM-DD)"),
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conn   = get_sqlite()
    offset = (page - 1) * page_size

    query  = "SELECT * FROM transactions WHERE user_id = ?"
    params = [user_id]

    if date_from:
        query += " AND timestamp >= ?"
        params.append(date_from)
    if date_to:
        query += " AND timestamp <= ?"
        params.append(date_to + " 23:59:59")

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([page_size, offset])

    rows = conn.execute(query, params).fetchall()

    if not rows and page == 1:
        exists = conn.execute(
            "SELECT 1 FROM transactions WHERE user_id = ? LIMIT 1", (user_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    return [dict(r) for r in rows]

# --- GET /users/{user_id}/stats ---

@app.get("/users/{user_id}/stats")
def user_stats(user_id: int):
    conn = get_sqlite()

    stats = conn.execute(
        "SELECT SUM(amount) AS total_amount, COUNT(*) AS transaction_count "
        "FROM transactions WHERE user_id = ?", (user_id,),
    ).fetchone()

    if stats["transaction_count"] == 0:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    top_category = conn.execute(
        "SELECT category FROM transactions WHERE user_id = ? "
        "GROUP BY category ORDER BY COUNT(*) DESC LIMIT 1", (user_id,),
    ).fetchone()

    top_country = conn.execute(
        "SELECT country_code FROM transactions WHERE user_id = ? "
        "GROUP BY country_code ORDER BY COUNT(*) DESC LIMIT 1", (user_id,),
    ).fetchone()

    return {
        'user_id':           user_id,
        'total_amount':      round(stats["total_amount"], 2),
        'transaction_count': stats["transaction_count"],
        'top_category':      top_category["category"],
        'country_code':      top_country["country_code"],
    }

# --- GET /anomalies/failed-transactions ---

@app.get("/anomalies/failed-transactions")
def anomalies_failed(
    threshold: int = Query(5, ge=1, description="Mínimo de transacciones fallidas"),
    days:      int = Query(30, ge=1, le=365, description="Ventana en días"),
):
    conn = get_sqlite()

    rows = conn.execute(
        "SELECT user_id, COUNT(*) AS failed_count "
        "FROM transactions "
        "WHERE status = 'failed' "
        "  AND timestamp >= datetime('now', ?)"
        "GROUP BY user_id "
        "HAVING COUNT(*) > ? "
        "ORDER BY failed_count DESC",
        (f'-{days} days', threshold),
    ).fetchall()

    return {
        'threshold':   threshold,
        'days':        days,
        'total_users': len(rows),
        'users': [
            {'user_id': r['user_id'], 'failed_count': r['failed_count']}
            for r in rows
        ],
    }

# --- POST /ingest/csv ---

@app.post("/ingest/csv")
async def ingest_csv(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=422, detail="Only CSV files accepted")

    content  = await file.read()
    text     = content.decode('utf-8')
    reader   = csv.DictReader(io.StringIO(text))
    raw_rows = []

    for row in reader:
        # Convert numeric types
        for int_field in ['user_id', 'merchant_id']:
            if row.get(int_field):
                try:
                    row[int_field] = int(row[int_field])
                except (ValueError, TypeError):
                    row[int_field] = None

        if row.get('amount'):
            try:
                row['amount'] = float(row['amount'])
            except (ValueError, TypeError):
                row['amount'] = None

        raw_rows.append(row)

    if not raw_rows:
        raise HTTPException(status_code=422, detail="CSV is empty or has no valid rows")

    # Pipeline: extract → transform → load
    normalized = extract(raw_rows)
    valid, rejected_summary = transform(normalized, quarantine_dir='/tmp/quarantine')
    load_result = load(valid, get_sqlite())

    # Invalidate analytic cache if rows were inserted
    if load_result['inserted'] > 0:
        cache.invalidate_prefix('analytics:')

    report = {
        'filename':         file.filename,
        'rows_extracted':   len(normalized),
        'rows_valid':       len(valid),
        'rows_rejected':    rejected_summary['total_rejected'],
        'rejected_by_type': rejected_summary['by_type'],
        'rows_inserted':    load_result['inserted'],
        'rows_duplicate':   load_result['duplicates'],
    }

    logger.info(f"CSV ingest: {file.filename} → {load_result['inserted']} inserted")
    return report
