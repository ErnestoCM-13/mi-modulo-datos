# Mi-modulo-datos

Repositorio del módulo **Python para Sistemas de Datos Modernos**.  
Contiene 5 ejercicios que construyen un sistema de datos completo.

## Requisitos

- Python 3.11 o superior
- [uv](https://github.com/astral-sh/uv)
- Docker (para E07 y E08)

### Instalación

- Instalar dependencias:
  ```bash
  uv sync
  ```

## Estructura

```
mi-modulo-datos/
├── ejercicio-01-formatos/
├── ejercicio-02-consultas/
├── ejercicio-03-sqlite/
├── ejercicio-04-sistema/
├── ejercicio-05-django/
├── ejercicio-06-pipelines/
├── ejercicio-07-contenedores/
├── data/                  ← generado localmente, no incluido en el repo
├── .gitignore
└── README.md
```

## Ejercicio 1 — Formatos Bajo la Lupa
 
Benchmarking de 5 formatos de almacenamiento sobre un dataset de hasta 1M de transacciones.
 
```bash
cd ejercicio-01-formatos && uv add pandas pyarrow numpy matplotlib
for size in 100k 500k 1m; do
  uv run python benchmark_cli.py --size $size --formats csv jsonl parquet_none parquet_snappy parquet_gzip
done
```
 
**Resultado:** Parquet Snappy es 12x más rápido que CSV en lectura, 21x en selectiva, 47% menos en disco.
 
---
 
## Ejercicio 2 — El Motor de Consultas
 
8 queries analíticas en pandas, DuckDB y Polars con validación de equivalencia y EXPLAIN ANALYZE.
 
```bash
cd ejercicio-02-consultas && uv add pandas polars duckdb pyarrow numpy
uv run python benchmark.py
```
 
**Resultado:** Polars ganó las 8 queries. DuckDB mostró predicate pushdown en Q5 leyendo solo el 7.4% del archivo.
 
---
 
## Ejercicio 3 — La Capa Transaccional
 
SQLite optimizada para consultas transaccionales con benchmark de impacto de índices vs DuckDB.
 
```bash
cd ejercicio-03-sqlite && uv add pandas duckdb pyarrow
uv run python ingest.py --parquet ../data/transactions_1m_none.parquet --wal
uv run python benchmark_queries.py
```
 
**Resultado:** SQLite con índices cumple los 5 SLAs (P1-P4 < 1ms, P5 = 9ms). Gana a DuckDB hasta 1,730x en lookups.
 
---
 
## Ejercicio 4 — El Sistema Completo
 
API FastAPI con arquitectura dual DuckDB + SQLite, cache con TTL y suite de tests.
 
```bash
cd ejercicio-04-sistema && uv add fastapi uvicorn pydantic duckdb pytest httpx numpy
cp -r ../ejercicio-03-sqlite/data ./data
PYTHONPATH=. uv run pytest tests/ -v
PYTHONPATH=. uv run uvicorn app.main:app
```
 
**Resultado:** Todos los SLAs cumplidos. Analytics warm ~2ms (67x mejora por cache). 11 tests pasando.
 
---
 
## Ejercicio 5 — El Backend con Estructura
 
Los mismos 6 endpoints reconstruidos con Django REST Framework: ORM, migraciones, autenticación por token y panel admin.
 
```bash
cd ejercicio-05-django && uv add django djangorestframework pyarrow duckdb
mkdir -p data
uv run python manage.py migrate
uv run python manage.py load_transactions --parquet ../data/transactions_1m_none.parquet
uv run python manage.py createsuperuser
uv run python manage.py test tests
uv run python manage.py runserver
```
 
**Resultado:** 10 tests pasando. Endpoints analíticos con DuckDB + cache, transaccionales con ORM + índices del E3. Admin panel funcional con filtros y búsqueda.

---
 
## Ejercicio 6 — El Pipeline de Datos
 
Pipeline ETL idempotente: extrae, normaliza, valida, carga en SQLite y envía rechazos a cuarentena.
 
```bash
cd ejercicio-06-pipelines && uv add pytest
uv run python pipeline.py --batch-size 500 --error-rate 0.15 --seed 42
uv run pytest tests/ -v
```
 
**Resultado:** 500 extraídas → 432 válidas (86.4%) → 432 insertadas. 68 rechazadas con 8 tipos de error detectados. 14 tests pasando. Idempotencia verificada con INSERT OR IGNORE.

---
 
## Ejercicio 7 — De tu Máquina al Mundo
 
Sistema del E04 contenerizado con Docker: multi-stage build, setup automático, healthcheck y JSON logging.
 
```bash
cd ejercicio-07-contenedores
cp .env.example .env
docker compose up --build
```
 
En otra terminal:
```bash
docker compose ps
curl http://localhost:8000/health
docker compose logs -f api
docker compose down -v
```
 
**Resultado:** Un solo comando levanta todo. Imagen < 300MB. Healthcheck cada 30s. Logs en JSON a stdout.
