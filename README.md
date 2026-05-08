# Mi-modulo-datos

Repositorio del módulo **Python para Sistemas de Datos Modernos**.  
Contiene 4 ejercicios que construyen un sistema de datos completo.

## Requisitos

- Python 3.11 o superior
- [uv](https://github.com/astral-sh/uv)

### Instalación

- Instalar dependencias:
  ```bash
  uv sync
  ```

## Estructura

```
mi-modulo-datos/
├── ejercicio-01-formatos/
│   ├── storage_benchmark/
│   │   ├── __init__.py
│   │   ├── writers.py
│   │   └── readers.py
│   ├── charts/
│   ├── results/
│   ├── generate_data.py
│   ├── benchmark_cli.py
│   ├── generate_charts.py
│   └── report.md
├── data/                  ← generado localmente, no incluido en el repo
├── .gitignore
└── README.md
```

## Ejercicio 1 — Formatos Bajo la Lupa

Herramienta de benchmarking que compara el rendimiento de 5 formatos de almacenamiento (CSV, JSON Lines, Parquet sin compresión, Parquet Snappy, Parquet Gzip) sobre un dataset de hasta 1 millón de registros.

### Uso

**1. Moverse en la carpeta del ejercicio**

```bash
cd ejercicio-01-formatos
```

**2. Generar el dataset**

```bash
uv run python generate_data.py --size 100k   # opciones: 100k, 500k, 1m
```

El archivo se guarda en `data/transactions_{size}.csv`.

**3. Correr el benchmark**

```bash
uv run python benchmark_cli.py --size 100k --formats csv jsonl parquet_none parquet_snappy parquet_gzip
```

Los resultados se guardan en `ejercicio-01-formatos/results/results_{size}.json`.

### Correr todo desde cero

```bash
cd ejercicio-01-formatos

for size in 100k 500k 1m; do
  uv run python benchmark_cli.py --size $size --formats csv jsonl parquet_none parquet_snappy parquet_gzip
done
```

### Charts

El directorio `ejercicio-01-formatos/charts/` contiene gráficas usadas en el reporte.

### Resultados

Los resultados del benchmark se encuentran en `ejercicio-01-formatos/results/`.

Esta carpeta incluye resultados de un benchmark realizado en entorno local para la redacción del reporte.

### Reporte

El repositorio cuenta con un reporte en [`ejercicio-01-formatos/report.md`](ejercicio-01-formatos/report.md) con los resultados completos y el análisis de un benchamrk realizado en entorno local.
