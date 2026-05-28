# Ejercicio 6 — El Pipeline de Datos
 
Pipeline ETL idempotente que extrae transacciones de una fuente simulada, normaliza
formatos, valida reglas de negocio, envía rechazos a cuarentena, y carga los datos
válidos en SQLite.
 
## Requisitos
 
- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
## Instalación
 
```bash
cd ejercicio-06-pipelines
uv sync
```
 
## Correr el pipeline
 
```bash
uv run python pipeline.py --batch-size 500 --error-rate 0.15 --seed 42
```
 
### Argumentos
 
| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--batch-size` | 500 | Transacciones a generar por ejecución |
| `--error-rate` | 0.15 | Proporción de filas con errores (0.0-1.0) |
| `--seed` | None | Semilla para reproducibilidad |
| `--db` | `data/pipeline.db` | Ruta a la base SQLite |
| `--quarantine-dir` | `quarantine/` | Directorio para filas rechazadas |
| `--results-dir` | `results/` | Directorio para reportes JSON |
 
## Estructura del reporte JSON
 
Cada ejecución genera un archivo `results/run_YYYYMMDD_HHMMSS.json`:
 
```json
{
  "timestamp": "2026-05-27T19:47:39",
  "batch_size": 500,
  "error_rate": 0.15,
  "rows_extracted": 500,
  "rows_valid": 432,
  "rows_rejected": 68,
  "rejected_by_type": {
    "amount out of range": 12,
    "invalid category": 17,
    "transaction_id is not valid UUID4": 14,
    "timestamp is in the future": 12,
    "user_id is null": 6,
    "amount is null": 3,
    "category is null": 3,
    "merchant_id is null": 1
  },
  "rows_inserted": 432,
  "rows_duplicate": 0,
  "time_s": 0.072
}
```
 
Invariantes verificadas en cada ejecución:
- `rows_extracted == rows_valid + rows_rejected`
- `rows_valid == rows_inserted + rows_duplicate`
## Correr tests
 
```bash
uv run pytest tests/ -v
```
 
14 tests: 3 de extract, 8 de transform, 2 de load (incluye idempotencia), 1 end-to-end.
 
## Arquitectura del pipeline
 
```
data_source.py          extract.py          transform.py          load.py
 (genera datos)  →  (normaliza formatos) → (valida negocio) → (inserta en SQLite)
                                                  │
                                                  ↓
                                           quarantine/*.jsonl
                                           (filas rechazadas)
```
 
Cada archivo tiene una sola responsabilidad. El orquestador (`pipeline.py`) los encadena
y genera el reporte de ejecución.
