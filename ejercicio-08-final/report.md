# Ejercicio 8 — Reporte

## Sistema de Monitoreo de Transacciones

Sistema completo que junta los componentes del ejercicio 1 al 7: una API REST con 7 endpoints, un pipeline para ingestar archivos CSV, detección de anomalías, y todo empaquetado con Docker.

---

## Endpoints implementados

| Endpoint | Backend | Función |
|----------|---------|---------|
| GET /health | Memoria + SQLite | Estado del sistema, uptime, cache hit rate, total de transacciones |
| GET /analytics/summary | DuckDB + cache | Totales globales y desglose por país y categoria|
| GET /analytics/top-merchants | DuckDB + cache | Top N merchants, con posibilidad de filtrar por país |
| GET /users/{id}/transactions | SQLite | Historial con filtros de fecha y paginación |
| GET /users/{id}/stats | SQLite | Monto total, conteo, categoría y país del usuario |
| GET /anomalies/failed-transactions | SQLite | Usuarios con más de N fallas en los últimos M días |
| POST /ingest/csv | Pipeline → SQLite | Sube CSV, valida, carga y devuelve reporte |

---

## Detección de anomalías

El endpoint `/anomalies/failed-transactions?threshold=3&days=30` básicamente lanza una consulta SQLite con GROUP BY y HAVING, contando las transacciones que tengan `status = 'failed'` dentro de una ventana de tiempo que se puede cambiar con parámetros.

La query usa la función `datetime('now', '-30 days')` de SQLite para calcular la fecha de corte dinámicamente. El índice `(user_id, timestamp)` del ejercicio 3 permite filtrar por fecha eficientemente. El resultado se ordena por `failed_count` de mayor a menor, así los usuarios con más problemas aparecen primero.

Quiero resaltar que cuando lo probé con el dataset de 1M de transacciones y `threshold=3, days=30`, el endpoint no me devolvió ningún usuario. Creo que esto tiene sentido, porque con solo aproximadamente 100K fallas distribuidas uniformemente entre 50,000 usuarios, la probabilidad de que un usuario tenga más de 3 fallas en exactamente 30 días es baja. Con un `threshold=1` o un `days=365` seguramente saldrían resultados distintos.

---

## Pipeline de ingesta CSV

El endpoint `POST /ingest/csv` acepta un archivo CSV que se sube por HTTP y ejecuta el pipeline del ejercicio 6 en tres fases:

1. **Extract:** lee el CSV con `csv.DictReader`, convierte los datos numéricos (`user_id`, `merchant_id`, `amount`) de string a sus tipos correctos, y normaliza formatos
2. **Transform:** valida las 5 reglas de negocio (UUID4, rango de amount, categoría válida, país válido, timestamp no futuro) y envía los rechazos a cuarentena con su respectivo motivo
3. **Load:** inserta las filas válidas con `INSERT OR IGNORE` usando la conexión SQLite que ya tiene la app

El reporte de respuesta incluye los conteos detallados:
```json
{
  "filename": "test.csv",
  "rows_extracted": 1,
  "rows_valid": 1,
  "rows_rejected": 0,
  "rejected_by_type": {},
  "rows_inserted": 1,
  "rows_duplicate": 0
}
```

A diferencia del pipeline del E06, aquí `load.py` recibe la misma conexión SQLite que ya está usando la app, en vez de abrir una nueva. Así evitamos posibles conflictos de bloqueo y garantizamos de que el modo WAL y `row_factory` ya esten configurados.

Después de cada ingesta exitosa, el cache analítico se invalida con `cache.invalidate_prefix('analytics:')` para que las próximas consultas ya reflejen los datos nuevos.

---

## Infraestructura Docker

Todo el sistema se levanta con un solo comando:

```bash
docker compose up --build
```

Son dos servicios: `setup` crea la base SQLite desde el Parquet (es idempotente, si ya tiene datos, no los vuelve a cargar), y `api` arranca después de que setup termina sin errores.

La imagen usa una build multi-stage con `python:3.11-slim`. Los datos se montan como volúmenes y no se copian dentro de la imagen. Agregué `PYTHONPATH=/app` en el Dockerfile para que los imports del módulo `pipeline/` funcionen sin problema.

El healthcheck cada 30 segundos verifica que `/health` responda.

---

## Suite de tests

14 tests, todos pasando en 2.46s:

| Grupo | Tests | Qué cubren |
|-------|-------|-----------|
| Health | 1 | Estructura completa: status, uptime, cache, connections, transaction_count |
| Analytics | 3 | Summary con estructura, top-merchants default (10), top-merchants con filtro de país |
| Users | 4 | Transacciones happy path, filtros de fecha, 404 para usuario inexistente, stats |
| Anomalías | 2 | Threshold default, threshold y días custom |
| CSV Ingestion | 3 | CSV válido (insertado), CSV con errores (rechazados), archivo no-CSV (422) |
| SLA | 1 | Analytics summary en warm < 20ms |

---

## Integración de los ejercicios anteriores

| Componente | Origen | Cómo se usa en E08 |
|-----------|--------|-------------------|
| Parquet de 1M registros | E01 | Fuente de datos para DuckDB (analytics) y setup inicial |
| DuckDB para analytics | E02 | Endpoints /analytics/* con projection pushdown |
| Índices SQLite | E03 | `idx_user_timestamp` para queries por usuario, `idx_country_user` para anomalías |
| API FastAPI + cache | E04 | Estructura base de los 7 endpoints con TTL de 60s |
| Pipeline ETL | E06 | Endpoint /ingest/csv reutiliza extract → transform → load |
| Docker multi-stage | E07 | Dockerfile, docker-compose, healthcheck, JSON logging |

Cada decisión de backend está respaldada por mediciones de los ejercicios anteriores. DuckDB para analytics porque en el ejercicio 2 se demostró que con projection pushdown solo leía el 7.4% del archivo. SQLite para la parte transaccional porque en el ejercicio 3 respondió en 0.079ms con índices, aproximadamente 303 veces más rápido que DuckDB para el mismo patrón.

---

## Registro de Tiempos y Desarrollo

A continuación, detallo los tiempos aproximados que invertí en el octavo ejercicio:

| Fase | Tiempo empleado |
|------|-----------------|
| Investigación previa | 1 h |
| Escritura de código | 7 h |
| Interpretación y reporte | 3 h |
| **Total acumulado** | **11 h** |
