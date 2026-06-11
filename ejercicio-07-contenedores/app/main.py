import json
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from app.db import init_sqlite, init_duckdb, close_all, get_sqlite, get_duckdb
from app.cache import cache
from app.models import TransactionIn

START_TIME = None

# --- JSON logging to stdout ───

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

# --- Lifespan ───

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


app = FastAPI(title="Transactions API", lifespan=lifespan)

# --- GET /health ───

@app.get("/health")
def health():
    return {
        'status':         'ok',
        'uptime_s':       round(time.time() - START_TIME, 1),
        'cache_hit_rate': cache.hit_rate(),
        'connections': {
            'sqlite': get_sqlite() is not None,
            'duckdb': get_duckdb() is not None,
        },
    }

# --- GET /analytics/summary ───

@app.get("/analytics/summary")
def analytics_summary():
    cached = cache.get('analytics:summary')
    if cached is not None:
        return cached

    conn = get_duckdb()

    totals = conn.execute("""
        SELECT COUNT(*)    AS total_count,
               SUM(amount) AS total_amount,
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

# --- GET /analytics/top-merchants ───

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

# --- GET /users/{user_id}/transactions ───
@app.get("/users/{user_id}/transactions")
def user_transactions(
    user_id:   int,
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conn   = get_sqlite()
    offset = (page - 1) * page_size

    rows = conn.execute(
        "SELECT * FROM transactions WHERE user_id = ? "
        "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (user_id, page_size, offset),
    ).fetchall()

    if not rows and page == 1:
        exists = conn.execute(
            "SELECT 1 FROM transactions WHERE user_id = ? LIMIT 1",
            (user_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    return [dict(r) for r in rows]

# --- GET /users/{user_id}/stats ───

@app.get("/users/{user_id}/stats")
def user_stats(user_id: int):
    conn = get_sqlite()

    stats = conn.execute(
        "SELECT SUM(amount) AS total_amount, COUNT(*) AS transaction_count "
        "FROM transactions WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if stats["transaction_count"] == 0:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    top_category = conn.execute(
        "SELECT category FROM transactions WHERE user_id = ? "
        "GROUP BY category ORDER BY COUNT(*) DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    top_country = conn.execute(
        "SELECT country_code FROM transactions WHERE user_id = ? "
        "GROUP BY country_code ORDER BY COUNT(*) DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    return {
        'user_id':           user_id,
        'total_amount':      round(stats["total_amount"], 2),
        'transaction_count': stats["transaction_count"],
        'top_category':      top_category["category"],
        'country_code':      top_country["country_code"],
    }

# --- POST /transactions/batch ───

@app.post("/transactions/batch")
def batch_insert(transactions: list[TransactionIn]):
    if len(transactions) > 500:
        raise HTTPException(status_code=422, detail="Maximum 500 transactions per batch")

    conn = get_sqlite()

    seen   = set()
    unique = []
    for t in transactions:
        if t.transaction_id not in seen:
            seen.add(t.transaction_id)
            unique.append(t)

    ids          = [t.transaction_id for t in unique]
    placeholders = ",".join(["?"] * len(ids))
    existing     = {
        r[0] for r in conn.execute(
            f"SELECT transaction_id FROM transactions "
            f"WHERE transaction_id IN ({placeholders})", ids,
        ).fetchall()
    }

    to_insert = [t for t in unique if t.transaction_id not in existing]

    if to_insert:
        with conn:
            conn.executemany(
                "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)",
                [
                    (t.transaction_id, t.timestamp, t.user_id, t.merchant_id,
                     t.amount, t.category, t.country_code, t.status)
                    for t in to_insert
                ],
            )
        cache.invalidate_prefix('analytics:')
        logger.info(f"Batch insert: {len(to_insert)} rows")

    return {
        'received':            len(transactions),
        'duplicates_in_batch': len(transactions) - len(unique),
        'duplicates_in_db':    len(unique) - len(to_insert),
        'inserted':            len(to_insert),
    }
