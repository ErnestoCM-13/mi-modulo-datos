# Decisiones Técnicas

## Tecnologías por capa

### API: FastAPI sobre Django REST Framework

Para la API me incliné por FastAPI. En el ejercicio 5 reconstruí los mismos endpoints con Django REST Framework y la funcionalidad quedo practicamente igual, pero en este caso FastAPI me dio algunas ventajas: arranque más rápido (lo que considero relevante para contenedores que se reinician), tiene menos overhead por request (medido en el benchmark del ejercicio 4 con p50 de 2ms en warm), y el Dockerfile quedó más simple sin necesidad de migraciones, collectstatic o un servidor WSGI aparte.

Creo que Django sería la elección correcta si el sistema necesitara un panel de administración para usuarios no técnicos, autenticación robusta con roles y permisos, o o todo el ecosistema de plugins que ya tiene. Para una API de datos sin frontend, me parece que FastAPI es suficiente y más liviana.

### Analytics: DuckDB sobre Parquet

Los endpoints `/analytics/summary` y `/analytics/top-merchants` los dejé con DuckDB leyendo directamente del Parquet. Me apoyé en lo que ví del ejercicio 2: DuckDB con projection pushdown lee solo las columnas necesarias del archivo y en Q5 procesó únicamente el 7.4% del Parquet gracias al predicate pushdown. Para queries analíticas que agregan sobre 1M de filas, DuckDB resultó más rápido que el ORM de Django o las queries SQLite directas.

El cache con TTL de 60 segundos reduce la latencia de unos 140ms (cold) a unos 2ms (warm) aproximadamente, cumpliendo el SLA de < 20ms para requests warm. La invalidación se activa cuando el endpoint de ingesta CSV inserta nuevas filas.

### Transaccional: SQLite con índices B-tree

Para los endpoints `/users/*` y `/anomalies/*` me fuí por SQLite, usando los mismos índices del ejercicio 3: `(user_id, timestamp)` para queries por usuario y `(country_code, user_id)` para queries por país. La evidencia es bastante directa: en el ejercicio 3, SQLite con índices respondió en 0.079ms para el patrón P2 (últimas 20 transacciones de un usuario), unas 303 veces más rápido que DuckDB sobre Parquet para el mismo patrón.

El endpoint de detección de anomalías también opera sobre SQLite porque, en el fondo, es un GROUP BY filtrado por un rango de fechas de un usuario específico; un patrón transaccional que el índice `(user_id, timestamp)` resuelve bastante bien.

### Pipeline: ETL en capas separadas

El endpoint `/ingest/csv` reutiliza el pipeline del ejercicio 6: extract normaliza formatos, transform valida las reglas de negocio y envía los rechazos a cuarentena, y load inserta con `INSERT OR IGNORE` para mantener la idempotencia. Las capas las implementé como funciones importables, no scripts CLI, así que se pueden llamar directamente desde el endpoint HTTP sin necesidad de lanzar subprocesos.

### Infraestructura: Docker con setup separado

En Docker mantuve la idea del ejercicio 7: un servicio `setup` crea la base SQLite desde el Parquet una sola vez, y el servicio `api` que solo arranca cuando el setup terminó bien. Los datos se montan como volúmenes, no se copian dentro de la imagen. Con esto la imagen se mantiene por debajo de 300MB y se pueden actualizar los datos sin reconstruirla.

---

## Compromisos (trade-offs) y consecuencias

**Cache TTL fijo vs invalidación por evento.** Elegir un TTL de 60 segundos es simple de implementar, pero tiene el costo de que los datos analíticos pueden quedarse hasta un minuto desactualizados después de una ingesta. Intenté mitigarlo un poco invalidando el cache al insertar un batch, pero eso no cubre el caso donde los datos se insertan directamente en SQLite por fuera de la API.

**SQLite single-writer vs PostgreSQL.** SQLite solo permite un writer a la vez. Si llegaran dos requests de ingesta CSV al mismo tiempo, una tendría que esperar a que la otra termine. Con el WAL mode no bloquea a los lectores, pero sí limita el throughput de escritura. Para una fintech real con cientos de inserciones por segundo, probablemente habría que moverse a PostgreSQL con connection pooling.

**DuckDB sobre Parquet estático.** Un detalle importante: los endpoints analíticos consultan el Parquet original de 1M de registros, no los datos nuevos que se insertan por CSV en SQLite. Esto crea una inconsistencia, ya que el resumen no incluye las transacciones que llegan después del setup inicial. Lo ideal sería que DuckDB también leyera de SQLite, o tener algún proceso de reconciliación que se ejecute cada cierto tiempo.

---

## ¿Qué cambiaría con 100M de filas?

**SQLite → PostgreSQL.** Con 100 millones de filas, creo que SQLite se quedaría corto. La base pesaría unos 20GB y la escritura concurrente sería un cuello de botella real. Ahí sí convendría saltar a PostgreSQL, con índices parciales (como crear un índice solo para `status = 'failed'`) y particionamiento por fecha, para que las consultas sigan siendo rápidas y se puedan hacer varias escrituras en paralelo.

**Parquet monolítico → Parquet particionado.** Un solo archivo Parquet de 100 millones de filas pesaría  unos 6GB. DuckDB seguramente lo manejaría, pero escanearlo completo sería lento. Particionar por `country_code` o por mes (`year=2026/month=05/data.parquet`) permitiría a DuckDB leer solo las particiones que necesita. El ejercicio 2 mostró que el predicate pushdown funciona a nivel de row group; con particiones físicas, el beneficio sería todavía mayor.

**Cache → Redis.** El cache actual vive en memoria, así que no sobrevive a un reinicio y no se comparte entre instancias. Con varias réplicas detrás de un load balancer, cada una arrancaría con su caché fría. Redis resolvería eso centralizando el cache y haciendo que persista entre reinicios.

**Setup sincrónico → ingesta incremental.** El setup actual carga todo el dataset al iniciar, y para 1 millon de filas toma unos 30 segundos. Con 100 millones serían aproximadamente unos 30 minutos, lo que considero inaceptable para un deploy. Por lo que considero que la alternativa sería una ingesta incremental: un proceso continuo que vaya leyendo archivos Parquet nuevos desde un bucket S3 y los cargue sin detener el servicio.

---

## Monitoreo en producción

**Latencia por endpoint.** Mediría p50, p95 y p99 de cada endpoint con un middleware que registre los tiempos. Si de repente el p95 de `/users/*/transactions` sube de 3ms a 50ms, podría ser señal de que un índice se corrompió o que la base creció más de lo que el B-tree puede manejar eficientemente.

**Hit rate del cache.** El endpoint `/health` ya reporta el hit rate. Si cayera del 95% al 30%, probablemente el TTL es demasiado corto para el patrón de tráfico, o las claves de caché no están bien diseñadas y no se reutilizan como deberían.

**Tamaño de la cuarentena.** Si de pronto el pipeline empieza a rechazar más del 20% de las filas, es muy probable que algo cambió en la fuente de datos. Una alerta automática cuando `rows_rejected / rows_extracted > 0.2` detectaría el problema antes de que un usuario lo note.

**Espacio en disco.** SQLite va creciendo con cada ingesta. Una alerta al 80% de capacidad del volumen Docker nos daría tiempo para limpiar datos antiguos o escalar el almacenamiento.

**Errores 5xx.** Cualquier respuesta con status 500 indicaría un bug o un recurso no disponible (base caída, Parquet no montado). Aquí hay cero tolerancia, cada 500 generaría una alerta inmediata.
