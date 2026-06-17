# Ejercicio 8 — El Proyecto Final

Sistema de monitoreo de transacciones para una fintech LATAM. Integra la API del E04, el pipeline del E06 y la infraestructura Docker del E07. Agrega detección de anomalías e ingesta de CSV por HTTP.

## Requisitos

- Docker instalado
- Parquet de 1M transacciones en `../data/` (generado en E01)

## Levantar el sistema

```bash
cd ejercicio-08-final
cp .env.example .env
docker compose up --build
```

## Verificar

```bash
docker compose ps
curl http://localhost:8000/health
```

## Endpoints

| Método | Ruta | Descripción | SLA |
|--------|------|-------------|-----|
| GET | `/health` | Estado del sistema, cache hit rate, conteo de transacciones | < 50ms |
| GET | `/analytics/summary` | Totales globales + breakdown por país y categoría | < 500ms cold / < 20ms warm |
| GET | `/analytics/top-merchants?limit=N&country=XX` | Top N merchants por volumen | < 500ms cold / < 20ms warm |
| GET | `/users/{id}/transactions?date_from=&date_to=&page=&page_size=` | Historial con filtros de fecha | < 80ms |
| GET | `/users/{id}/stats` | Monto total, conteo, categoría y país del usuario | < 80ms |
| GET | `/anomalies/failed-transactions?threshold=N&days=30` | Usuarios con > N fallas en los últimos 30 días | < 200ms |
| POST | `/ingest/csv` | Sube un CSV, lo valida y carga. Devuelve reporte | < 2s |

### Ejemplos con curl

```bash
# Analytics
curl http://localhost:8000/analytics/summary
curl "http://localhost:8000/analytics/top-merchants?limit=5&country=MX"

# Usuario con filtro de fecha
curl "http://localhost:8000/users/1/transactions?date_from=2026-01-01&date_to=2026-06-01"
curl http://localhost:8000/users/1/stats

# Detección de anomalías
curl "http://localhost:8000/anomalies/failed-transactions?threshold=3&days=30"

# Ingesta CSV
curl -X POST -F "file=@transactions_new.csv" http://localhost:8000/ingest/csv
```

## Correr tests

```bash
# Con Docker corriendo:
SQLITE_PATH=data/transactions.db PARQUET_PATH=../data/transactions_1m_none.parquet \
    PYTHONPATH=. uv run pytest tests/ -v

# O sin Docker (requiere la base SQLite y el Parquet):
cp .env.example .env
source .env
PYTHONPATH=. uv run pytest tests/ -v
```

## Parar y limpiar

```bash
docker compose down -v
```

## Arquitectura

```
                  ┌─────────────────────────────────┐
                  │          FastAPI App            │
                  │                                 │
     ┌────────────┼──────────────┬───────────┐      │
     │            │              │           │      │
  /analytics   /users     /anomalies   /ingest/csv  │
  (DuckDB)    (SQLite)     (SQLite)     (Pipeline)  │
     │            │              │           │      │
     └────────────┼──────────────┴───────────┘      │
                  │                                 │
                  │  ┌──────────┐  ┌─────────────┐  │
                  │  │  Cache   │  │  Pipeline   │  │
                  │  │  (TTL)   │  │  E→T→L      │  │
                  │  └──────────┘  └─────────────┘  │
                  └──────────┬──────────┬───────────┘
                             │          │
                  ┌──────────┴──┐ ┌─────┴──────────┐
                  │   DuckDB    │ │    SQLite      │
                  │  (Parquet)  │ │ (transactions) │
                  └─────────────┘ └────────────────┘
```
