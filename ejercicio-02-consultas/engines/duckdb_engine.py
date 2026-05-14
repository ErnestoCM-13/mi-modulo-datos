import duckdb

def q1(conn: duckdb.DuckDBPyConnection):
    return conn.execute("""
        SELECT country_code, COUNT(*) AS count
        FROM transactions
        GROUP BY country_code
        ORDER BY count DESC
    """).df()

def q2(conn: duckdb.DuckDBPyConnection):
    return conn.execute("""
        SELECT category,
               AVG(amount)  AS avg_amount,
               MIN(amount)  AS min_amount,
               MAX(amount)  AS max_amount
        FROM transactions
        GROUP BY category
        ORDER BY category
    """).df()

def q3(conn: duckdb.DuckDBPyConnection):
    return conn.execute("""
        SELECT user_id,
               SUM(amount) AS total_amount,
               COUNT(*)    AS transaction_count
        FROM transactions
        GROUP BY user_id
        ORDER BY total_amount DESC
        LIMIT 10
    """).df()

def q4(conn: duckdb.DuckDBPyConnection):
    return conn.execute("""
        SELECT HOUR(timestamp) AS hour, COUNT(*) AS count
        FROM transactions
        WHERE status = 'failed'
        GROUP BY hour
        ORDER BY hour
    """).df()

def q5(conn: duckdb.DuckDBPyConnection):
    return conn.execute("""
        WITH max_ts AS (
            SELECT MAX(timestamp) AS max_date FROM transactions
        )
        SELECT t.*
        FROM transactions t, max_ts
        WHERE t.amount > 500
          AND t.country_code IN ('MX', 'CO')
          AND t.timestamp >= max_ts.max_date - INTERVAL '30 days'
        ORDER BY t.transaction_id
    """).df()

def q6(conn: duckdb.DuckDBPyConnection):
    return conn.execute("""
        WITH counts AS (
            SELECT country_code,
                   category,
                   COUNT(*)     AS count,
                   AVG(amount)  AS avg_amount
            FROM transactions
            GROUP BY country_code, category
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY country_code
                       ORDER BY count DESC
                   ) AS rn
            FROM counts
        )
        SELECT country_code, category, count, avg_amount
        FROM ranked
        WHERE rn = 1
        ORDER BY country_code
    """).df()

def q7(conn: duckdb.DuckDBPyConnection):
    return conn.execute("""
        SELECT user_id, COUNT(*) AS failed_count
        FROM transactions
        WHERE status = 'failed'
        GROUP BY user_id
        HAVING COUNT(*) > 5
        ORDER BY failed_count DESC
    """).df()

def q8(conn: duckdb.DuckDBPyConnection):
    return conn.execute("""
        SELECT CAST(timestamp AS DATE) AS date,
               category,
               AVG(amount) AS avg_amount
        FROM transactions
        GROUP BY date, category
        ORDER BY date, category
    """).df()

def explain_analyze(conn: duckdb.DuckDBPyConnection, query_id: str) -> str:
    queries = {
        'Q3': """
            EXPLAIN ANALYZE
            SELECT user_id,
                   SUM(amount) AS total_amount,
                   COUNT(*)    AS transaction_count
            FROM transactions
            GROUP BY user_id
            ORDER BY total_amount DESC
            LIMIT 10
        """,
        'Q5': """
            EXPLAIN ANALYZE
            WITH max_ts AS (
                SELECT MAX(timestamp) AS max_date FROM transactions
            )
            SELECT t.*
            FROM transactions t, max_ts
            WHERE t.amount > 500
              AND t.country_code IN ('MX', 'CO')
              AND t.timestamp >= max_ts.max_date - INTERVAL '30 days'
            ORDER BY t.transaction_id
        """,
        'Q6': """
            EXPLAIN ANALYZE
            WITH counts AS (
                SELECT country_code,
                       category,
                       COUNT(*)     AS count,
                       AVG(amount)  AS avg_amount
                FROM transactions
                GROUP BY country_code, category
            ),
            ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY country_code
                           ORDER BY count DESC
                       ) AS rn
                FROM counts
            )
            SELECT country_code, category, count, avg_amount
            FROM ranked
            WHERE rn = 1
            ORDER BY country_code
        """,
    }
    rows = conn.execute(queries[query_id]).fetchall()
    return '\n'.join(row[1] for row in rows)
