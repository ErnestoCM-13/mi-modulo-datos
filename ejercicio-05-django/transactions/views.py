import time

import duckdb
from django.conf import settings
from django.db.models import Sum, Count
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from transactions.cache import cache
from transactions.models import Transaction
from transactions.serializers import TransactionSerializer, TransactionInSerializer

START_TIME = time.time()

# ── DuckDB (lazy init con pre-calentamiento) ──────────────────────────────────

_duckdb_conn = None

def get_duckdb():
    global _duckdb_conn
    if _duckdb_conn is None:
        _duckdb_conn = duckdb.connect()
        _duckdb_conn.execute(
            f"CREATE VIEW transactions AS "
            f"SELECT * FROM read_parquet('{settings.PARQUET_PATH}')"
        )
        # Pre-calentar: forzar lectura del Parquet a memoria
        _duckdb_conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
    return _duckdb_conn

# ── GET /health ────────────────────────────────────────────────────────────────

class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'status':         'ok',
            'uptime_s':       round(time.time() - START_TIME, 1),
            'cache_hit_rate': cache.hit_rate(),
        })

# ── GET /analytics/summary ─────────────────────────────────────────────────────

class AnalyticsSummaryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cached = cache.get('analytics:summary')
        if cached is not None:
            return Response(cached)

        conn = get_duckdb()

        totals = conn.execute("""
            SELECT COUNT(*)    AS total_count,
                   SUM(amount) AS total_amount,
                   AVG(amount) AS avg_amount
            FROM transactions
        """).fetchone()

        by_country = conn.execute("""
            SELECT country_code, COUNT(*) AS count, SUM(amount) AS total
            FROM transactions
            GROUP BY country_code
            ORDER BY total DESC
        """).fetchall()

        by_category = conn.execute("""
            SELECT category, COUNT(*) AS count, SUM(amount) AS total
            FROM transactions
            GROUP BY category
            ORDER BY total DESC
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
        return Response(result)

# ── GET /analytics/top-merchants ───────────────────────────────────────────────

class TopMerchantsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        limit   = int(request.query_params.get('limit', 10))
        country = request.query_params.get('country')

        cache_key = f'analytics:top-merchants:{limit}:{country}'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        conn = get_duckdb()

        if country:
            rows = conn.execute("""
                SELECT merchant_id, COUNT(*) AS transaction_count,
                       SUM(amount) AS total_volume
                FROM transactions
                WHERE country_code = ?
                GROUP BY merchant_id
                ORDER BY total_volume DESC
                LIMIT ?
            """, [country, limit]).fetchall()
        else:
            rows = conn.execute("""
                SELECT merchant_id, COUNT(*) AS transaction_count,
                       SUM(amount) AS total_volume
                FROM transactions
                GROUP BY merchant_id
                ORDER BY total_volume DESC
                LIMIT ?
            """, [limit]).fetchall()

        result = [
            {'merchant_id': r[0], 'transaction_count': r[1],
             'total_volume': round(r[2], 2)}
            for r in rows
        ]

        cache.set(cache_key, result, ttl=60)
        return Response(result)

# ── GET /users/{user_id}/transactions ──────────────────────────────────────────

class UserTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        page      = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        offset    = (page - 1) * page_size

        qs = (
            Transaction.objects
            .filter(user_id=user_id)
            .order_by('-timestamp')
        )[offset:offset + page_size]

        results = TransactionSerializer(qs, many=True).data

        if not results and page == 1:
            exists = Transaction.objects.filter(user_id=user_id).exists()
            if not exists:
                return Response(
                    {'detail': f'User {user_id} not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(results)

# ── GET /users/{user_id}/stats ─────────────────────────────────────────────────

class UserStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        stats = (
            Transaction.objects
            .filter(user_id=user_id)
            .aggregate(
                total_amount=Sum('amount'),
                transaction_count=Count('transaction_id'),
            )
        )

        if stats['transaction_count'] == 0:
            return Response(
                {'detail': f'User {user_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        top_category = (
            Transaction.objects
            .filter(user_id=user_id)
            .values('category')
            .annotate(cnt=Count('transaction_id'))
            .order_by('-cnt')
            .first()
        )

        top_country = (
            Transaction.objects
            .filter(user_id=user_id)
            .values('country_code')
            .annotate(cnt=Count('transaction_id'))
            .order_by('-cnt')
            .first()
        )

        return Response({
            'user_id':           user_id,
            'total_amount':      round(stats['total_amount'], 2),
            'transaction_count': stats['transaction_count'],
            'top_category':      top_category['category'],
            'country_code':      top_country['country_code'],
        })

# ── POST /transactions/batch ──────────────────────────────────────────────────

class BatchInsertView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not isinstance(request.data, list):
            return Response(
                {'detail': 'Expected a list of transactions'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if len(request.data) > 500:
            return Response(
                {'detail': 'Maximum 500 transactions per batch'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Validar cada transacción con el serializer
        serializer = TransactionInSerializer(data=request.data, many=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        validated = serializer.validated_data

        # Deduplicar dentro del batch
        seen   = set()
        unique = []
        for t in validated:
            if t['transaction_id'] not in seen:
                seen.add(t['transaction_id'])
                unique.append(t)

        # Verificar cuáles ya existen en la base
        existing_ids = set(
            Transaction.objects
            .filter(transaction_id__in=[t['transaction_id'] for t in unique])
            .values_list('transaction_id', flat=True)
        )

        to_insert = [t for t in unique if t['transaction_id'] not in existing_ids]

        if to_insert:
            objs = [Transaction(**t) for t in to_insert]
            Transaction.objects.bulk_create(objs)
            # Invalidar cache analítico
            cache.invalidate_prefix('analytics:')

        return Response({
            'received':            len(request.data),
            'duplicates_in_batch': len(request.data) - len(unique),
            'duplicates_in_db':    len(unique) - len(to_insert),
            'inserted':            len(to_insert),
        })
