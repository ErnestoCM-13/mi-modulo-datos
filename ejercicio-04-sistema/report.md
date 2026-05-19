# Ejercicio 4 — El Sistema Completo

API REST con FastAPI · Arquitectura dual DuckDB + SQLite · Cache con TTL  
11 tests · Benchmark de latencia: 100 requests por endpoint

---

## Arquitectura

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
                    /analytics   /users
                                 /transactions/batch
```

La API usa dos backends especializados. DuckDB lee directamente del Parquet para queries analíticas que agregan sobre millones de filas. SQLite para queries transaccionales por usuario individual usando los índices B-tree del Ejercicio 3. Ambas conexiones se inicializan una sola vez en el lifespan de FastAPI y se reutilizan durante toda la vida del servidor.

---

## Backend por endpoint
 
| Endpoint | Backend | Cache | Justificación |
|----------|---------|-------|---------------|
| GET /analytics/summary | DuckDB | TTL 60s | Operaciones globales sobre 1M de filas (COUNT, SUM, AVG) con desglose por país y categoría. DuckDB procesa esto en paralelo leyendo solo las columnas necesarias del archivo Parquet. |
| GET /analytics/top-merchants | DuckDB | TTL 60s | Agrupación (`GROUP BY`) sobre 10,000 merchants con ordenamiento. Misma lógica que el endpoint de summary. La key del caché incluye los parámetros `limit` y `country` para guardar combinaciones distintas por separado.|
| GET /users/{user_id}/transactions | SQLite | No | Sigue el patrón del Ejercicio 3: búsqueda por user_id ordenando por timestamp. El índice compuesto `(user_id, timestamp)` resuelve esta consulta en menos de 1ms, por lo que no requiere caché.|
| GET /users/{user_id}/stats | SQLite | No | Realiza tres consultas rápidas sobre el índice del mismo usuario. Responde aproximadamente en unos 2ms sin necesidad de caché. |
| POST /transactions/batch | SQLite | No | Inserciones seguras con validación de estructura (Pydantic) y eliminación de duplicados. SQLite asegura propiedades ACID, es decir, si una fila falla, se cancela todo el paquete de datos de forma automática.|
| GET /health | Memoria | No | Consulta el tiempo de actividad del servidor, el porcentaje de aciertos de la caché (contadores) y el estado de las conexiones, todo sin tocar las bases de datos. |

---

## Benchmark de latencia

100 requests por endpoint. La primera request se hace en cold (sin cache). El resto se hacen en warm (con cache activo para endpoints analíticos).

### Resultados

| Endpoint | Cold (ms) | p50 warm (ms) | p95 warm (ms) | p99 warm (ms) |
|----------|----------|--------------|--------------|--------------|
| GET /analytics/summary | 53.87 | 2.13 | 2.45 | 2.70 |
| GET /analytics/top-merchants | 347.36 | 2.09 | 2.61 | 3.29 |
| GET /analytics/top-merchants?limit=5&country=MX | 20.62 | 2.05 | 2.35 | 2.62 |
| GET /users/1/transactions | 3.82 | 2.52 | 3.11 | 3.46 |
| GET /users/1/stats | 3.38 | 2.16 | 2.68 | 2.90 |
| GET /health | 2.32 | 2.06 | 2.57 | 2.77 |

### Cumplimiento de SLAs

| Endpoint | SLA | Cold | Warm p50 | Cumple |
|----------|-----|------|----------|--------|
| GET /analytics/summary | < 500ms cold / < 20ms warm | 53.87ms | 2.13ms | ✓ |
| GET /analytics/top-merchants | < 500ms cold / < 20ms warm | 347.36ms | 2.09ms | ✓ |
| GET /users/1/transactions | < 80ms | 3.82ms | 2.52ms | ✓ |
| GET /users/1/stats | < 80ms | 3.38ms | 2.16ms | ✓ |
| GET /health | < 50ms | 2.32ms | 2.06ms | ✓ |

Todos los SLAs se cumplen.

---

## Impacto del cache

### Analytics: 67x de mejora

Los endpoints analíticos promedian **140.6ms en la primera consulta** y **2.1ms en las siguientes (p50)**, una mejora de 67 veces. La primera consulta ejecuta todo el proceso sobre DuckDB (escanear el Parquet, agrupar, ordenar). Las siguientes 99 consultas obtienen el resultado directamente del diccionario en memoria, ya que el costo es simplemente buscar la clave y comparar el tiempo de expiración.

Tomé la decisión de dejar el tiempo de vida (TTL) en 60 segundos aún sabiendo el costo de que, en un sistema real, las transacciones nuevas del `POST /transactions/batch` tardarían hasta 60 segundos en reflejarse en los totales analíticos. Pero considero que para un panel de control donde tener los datos al segundo no es crítico, esto es aceptable. Si el negocio requiriera de datos más actualizados, este tiempo podría reducirse, o incluso se podría activar una limpieza de memoria automática al recibir un paquete de datos nuevo.

### Transaccional: no necesita cache

Los endpoints de usuario promedian **2.3ms en p50**, muy por debajo del SLA de 80ms. No hay diferencia meaningful entre la primera y las siguientes requests porque SQLite con índices B-tree tiene latencia consistente: la búsqueda es O(log n) sin importar si es la primera o la centésima vez. Agregar cache aquí añadiría complejidad sin beneficio medible, y crearía problemas de consistencia cuando el batch insert modifica datos de un usuario.

Los endpoints de usuario promedian **2.3ms en p50**, muy por debajo del límite SLA de 80ms. No hay una diferencia relevante entre la primera consulta y las siguientes porque SQLite con índices B-tree tiene un tiempo de respuesta muy estable, ya que la busqueda es 0 sin importar si es la primera o la centésima vez. Considero que agregar caché aquí añadiría complejidad sin ningún beneficio real, y también crearía problemas para mantener los datos sincronizados cuando se actualice la información de un usuario.

### Top-merchants: el caso interesante

El endpoint `GET /analytics/top-merchants` sin filtro de país tarda 347ms al arrancar en cold, por lo que es el más lento de todos. En mi opinión esto tiene sentido, ya que es un **GROUP BY** sobre 10,000 comercios distintos que debe ordenar por volumen total. Con filtro de país (`?country=MX`), ese tiempo baja a 20ms porque DuckDB filtra primero y agrupa un grupo de datos mucho menor.

Ahora, para bajar esos 347ms iniciales, tuve que aplicar una precarga de DuckDB al iniciar la aplicación (`lifespan`), lo que agregué fue una consulta `SELECT COUNT(*) FROM transactions` al arrancar el servidor. Esto obliga a DuckDB a leer el archivo Parquet a memoria una sola vez. Antes, sin esta precarga, la primera consulta tardaba aproximadamente unos 950ms porque incluía la lectura completa del archivo desde cero.

---

## Validación del batch

Para el endpoint `POST /transactions/batch` implementé tres capas de protección:

**Validación de schema (Pydantic):** si un campo falta o tiene un tipo incorrecto, FastAPI devuelve un error HTTP 422 con el detalle automáticamente. Esto ocurre antes de que el código del endpoint empiece a correr.

**Límite de tamaño:** máximo 500 transacciones por batch. Pasar de ese número hace que el INSERT se vuelva lento y la conexión del cliente podría caerse por tiempo de espera (timeout).

**Deduplicación en dos pasos:** el primer paso dentro del batch (por si el cliente envía el mismo `transaction_id` dos veces), y el segundo contra la base de datos (por si ya existe). Esto epara evitar errores de **UNIQUE constraint** sin necesidad de `INSERT OR IGNORE`, lo cual taparía otros posibles errores de integridad.

---

## Suite de tests

Agregué 11 tests con pytest, todos pasando.

| Test | Qué valida |
|------|-----------|
| test_health_returns_200 | Estructura completa del /health: status, uptime, hit rate, conexiones |
| test_analytics_summary_structure | Campos esperados: total_count, total_amount, by_country, by_category |
| test_top_merchants_default | Devuelve lista de 10 merchants (limit default) |
| test_top_merchants_with_country | Filtro por país respeta el limit |
| test_user_transactions_happy_path | Devuelve transacciones con estructura correcta |
| test_user_not_found_404 | Usuario inexistente → HTTP 404 |
| test_pagination_out_of_range | Página 9999 → lista vacía (no error) |
| test_user_stats_happy_path | Estructura: total_amount, transaction_count, top_category, country_code |
| test_batch_valid | Inserta 1 transacción, recibe confirmación con conteos correctos |
| test_batch_invalid_schema_422 | Schema incompleto → HTTP 422 con detalle |
| test_analytics_summary_sla | Segunda llamada (warm) responde en < 20ms |

---

## Conexión con los ejercicios anteriores

Por último, quiero mencionar que este ejercicio integra todo lo construido en el módulo de ejercicios:

**Del Ejercicio 1** usa el archivo Parquet como la fuente de datos para DuckDB. La elección de este formato (Parquet Snappy) quedó justificada con los benchmarks del ejercicio 1, donde se demostró que es 12 veces más rápido que CSV al leer todo el archivo.

**Del Ejercicio 2** aplica el aprendizaje de que DuckDB es muy superior para queries analíticas (esto gracias al procesamiento por columnas en paralelo y a que solo lee los datos que necesita), mientras que para búsquedas de registros individuales es lento porque no maneja índices.

**Del Ejercicio 3** usa la base SQLite con los índices `idx_user_timestamp` e `idx_country_user`. Esto es lo que permite que las consultas de transacciones respondan en menos de 3 milisegundos. Sin estos índices, esas mismas búsquedas tardarían más de 80 ms (tal como se comprobó en el benchmark de E3).

En conclusión, gracias a esto, me doy cuenta que esta arquitectura doble (DuckDB + SQLite) no se eligió al azar, ya que cada decisión sobre qué base de datos usar está respaldada por los datos reales y las mediciones que obtuvimos en los tres ejercicios anteriores.

## Registro de Tiempos y Desarrollo

A continuación, detallo los tiempos aproximados que invertí en el primer ejercicio:

| Fase | Tiempo empleado |
|------|-----------------|
| Investigación previa | 3 h |
| Escritura de código | 4 h |
| Interpretación y reporte | 3 h |
| **Total acumulado** | **10 h** |

En este último tuve la ventaja de que ya hemos visto y/o trabajado con endpoint, peticiones HTTP y tests unitarios. Entonces la mayor cantidad de tiempo la invertí en imvestigar sobre FastAPI (principalmente cómo maneja la inyección de deperndencias y el ciclo de vida) y cómo integrar dos motores de base de datos en una misma app. También, aunque ya hemos trabajado con tests unitarios, me sigo tardando un poco en planearlos para cubrir los puntos importantes para que agreguen valor real.
