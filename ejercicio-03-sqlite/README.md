# Ejercicio 3 — La Capa Transaccional
Base de datos SQLite optimizada para consultas transaccionales por usuario individual, con pipeline de ingesta eficiente y benchmark comparativo contra DuckDB.

## Requisitos

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- Dataset de 1M transacciones generado en el Ejercicio 1

## Regenerar la base desde cero

```bash
uv run python ingest.py --csv ../data/transactions_1m.csv --wal --chunk-size 10000
```

Esto crea `data/transactions.db` con la tabla, los índices y los 1M de registros.

## Correr el benchmark

```bash
uv run python benchmark_queries.py
```

## Correr todo desde cero

```bash
# Ingesta sin WAL
uv run python ingest.py --csv ../data/transactions_1m.csv --no-wal --chunk-size 10000

# Ingesta con WAL
uv run python ingest.py --csv ../data/transactions_1m.csv --wal --chunk-size 10000

# Benchmark de patrones
uv run python benchmark_queries.py
```

Los resultados se guardan en `results/`.

## Estructura

```
ejercicio-03-sqlite/
├── schema.sql              ← DDL: tabla + índices
├── schema_design.md        ← Justificación de cada decisión
├── ingest.py               ← CLI: --csv, --chunk-size, --wal/--no-wal
├── benchmark_queries.py    ← 5 patrones con/sin índices + DuckDB
├── results/
│   ├── ingest_wal.json
│   ├── ingest_nowal.json
│   └── benchmark_queries.json
└── README.md
```
