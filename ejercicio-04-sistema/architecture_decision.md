# Decisiones de Arquitectura
 
## Diagrama del sistema
 
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
```
 
## Backend por endpoint
 
### `GET /analytics/summary` → DuckDB
 
Esta query agrega sobre el 100% de las transacciones: conteo total, suma total, promedio, y breakdown por 15 países y 10 categorías. Es un workload totalmente analítico (OLAP).
 
En este caso DuckDB sería la elección correcta, porque procesa datos columnar directamente desde el Parquet, paraleliza las agregaciones internamente, y solo lee las columnas que necesita. En el Ejercicio 2 se demostró que DuckDB es significativamente más rápido que pandas para este tipo de operaciones.
 
El cache con TTL de 60s garantiza que el cold de 200-400ms se convierta en < 20ms después de la primera llamada. Un resumen global no cambia con cada transacción nueva, así que considero que un TTL de 60s es una compensación razonable entre frescura y rendimiento.
 
### `GET /analytics/top-merchants` → DuckDB
 
Query analítica con GROUP BY sobre `merchant_id` (10,000 valores distintos), ordenamiento por volumen, y filtro opcional por país. Aquí mi justificación es la misma que con el summary: DuckDB con projection pushdown sobre Parquet + cache.
 
Incluí en la cache key los parámetros `limit` y `country` para que combinaciones distintas de filtros tengan sus propias entradas en cache.
 
### `GET /users/{user_id}/transactions` → SQLite
 
El patrón de la consulta transaccional es buscar las transacciones de un usuario específico, ordenadas por fecha y con paginación. Esto es exactamente el patrón P2 del Ejercicio 3, donde SQLite con el índice compuesto `(user_id, timestamp)` respondió en 0.079ms — 303x más rápido que DuckDB sobre Parquet.
 
Si usara DuckDB aquí, tendría que escanear todo el Parquet para encontrar las filas de un usuario. Por el contrario, SQLite navega directamente al rango del B-tree correspondiente. Decidí no usar cache porque los datos de un usuario pueden cambiar con cada batch insert y la latencia ya cumple el SLA sin él.
 
### `GET /users/{user_id}/stats` → SQLite
 
Caso similar al anterior: consulta por un `user_id` específico con tres queries al índice. La categoría más frecuente y el país se obtienen con GROUP BY sobre el subconjunto de filas de ese usuario (típicamente 20 filas), lo cual no requiere esfuerzo gracias al índice.
 
### `POST /transactions/batch` → SQLite
 
Para las inserciones usé SQLite por la base transaccional. SQLite soporta transacciones ACID, es decir, si alguna fila falla, se puede hacer rollback del batch completo sin dejar la base en un estado inconsistente.
 
Al contrario, DuckDB no es apropiado para inserciones frecuentes en caliente, ya que está diseñado para lecturas analíticas sobre datos ya escritos.
 
La deduplicación se hace en dos pasos: primero dentro del batch (por si el cliente envía duplicados), luego contra la base (por si el `transaction_id` ya existe). La idea es evitar errores de UNIQUE constraint sin sacrificar rendimiento.
 
### `GET /health` → Ninguno (estado en memoria)
 
Aquí no se consulta bases de datos. Solo se lee el timestamp de arranque (para uptime), el hit rate del cache (un contador en memoria), y se verifica que las conexiones existen. Durante las pruebas dió una respuesta constante < 1ms.
