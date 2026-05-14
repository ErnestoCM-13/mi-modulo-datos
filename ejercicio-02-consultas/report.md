# Ejercicio 2 — El Motor de Consultas

Dataset: `transactions_1m_none.parquet` (1,000,000 registros)  
Repeticiones por medición: 3 · Métrica de tiempo: promedio

---

## Tabla comparativa — Tiempo de ejecución (segundos)

| Query | pandas | DuckDB | Polars | Ganador |
|-------|--------|--------|--------|---------|
| Q1 — Conteo por país | 0.0302 | 0.0109 | **0.0061** | Polars |
| Q2 — Stats de monto por categoría | 0.0330 | 0.0245 | **0.0074** | Polars |
| Q3 — Top 10 usuarios por gasto | 0.0373 | 0.0908 | **0.0179** | Polars |
| Q4 — Transacciones fallidas por hora | 0.0745 | 0.0116 | **0.0067** | Polars |
| Q5 — Filtro compuesto + últimos 30 días | 0.0665 | 0.0594 | **0.0093** | Polars |
| Q6 — Categoría dominante por país | 0.0847 | 0.0377 | **0.0123** | Polars |
| Q7 — Usuarios con más de 5 fallas | 0.0500 | 0.0146 | **0.0106** | Polars |
| Q8 — Promedio diario por categoría | 0.7014 | 0.0446 | **0.0397** | Polars |

## Tabla comparativa — Pico de memoria RAM (MB)

| Query | pandas | DuckDB | Polars |
|-------|--------|--------|--------|
| Q1 | 16.22 | 0.07 | 0.02 |
| Q2 | 15.27 | 0.14 | 0.00 |
| Q3 | 40.89 | 0.11 | 0.00 |
| Q4 | 6.85 | 0.07 | 0.00 |
| Q5 | 38.16 | 3.22 | 0.01 |
| Q6 | 71.37 | 0.14 | 0.00 |
| Q7 | 7.58 | 0.07 | 0.00 |
| Q8 | 140.15 | 0.42 | 0.00 |

> Nota sobre los valores de RAM en DuckDB y Polars:

> Los números de memoria en esta tabla miden lo que tracemalloc puede ver, por lo que, en base a lo que investigué, tracemalloc solo monitorea el heap de Python, es decir, el espacio donde Python crea sus propios objetos (listas, DataFrames, strings, etc.).
Ví que Pandas construye todas sus estructuras directamente en ese espacio, eso explicaría por qué sus números son tan altos y reales. Por ejemplo, 140 MB en Q8, donde se refleja las columnas temporales, copias intermedias y el DataFrame resultado que pandas crea durante la ejecución.
También ví que DuckDB funciona diferente: cuando le mandas un SELECT, ejecuta toda la query internamente en C++ y solo regresa el resultado final a Python. Tracemalloc no ve nada de lo que ocurrió adentro, solo ve el DataFrame pequeño del resultado. Esto explicaría por qué Q1 muestra 0.07 MB, ya que es literalmente el costo de crear una tabla de 15 filas en Python, mas no el costo de procesar 1 millon de registros.
Por último, investigando de Polars, ví que está escrito en Rust y gestiona su propia memoria fuera del heap de Python. En este caso tracemalloc no tiene acceso a ella, así que registra 0.00 MB aunque Polars sí tenga datos en RAM.
Gracias a esta investigación y la tabla de resultados, puedo deducir que esto no significa que DuckDB y Polars no usen memoria, más bien significa que tracemalloc no sería la herramienta correcta para medirla. Aunque actualmente desconosco cuál sería la correcta.

---

## EXPLICACIÓN DE ANALYZE — Q3, Q5, Q6

### Q3 — Top 10 usuarios por suma de amount

```
TABLE_SCAN (READ_PARQUET)       → 1,000,000 filas | 0.01s
  Projections: user_id, amount
      ↓
PROJECTION (compress integers)  → 1,000,000 filas | 0.00s
      ↓
HASH_GROUP_BY                   → 50,000 filas    | 0.10s  ← cuello de botella
  Groups: user_id
  Aggregates: SUM(amount), COUNT(*)
      ↓
PROJECTION (decompress)         → 50,000 filas    | 0.00s
      ↓
TOP_N                           → 10 filas        | 0.00s
  Order: total_amount DESC, Limit: 10
```

**Qué está haciendo DuckDB:**

Lo primero es un `TABLE_SCAN` con **projection pushdown**: en lugar de leer las 8 columnas del Parquet, DuckDB identifica que solo necesita `user_id` y `amount`, y lee únicamente esas dos del archivo. El resto ni se toca en disco.

Los pasos de `compress/decompress integers` son DuckDB aplicando su propio esquema de compresión interna (dictionary encoding) durante el procesamiento en memoria. Tengo entendido que no tienen costo de tiempo medible.

Por lo que veo, el `HASH_GROUP_BY` aquí actua como un cuello de botella, ya que para agrupar por `user_id` con 50,000 usuarios distintos, DuckDB construye una tabla hash de 50,000 entradas y acumula sumas y conteos en cada bucket. Esto provoca que este paso tarde **0.10s** lo que es prácticamente todo el tiempo de la query.

Finalmente, `TOP_N` parece ser más eficiente, ya que, en lugar de ordenar los 50,000 resultados completos, mantiene un heap de solo 10 elementos y descarta el resto mientras los recibe.

Aquí me surge una duda. Por qué DuckDB es más lento que pandas y Polars en Q3? Tengo entendido que en este benchmark los datos ya estrían en RAM. Entonces el `HASH_GROUP_BY` de DuckDB sobre 50,000 grupos tiene más overhead de inicialización que las implementaciones de pandas y Polars, los cuales operan directamente sobre arrays NumPy o Arrow ya en memoria. DuckDB está optimizado para cuando los datos viven en disco, esto causaría que, cuando ya están cargados, su ventaja desaparece y su overhead de pipeline se volvería visible.

---

### Q5 — Transacciones amount > 500 en MX/CO, últimos 30 días

```
COLUMN_DATA_SCAN (max_ts CTE)        → 1 fila       | 0.00s
      ↓
TABLE_SCAN (READ_PARQUET)            → 73,603 filas  | 0.03s  ← de 1M a 73K
  Projections: todas las columnas
  Filters:        amount > 500
                  country_code IN ('MX', 'CO')
  Dynamic Filter: timestamp >= '2026-04-13 19:02:27' (calculado del CTE)
      ↓
PROJECTION (compress)                → 9,973 filas   | 0.00s
      ↓
NESTED_LOOP_JOIN (con max_ts, 1 fila) → 9,973 filas  | 0.00s
  Condition: timestamp >= max_date - INTERVAL '30 days'
      ↓
FILTER (country_code = 'MX' OR 'CO') → 9,973 filas  | 0.00s
      ↓
ORDER_BY transaction_id ASC          → 9,973 filas   | 0.00s
```

**Qué está haciendo DuckDB:**

Podemos observar que esta query muestra dos optimizaciones avanzadas del query planner.

La primera es **predicate pushdown**: DuckDB empuja los filtros `amount > 500` y `country_code IN ('MX', 'CO')` directamente al `TABLE_SCAN`. Esas condiciones se evalúan mientras lee el Parquet, antes de que los datos entren al pipeline. De 1,000,000 de filas, solo 73,603 pasan el filtro y se procesan después.

La segunda es el **Dynamic Filter**: DuckDB ejecuta primero el CTE `max_ts` para obtener la fecha máxima del dataset (1 sola fila), e inyecta ese valor concreto como filtro adicional en el `TABLE_SCAN`. Gracias a esto, en lugar de leer 1M filas y filtrar por fecha después, DuckDB ya conoce la fecha de corte antes de leer el archivo y la aplica durante la lectura. Investigando un poco, encontré que esto se llama "filter pushdown across CTEs".

El `NESTED_LOOP_JOIN` con el CTE de 1 fila podría ser esencialmente un filtro simple disfrazado de join. Aunque, honestamente, no estoy 100% seguro. Pero de ser así, con un solo elemento en el lado derecho, el costo es mínimo.

El resultado: Esto es simple, DuckDB procesó efectivamente solo el 7.4% del archivo para responder esta query.

---

### Q6 — Categoría dominante por país

```
TABLE_SCAN (READ_PARQUET)            → 1,000,000 filas | 0.01s
  Projections: country_code, category, amount
      ↓
HASH_GROUP_BY (1er nivel)            → 150 filas        | 0.03s
  Groups: country_code, category
  Aggregates: count_star(), avg(amount)
      ↓
PROJECTION (struct_pack)             → 150 filas        | 0.00s
  Empaqueta {category, avg_amount, count} en un struct
      ↓
HASH_GROUP_BY (2do nivel)            → 15 filas         | 0.00s
  Groups: country_code
  Aggregates: arg_max_nulls_last(struct, count)
      ↓
PROJECTION (desempaqueta struct)     → 15 filas         | 0.00s
      ↓
ORDER_BY country_code ASC            → 15 filas         | 0.00s
```

**Qué está haciendo DuckDB:**

Esta query tiene, en mi opinión, la optimización más interesante de las tres, ya que **DuckDB eliminó por completo la window function que se escribió en el SQL**.

El código usaba `ROW_NUMBER() OVER (PARTITION BY country_code ORDER BY count DESC)` para rankear categorías por país. Pero DuckDB detectó que el objetivo era quedarse con `rn = 1` (el máximo por grupo) y reemplazó internamente el `ROW_NUMBER` con `arg_max_nulls_last`, lo que, tengo untendido, es una función de agregación de un solo paso.

Pasando al mecanismo, este empaqueta `{category, avg_amount, count}` en un struct, luego en el segundo `HASH_GROUP_BY` encuentra el struct con el mayor `count` por `country_code` usando `arg_max`. Finalmente desempaqueta el resultado. Si no estoy mal, esto colapsa 1,000,000 filas a 150 combinaciones y estas a su vez a 15 ganadores, todo esto sin construir nunca la tabla de rankings completa.

---

## Recomendación de arquitectura: cuándo usar cada engine

### Pandas
Yo usaría Pandas cuando el dataset cabe cómodamente en RAM, el trabajo es e iterativo (notebooks, análisis ad hoc), o se necesita de integración directa con librerías del ecosistema científico de Python. También cuando el equipo ya conoce la API y el tiempo de desarrollo importa más que el tiempo de ejecución.

### DuckDB
En el caso de DuckDB, lo usaría cuando los datos viven en disco, como en el caso de Parquet o CSV, y no se quiere o puede cargarlos completos en RAM, ya que la Q5 demuestra que DuckDB puede leer solo el 7.4% de un archivo para responder una query. También cuando el dataset es más grande que la RAM disponible.

### Polars
Por último, utilizaría Polars cuando la velocidad es prioridad y los datos caben en RAM. Polars ganó en las 8 queries de este benchmark. Investigando, encontré que su ventaja viene de tres fuentes: ejecución lazy con optimización del plan antes de correr, procesamiento paralelo automático sobre múltiples cores, y operación nativa sobre Apache Arrow.

### Tabla de decisión
Para terminar, preparé una pequeña tabla para poder ver, de manera gráfica, el engine que recomendaría por situación

| Situación | Engine recomendado |
|-----------|-------------------|
| Datos en disco, no caben en RAM | DuckDB |
| Datos en RAM, máxima velocidad | Polars |
| Análisis exploratorio en notebook | Pandas |
| SQL estándar y EXPLAIN ANALYZE | DuckDB |
| Pipeline de producción en Python | Polars |
| Integración con scikit-learn / scipy | Pandas |
