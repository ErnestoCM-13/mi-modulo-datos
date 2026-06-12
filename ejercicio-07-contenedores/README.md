# Ejercicio 7 — De tu Máquina al Mundo

Sistema del ejercicio 4 (FastAPI + DuckDB + SQLite) contenerizado con Docker.
Un solo comando levanta todo desde cero en cualquier máquina.

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) instalado
- Archivo Parquet de 1M transacciones en `../data/` (generado en E01)

## Configuración

```bash
cd ejercicio-07-contenedores
cp .env.example .env
```

Verifica que `../data/transactions_1m_none.parquet` existe. Si no:

```bash
cd ../ejercicio-01-formatos
uv run python generate_data.py --size 1m
uv run python benchmark_cli.py --size 1m --formats parquet_none
cd ../ejercicio-07-contenedores
```

## Levantar el sistema desde cero

```bash
docker compose up --build
```

Esto hace tres cosas en orden:
1. Construye la imagen Docker (instala dependencias)
2. Ejecuta el servicio `setup` (crea la base SQLite desde el Parquet)
3. Arranca el servicio `api` en el puerto 8000

## Verificar que está corriendo

```bash
docker compose ps
```

```bash
curl http://localhost:8000/health
```

## Ver los logs en tiempo real

```bash
docker compose logs -f api
```

Los logs salen en formato JSON (un objeto por línea):
```json
{"timestamp": "2026-05-27 20:00:00,000", "level": "INFO", "message": "Servidor listo."}
```

## Probar los endpoints

```bash
# Analytics (públicos)
curl http://localhost:8000/analytics/summary
curl "http://localhost:8000/analytics/top-merchants?limit=5&country=MX"

# Usuarios
curl http://localhost:8000/users/1/transactions
curl http://localhost:8000/users/1/stats

# Health
curl http://localhost:8000/health
```

## Parar y limpiar todo

```bash
docker compose down -v
```

El flag `-v` elimina los volúmenes (incluida la base SQLite). La próxima vez que se levante el sistema, `setup` recreará la base desde el Parquet.

## Variables de entorno

Ver `.env.example` para la lista completa:

| Variable | Valor en contenedor | Descripción |
|----------|--------------------|-------------|
| `SQLITE_PATH` | `/data/db/transactions.db` | Ruta a la base SQLite dentro del contenedor |
| `PARQUET_PATH` | `/data/parquet/transactions_1m_none.parquet` | Ruta al Parquet dentro del contenedor |
| `PARQUET_DIR` | `./../data` | Directorio en el host con los archivos Parquet |

## Arquitectura Docker

```
┌─────────────────────────────────────────────────┐
│              docker compose up                  │
│                                                 │
│  ┌──────────┐         ┌──────────────────────┐  │
│  │  setup   │────────→│       api            │  │
│  │(run once)│  done   │  FastAPI :8000       │  │
│  └─────┬────┘         └──────────┬───────────┘  │
│        │                         │              │
│        └──────────┬──────────────┘              │
│                   │                             │
│            ┌──────┴──────┐                      │
│            │  db-data    │  ← volumen compartido│
│            │(SQLite .db) │                      │
│            └─────────────┘                      │
│                                                 │
│  ┌──────────────────────┐                       │
│  │  host: ../data/      │  ← montado read-only  │
│  │  (Parquet files)     │                       │
│  └──────────────────────┘                       │
└─────────────────────────────────────────────────┘
```
