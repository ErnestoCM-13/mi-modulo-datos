# Diseño del Schema — Justificación de decisiones

## Tabla `transactions`

### Tipos de dato

**`transaction_id TEXT PRIMARY KEY`**
UUID4 es un string de 36 caracteres. Como SQLite no tiene un tipo UUID nativo, considero que TEXT sería la opción correcta. Al declararlo como PRIMARY KEY, SQLite crea automáticamente un índice B-tree único sobre esta columna. Esto haría que P1 (buscar por transaction_id exacto) sea O(log n) sin necesidad de un índice adicional.

**`timestamp TEXT`**
SQLite no tiene un tipo DATETIME nativo. Entonces almacena las fechas como TEXT en formato ISO 8601 (ej: `2025-07-15 14:30:00`). La ventaja de este formato es que las comparaciones tipo `>=` y `BETWEEN` producen el mismo resultado que las comparaciones cronológicas, ej: "2025-08" viene después de "2025-07" tanto en orden alfabético como en orden temporal. Esto permitiría que los índices sobre timestamp funcionen correctamente sin funciones de conversión.

**`user_id INTEGER` y `merchant_id INTEGER`**
Son enteros nativos. SQLite los almacena con longitud variable (1-8 bytes según el valor), pienso que esto sería más eficiente que TEXT para comparaciones numéricas y como claves de agrupación.

**`amount REAL`**
Punto flotante de 8 bytes (double IEEE 754). Considerío que sería suficiente para los montos monetarios en este ejercicio. Aunque tengo entendido que en un sistema real de producción se usaría un tipo decimal o se almacenaría como entero en centavos para evitar errores de redondeo.

**`category TEXT`, `country_code TEXT`, `status TEXT`**
Son strings de baja cardinalidad (10, 15 y 3 valores distintos respectivamente). SQLite no tiene un tipo ENUM, por lo que considero que TEXT sería lo correcto. Su cardinalidad baja hace que no valga la pena crear índices individuales sobre ellas, ya que un índice sobre una columna con solo 3 valores distintos (status) no ayudaría a reducir el espacio de búsqueda significativamente.

---

## Índices

### `PRIMARY KEY` en `transaction_id` (automático)

**Sirve para:** P1 — buscar una transacción por ID exacto.

Tengo entendido que SQLite implementa el PRIMARY KEY como un índice B-tree único. Por lo que para 1M de registros, una búsqueda por clave exacta requeriría un aproximado de 20 comparaciones. Esto garantizaría el SLA de < 10ms de P1, en teoría, sin esfuerzo adicional.

### `idx_user_timestamp` en `(user_id, timestamp)`

**Sirve para:** P2, P3 y P4, es decir, todas las queries que filtran por `user_id` y luego ordenan o filtran por `timestamp`.

Este es un índice compuesto. Por lo que el orden de las columnas es muy importante: `user_id` va primero porque las tres queries siempre filtran por un `user_id` en específico. Dentro de cada `user_id`, los registros están ordenados por `timestamp`, lo que permitiría:

- **P2** — encontrar las últimas 20 transacciones de un usuario sin ordenar, ya que el índice ya las tiene en orden cronológico, SQLite solo tiene que recorrer las últimas 20 entradas del rango de ese user_id.
- **P3** — filtrar por rango de fechas dentro de un usuario, ya que SQLite navega el B-tree hasta el user_id y luego hace un range scan entre las dos fechas.
- **P4** — sumar montos del último mes de un usuario, el mismo mecanismo que P3 pero acumulando la suma.

### `idx_country_user` en `(country_code, user_id)`

**Sirve para:** P5 — usuarios de un país con más de N transacciones.

`country_code` va primero porque el WHERE filtra por país. Dentro de cada país, los registros están agrupados por `user_id`, lo que permitiría a SQLite contar transacciones por usuario recorriendo el índice secuencialmente sin tocar la tabla principal. Esto vendría siendo más eficiente porque el índice contiene todo lo que la query necesita para el GROUP BY y el HAVING, por lo que solo necesita acceder a la tabla para devolver los resultados finales.

### Índices que no se crearon y por qué

Por último, no se crearon índices sobre `status`, `category`, `merchant_id`, ni `amount` individualmente. Ninguno de los 5 patrones de acceso definidos filtra por esas columnas como condición principal. Ya que, durante este ejercicio me dí cuenta de una cosa: crear índices innecesarios tiene un costo, cada INSERT debe actualizar todos los índices, lo que ralentizaría la ingesta. Con 1M de registros y un SLA de ingesta de < 3 minutos, conisdero que es mejor mantener solo los índices necesarios.
