# Ejercicio 3 — La Capa Transaccional

Dataset: 1,000,000 transacciones  
Base de datos: SQLite · Comparación: DuckDB sobre Parquet

---

## Ingesta

| Modo | Tiempo (s) | Tamaño de la base (MB) |
|------|-----------|----------------------|
| Sin WAL | 95.16 | 213.2 |
| Con WAL | 109.21 | 213.2 |

Ambas ingestas se completan por debajo del límite de 3 minutos (180s). Los índices se crean después de insertar todos los datos para evitar el overhead de actualizar el B-tree en cada INSERT.

El modo sin WAL resultó más rápido que WAL en este caso. Investigando, encontré que WAL está optimizado para escenarios donde hay lecturas y escrituras simultáneas, por lo que su ventaja es permitir que una conexión lea mientras otra escribe. En este benchmark la ingesta es la única operación y no hay lectores concurrentes, así que considero que el overhead de mantener el archivo WAL separado y luego fusionarlo no se amortiza. Pero en un sistema de producción con usuarios consultando mientras se insertan datos, en teoría WAL sería la elección correcta.

---

## Benchmark de patrones — SQLite con índices

| Patrón | Descripción | Tiempo (ms) | SLA | Cumple | EXPLAIN QUERY PLAN |
|--------|-------------|------------|-----|--------|--------------------|
| P1 | Buscar por transaction_id | 0.036 | < 10ms | ✓ | SEARCH USING INDEX sqlite_autoindex_transactions_1 (transaction_id=?) |
| P2 | Últimas 20 de un user_id | 0.079 | < 50ms | ✓ | SEARCH USING INDEX idx_user_timestamp (user_id=?) |
| P3 | Transacciones de un user_id en rango de fechas | 0.025 | < 50ms | ✓ | SEARCH USING INDEX idx_user_timestamp (user_id=? AND timestamp>? AND timestamp<?) |
| P4 | Suma de amount de un user_id en el último mes | 0.013 | < 50ms | ✓ | SEARCH USING INDEX idx_user_timestamp (user_id=? AND timestamp>?) |
| P5 | Usuarios de un país con más de N transacciones | 9.173 | < 200ms | ✓ | SEARCH USING COVERING INDEX idx_country_user (country_code=?) |

Todos los patrones cumplen sus SLAs con margen amplio. P1-P4 responden en menos de 1ms. P5 tarda 9ms, más que los 4 anteriores, pero aún así está muy por debajo de los 200ms permitidos.

### Interpretación de los planes de ejecución

**P1** usa `sqlite_autoindex_transactions_1`, el índice automático que SQLite crea sobre el PRIMARY KEY. Navega el B-tree directamente al transaction_id solicitado en O(log n) — unas 20 comparaciones para 1M de filas.

**P2, P3, P4** usan `idx_user_timestamp`. El plan muestra que SQLite aprovecha el índice compuesto `(user_id, timestamp)` de forma distinta según la query, ya que para P2 filtra por user_id y recorre las últimas entradas; para P3 y P4 añade la condición de timestamp como range scan directamente en el índice, lo que se refleja en el `AND timestamp>? AND timestamp<?` del plan.

**P5** muestra `COVERING INDEX`, lo que significa que SQLite resuelve la query **sin tocar la tabla principal**, ya que todo lo que necesita (country_code y user_id para contar) está dentro del índice. Esto es especialmente eficiente porque evita el acceso aleatorio a disco para leer filas completas.

---

## Benchmark de patrones — SQLite sin índices

| Patrón | Con índices (ms) | Sin índices (ms) | Factor | EXPLAIN sin índices |
|--------|-----------------|-----------------|--------|---------------------|
| P1 | 0.036 | 0.072 | 2x | SEARCH USING INDEX sqlite_autoindex_transactions_1 (PK se mantiene) |
| P2 | 0.079 | 87.094 | 1,102x | SCAN transactions + USE TEMP B-TREE FOR ORDER BY |
| P3 | 0.025 | 81.203 | 3,248x | SCAN transactions |
| P4 | 0.013 | 82.531 | 6,349x | SCAN transactions |
| P5 | 9.173 | 121.065 | 13x | SCAN transactions + USE TEMP B-TREE FOR GROUP BY |

### Por qué el impacto es tan dramático

Sin el índice `idx_user_timestamp`, los patrones P2-P4 pasan de `SEARCH` a `SCAN`, lo que provoca que SQLite recorra las 1,000,000 de filas completas para encontrar las del usuario solicitado.

P1 apenas cambia (0.036ms → 0.072ms), considero que es porque el PRIMARY KEY no se puede eliminar, lo que provocaría que el índice automático sobre `transaction_id` sigue activo.

P2 sin índices muestra un paso adicional: `USE TEMP B-TREE FOR ORDER BY`. Esto significaría que, después de encontrar las filas del usuario (escaneando toda la tabla), SQLite tiene que construir un B-tree temporal en memoria para ordenarlas por timestamp antes de devolver las últimas 20. Con el índice compuesto, las filas ya están ordenadas por timestamp dentro de cada user_id, así que el ORDER BY es practicamente regalado.

P5 muestra `USE TEMP B-TREE FOR GROUP BY`, por lo que, sin el índice `idx_country_user`, SQLite escanea toda la tabla y necesita un B-tree temporal para agrupar por user_id y contar. Con el COVERING INDEX, los user_ids ya están agrupados dentro de cada country_code en el propio índice.

---

## Comparación SQLite (con índices) vs DuckDB (Parquet)

| Patrón | SQLite (ms) | DuckDB (ms) | Ganador | Factor |
|--------|------------|------------|---------|--------|
| P1 | **0.036** | 62.28 | SQLite | 1,730x |
| P2 | **0.079** | 23.94 | SQLite | 303x |
| P3 | **0.025** | 17.12 | SQLite | 685x |
| P4 | **0.013** | 8.14 | SQLite | 626x |
| P5 | **9.173** | 14.92 | SQLite | 1.6x |

### Análisis patrón por patrón

**P1 — SQLite gana 1,730x.** DuckDB no tiene índice sobre `transaction_id` en el Parquet, entonces debe escanear el archivo completo (o al menos sus row groups) para encontrar un UUID específico. En el caso de SQLite, navega su B-tree en aproximadamente 20 comparaciones. Esto sería la diferencia fundamental entre OLTP y OLAP para lookups por clave.

**P2 — SQLite gana 303x.** DuckDB escanea todas las filas, filtra por user_id, y luego ordena para tomar las últimas 20. Pero SQLite va directo al rango de ese user_id en el índice compuesto y recorre solo las 20 entradas más recientes sin tocar el resto.

**P3 y P4 — SQLite gana ~650x.** Aquí se sigue el mismo principio que P2: el índice compuesto `(user_id, timestamp)` permite un range scan preciso. A diferencia de DuckDB, que no puede hacer esto porque Parquet no tiene índices, lo que provoca que deba leer y filtrar secuencialmente.

**P5 — SQLite gana 1.6x (la diferencia más pequeña).** P5 es la query más parecida a un patrón analítico, ya que filtra por país y agrupa por usuario sobre una fracción grande de los datos (~67K filas de MX). Aquí DuckDB puede aprovechar su procesamiento columnar y paralelo, lo que reduce la brecha. Esto demuestra que la ventaja de SQLite es más grande mientras más transaccional y menos analytic sea. Aún así SQLite, considero, gana gracias al COVERING INDEX, aunque la ventaja sea modesta. Aquí me surge la duda de si, en un dataset más grande o con más países, DuckDB podría igualar o superar a SQLite en este patrón.

### ¿Cuándo usar cada uno?

**SQLite** es la elección correcta cuando el patrón de acceso es transaccional: consultas por usuario individual, lookups por ID o rangos de fechas acotados.

**DuckDB** sigue siendo superior para analytics: agregaciones sobre millones de filas, GROUP BY con muchas categorías o window functions. Esto ya quedó demostyrado en el ejercicio 2, con las 8 queries analíticas. En el caso de P5, parece demostrar un punto de cruce, ya que cuando la query empieza a parecerse más a analytics que a transaccional, la ventaja de SQLite se reduce.

Ahora, si hablamos de un sistema de producción real, considero que la arquitectura correcta sería usar **ambos**: DuckDB (o un equivalente columnar) para el pipeline analítico, y SQLite (o PostgreSQL) para la capa transaccional que sirve a la API. Y, por lo que ví en el documento de los ejercicios, es exactamente lo que debemos construir en el Ejercicio 4.
