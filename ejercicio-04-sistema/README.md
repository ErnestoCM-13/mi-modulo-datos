# Ejercicio 4 — El Sistema Completo

API REST con FastAPI que sirve datos de transacciones usando una arquitectura dual:
DuckDB para endpoints analíticos y SQLite para endpoints transaccionales, con cache
en memoria y TTL configurable.

## Requisitos

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- Base SQLite del Ejercicio 3 (`data/transactions.db`)
- Parquet del Ejercicio 1 (`../data/transactions_1m_none.parquet`)

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `SQLITE_PATH` | `data/transactions.db` | Ruta a la base SQLite |
| `PARQUET_PATH` | `../data/transactions_1m_none.parquet` | Ruta al archivo Parquet |

## Arrancar el servidor

```bash
uv run uvicorn app.main:app --reload
```

El servidor arranca en `http://localhost:8000`. Documentación interactiva en `http://localhost:8000/docs`.

## Correr los tests

```bash
uv run pytest tests/ -v
```

## Correr el benchmark de latencia

Con el servidor corriendo en una terminal:

```bash
uv run python benchmarks/run_latency.py
```

Genera `benchmarks/latency_report.md` con p50, p95, p99 por endpoint y análisis cold vs warm.

## Diagrama de arquitectura

```
                    ┌────────────────────────────┐
                    │        FastAPI App         │
                    │                            │
                    │  ┌──────────────────────┐  │
                    │  │    Cache (memoria)   │  │
                    │  │    TTL por endpoint  │  │
                    │  └──────────┬───────────┘  │
                    │             │              │
                    │  ┌──────────┴───────────┐  │
                    │  │      Endpoints       │  │
                    │  └──┬──────────────┬----┘  │
                    │     │              │       │
                    └─────┼──────────────┼-------┘
                          │              │
               ┌──────────┴───┐  ┌───────┴─────────---┐
               │   DuckDB     │  │     SQLite         │
               │  (Parquet)   │  │  (transactions.db) │
               │              │  │                    │
               │  Analytics   │  │  Transaccional     │
               └──────────────┘  └────────────────────┘
```

## Endpoints

| Método | Ruta | Backend | SLA |
|--------|------|---------|-----|
| GET | `/analytics/summary` | DuckDB + cache | < 500ms cold / < 20ms warm |
| GET | `/analytics/top-merchants` | DuckDB + cache | < 500ms cold / < 20ms warm |
| GET | `/users/{user_id}/transactions` | SQLite | < 80ms |
| GET | `/users/{user_id}/stats` | SQLite | < 80ms |
| POST | `/transactions/batch` | SQLite | < 2s para 500 registros |
| GET | `/health` | Memoria | < 50ms |
