# Ejercicio 7 — Reporte

## Sistema contenerizado con Docker

API FastAPI del ejercicio 4 empaquetada en Docker, con un setup que se ejecuta automáticamente, healthcheck y logging en JSON. 
Con solo un `docker compose up --build` se levanta todo desde cero.

---

## Imagen Docker

### Multi-stage build

| Stage | Propósito | Contenido |
|-------|-----------|-----------|
| builder | Instalar dependencias | pip + requirements.txt → `/install` |
| runtime | Ejecutar la app | python:3.11-slim + dependencias + código |

El stage de builder instala las dependencias en un directorio aparte (`--prefix=/install`). Despues, el stage runtime arranca desde una imagen limpia y solo copia las dependencias ya compiladas y el código de la app. Todo lo que se usó para compilar (pip, cache, headers) se queda en el builder, asi que no llega a la imagen final.

Decidí usar `--no-cache-dir` en pip para que no guarde los archivos `.whl` descargados; ya que, después de instalar no nos sirven y ocuparían espacio de más.

### Tamaño de la imagen

La imagen base `python:3.11-slim` pesa aprox 120MB. Con las dependencias (FastAPI, uvicorn, DuckDB, PyArrow, Pandas) la imagen final quedó por debajo de los 300MB requeridos.

---

## Servicios en docker-compose

### Setup (corre una sola vez)

El servicio `setup` ejecuta `scripts/setup_db.py` que:

1. Verifica si la base SQLite ya tiene datos; si sí, termina inmediatamente (es decir, es idempotente)
2. Lee el Parquet desde el volumen montado usando `iter_batches` (chunking real, aplicando el feedback que recibí en el tercer ejercicio)
3. Crea la tabla con los índices `idx_user_timestamp` e `idx_country_user`
4. Carga los datos con `INSERT OR IGNORE`
5. Termina con exit code 0

### API (depende de setup)

```yaml
depends_on:
  setup:
    condition: service_completed_successfully
```

La API no arranca hasta que setup termine con código 0. Si setup falla (porque no encuentra el Parquet, hay un error de schema, etc.), la API nunca arranca y Docker muestra el error. Así se evita el problema de que la API esté corriendo pero sin datos.

### Volúmenes

| Volumen | Tipo | Uso |
|---------|------|-----|
| `db-data` | Named volume | Base SQLite compartida entre setup y api. Persiste aunque se reinicie. |
| `../data` | Bind mount (read-only) | Parquet del host montado como `/data/parquet/`. No se modifica. |

Esta separación la hice a propósito: los datos de entrada (el Parquet) están en el host y se montan como solo lectura. Los datos generados (la base SQLite) viven en un volumen Docker que se puede eliminar con `docker compose down -v` para poder empezar de cero.

---

## Variables de entorno

| Variable | Valor | Propósito |
|----------|-------|-----------|
| `SQLITE_PATH` | `/data/db/transactions.db` | Ruta dentro del contenedor a la base SQLite |
| `PARQUET_PATH` | `/data/parquet/transactions_1m_none.parquet` | Ruta dentro del contenedor al Parquet |
| `PARQUET_DIR` | `./../data` | Ruta en el host donde están los Parquet |

Si falta alguna variable necesaria, la aplicación falla de inmediato con un mensaje que dice exactamente qué variable falta y dónde buscar. Por ejemplo:

```
ERROR: la variable de entorno SQLITE_PATH es requerida. Revisa .env.example para los valores esperados.
```

Esto me pareció bastante más útil que un stacktrace de Python perdido tres niveles adentro de una función.

---

## Healthcheck

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
```

Docker ejecuta este comando cada 30 segundos. Si `/health` no responde en 5 segundos, después de 3 fallos consecutivos el contenedor entra en estado `unhealthy`. Con eso, herramientas como Kubernetes o Docker Swarm podrían reiniciarlo automáticamente.

Se usa `urllib` de Python en lugar de `curl` porque la imágen `python:3.11-slim` no trae curl, y siento que no vale la pena instalar paquetes extra solo para el healthcheck.

Verificación:
```
$ docker compose ps
NAME                              STATUS
ejercicio-07-contenedores-api-1   Up 17 seconds (health: starting)
```

Después de 30 segundos cambia a `(healthy)`.

---

## JSON Logging

```json
{"timestamp": "2026-06-11 21:48:40,547", "level": "INFO", "message": "Inicializando conexiones..."}
{"timestamp": "2026-06-11 21:48:40,566", "level": "INFO", "message": "Servidor listo."}
{"timestamp": "2026-06-11 21:48:56,877", "level": "INFO", "message": "analytics/summary computed (cold)"}
```

Cada línea de log es un objeto JSON con tres campos fijos: timestamp, level y message. En producción, supongo que herramientas como Datadog, ELK o CloudWatch pueden leer estos logs en automático para indexar, buscar y disparar alertas. Un log en texto plano requeriría un regex para parsearlo, entonces con JSON evitamos ese paso.

Los logs se mandan a stdout (`StreamHandler(sys.stdout)`), que es donde Docker los espera. Con `docker compose logs -f api` los muestra en tiempo real.

---

## Decisiones de diseño

### ¿Por qué FastAPI (E04) y no Django (E05)?

Para meterlo en Docker, creo que FastAPI tiene ventajas prácticas: un solo archivo `main.py` como punto de entrada, sin migraciones que correr en el setup, sin archivos estáticos que servir. Django requeriría `collectstatic`, `migrate`, y quizás un servidor WSGI como gunicorn, lo que metería más complejidad en el Dockerfile sin que realmente ganáramos algo en este ejercicio.

### ¿Por qué setup como servicio separado?

La alternativa habría sido un script de entrypoint que checara y creara la base antes de lanzar uvicorn. Al separarlo en dos servicios, los logs de setup y los de la API quedan separados (por lo que sería más fácil diagnosticar), y ví que el `depends_on: service_completed_successfully` es una garantía que da Docker; por lo que me pareció mejor que depender de meter esa lógica en el código.

### ¿Por qué no copiar datos en la imagen?

El Parquet de 1M registros pesa aprox 62MB (sin comprimir). Si lo copiáramos dentro de la imagen, cada `docker build` arrastraría esos 62MB de datos que nunca cambian, y quien descargue la imagen también pagaría ese costo. Pero usando volúmenes, los datos quedan fuera de la imagen y se montan al ejecutar; así la imagen se mantiene ligera y los datos se pueden actualizar sin tener que reconstruirla.

## Registro de Tiempos y Desarrollo

Por último, detallo los tiempos aproximados que invertí en el séptimo ejercicio:

| Fase | Tiempo empleado |
|------|-----------------|
| Investigación previa | 3.5 h |
| Escritura de código | 2.5 h |
| Interpretación y reporte | 1.5 h |
| **Total acumulado** | **7.5 h** |

En este ejercicio invertí una gran cantidad de tiempo investigando y aprendiendo de Docker, principalmente el concepto de capas y el uso de builds multi-stage; por lo que se me complicó coordinar la sincronización entre servicios mediante Compose y el asegurarme de que el servicio de inicialización o setup se ejecute estrictamente una sola vez

---
