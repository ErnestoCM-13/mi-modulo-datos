# Ejercicio 5 — Reporte
 
## Arquitectura: FastAPI (E4) vs Django REST Framework (E5)
 
Este ejercicio reconstruyeron los mismos 6 endpoints del E4, pero esta vez utilizando Django y DRF. Aunque la funcionalidad es exactamente la misma, las diferencias clave radican en la organización y la estructura del código.
 
---
 
## Modelo de datos y migraciones
 
El modelo `Transaction` en `models.py` replica el schema de los ejercicios anteriores. Los dos índices compuestos del E3 se definieron mediante `Meta.indexes`:
 
```python
class Meta:
    indexes = [
        models.Index(fields=['user_id', 'timestamp'], name='idx_user_timestamp'),
        models.Index(fields=['country_code', 'user_id'], name='idx_country_user'),
    ]
```
 
Django se encarga de generar automáticamente la migración con el `CREATE TABLE` y los `CREATE INDEX`. La ventaja principal frente al `schema.sql` manual del E3 es que las migraciones quedan versionadas, es decir, si más adelante se añade un campo o un índice, Django genera una migración incremental que solo aplica ese cambio específico, de esta forma se evita tener que recrear la tabla desde cero.
 
---
 
## Decisiones de backend por endpoint
 
Se mantuvo la misma arquitectura dual del ejercicio 4:
 
| Endpoint | Backend | Razón |
|----------|---------|-------|
| `/analytics/*` | DuckDB sobre Parquet | Consultas analíticas de agregación. DuckDB con projection pushdown es significativamente más rápido que el ORM para operaciones de `GROUP BY` sobre 1M de filas (como se vio en E2).|
| `/users/*` | ORM de Django (SQLite) | Consultas transaccionales por usuario. El ORM genera las mismas queries que el SQL crudo del E4, y los índices `idx_user_timestamp` ayudan a mantener los tiempos por debajo de 1ms (como se vio en E3).|
| `/transactions/batch` | ORM de Django (SQLite) | Uso de `bulk_create` con deduplicación e invalidación del caché analítico al insertar datos nuevos.|
| `/health` | Memoria | No requiere acceso a bases de datos. |
 
Optar por DuckDB directamente para la parte de analytics en lugar de pasar por el ORM me parece lo más adecuado, ya que el ORM de Django no está diseñado para leer Parquet de forma nativa ni aprovecha las optimizaciones columnares que implementa DuckDB.
 
---
 
## Autenticación por token
 
Los endpoints quedaron divididos en dos niveles de acceso:
 
**Públicos** (`AllowAny`): `/health`, `/analytics/summary`, `/analytics/top-merchants`. Al tratarse de datos agregados que no exponen información sensible de usuarios individuales, no creí necesario requerir autenticación.
 
**Protegidos** (`IsAuthenticated`): `/users/*/transactions`, `/users/*/stats`, `/transactions/batch`. Estos endpoints consultan datos específicos de usuarios o modifican el estado de la base de datos, por lo que estos sí exigen un token válido en el header `Authorization: Token <key>`
 
DRF resuelve la validación de forma nativa: si el token falta o no es válido, intercepta la petición y devuelve un HTTP 401 directamente. Esto resulta bastante más limpio que gestionar la verificación de forma manual dentro de cada vista.
 
---
 
## Django Admin
 
Se habilitó el panel en `/admin/` para poder explorar las transacciones de forma visual sin depender de consultas SQL. La configuración incluye:
 
- **list_display**: para visualizar las 8 columnas del schema en la tabla principal.
- **list_filter**: filtros laterales por `status` y `country_code`, esto resulta útil para aislar, por ejemplo, transacciones `failed` de `MX` rápidamente.
- **search_fields**: búsqueda parcial por `transaction_id` y exacta por `user_id`.
- **ordering**: muestra los registros más recientes primero.

Para un equipo de producto o soporte, contar con esta interfaz puede ahorrar bastante tiempo al permitir consultar datos sin necesidad de interactuar directamente con la base de datos.
 
---
 
## Ingesta con chunking real
 
El management command `load_transactions` incorpora los ajustes que me fueron sugeridos en el feedback del ejercicio 3:
 
- Lee el archivo Parquet (en lugar de un CSV) mediante `pyarrow.parquet.iter_batches`, evitando cargar todo el dataset en memoria.
- Utiliza `bulk_create(ignore_conflicts=True)` para asegurar la idempotencia (ejecutarlo más de una vez no duplica los registros).
- Muestra una barra o indicador de progreso por cada chunk procesado.
---
 
## Mejoras aplicadas desde el feedback de E4

También apliqué diferentes mejoras basandome en mi feedback del ejercicio 4
 
| Feedback E4 | Implementación en E5 |
|-------------|---------------------|
| Falta `PRAGMA journal_mode=WAL` | Configurado en `apps.py` mediante la señal `connection_created`, de esta forma se aplica en cada nueva conexión de SQLite. |
| Cache no se invalida al insertar | Se ejecuta `cache.invalidate_prefix('analytics:')` al finalizar con éxito cada inserción en batch. |
| Variables hardcodeadas | `SECRET_KEY`, `DEBUG` y `PARQUET_PATH` ahora se leen desde variables de entorno con defaults seguros. |
 
---
 
## Comparación FastAPI vs Django REST Framework

Durante la resolución del ejercicio, pude observar las diferencias a la hora de utilizar FastAPI y Django REST. La siguiente tabla muestra, de forma resumida, las que considero importante mencionar
 
| Aspecto | FastAPI (E4) | Django REST Framework (E5) |
|---------|-------------|---------------------------|
| Setup inicial | Mínimo: un archivo `main.py` | Más código: settings, urls, apps, models, serializers, views |
| Modelo de datos | SQL crudo o conexión manual | ORM con migraciones automáticas |
| Validación | Pydantic (integrado) | Serializers de DRF (separados del modelo) |
| Autenticación | Manual o con dependencias | Integrada con `permission_classes` |
| Admin panel | No existe | Gratis con `django.contrib.admin` |
| Performance | Más rápido en requests async | Comparable en requests síncronos |
| Curva de aprendizaje | Baja para APIs simples | Más alta, pero más estructura a cambio |

| Aspecto | FastAPI (E4) | Django REST Framework (E5) |
| --- | --- | --- |
| Setup inicial | Mínimo: suele bastar con un archivo `main.py` | Más código: requiere configurar settings, urls, apps, models, serializers y views |
| Modelo de datos | SQL nativo o gestión manual de conexiones | ORM integrado con sistema de migraciones automatizado |
| Validación | Pydantic (integrado) | Serializers de DRF (separados del modelo) |
| Autenticación | Manual o mediante dependencias externas | Integrada a través de `permission_classes` |
| Panel de Admin | No incluye de forma nativa | Disponible inmediatamente con `django.contrib.admin` |
| Rendimiento | Generalmente superior en requests async | Similar en operaciones síncronas |
 
**¿Cuándo usar cada uno?**
 
FastAPI parece ser la mejor opción cuando se necesita una API ligera, se quiere mantener el control total de la arquitectura o el proyecto se beneficia del rendimiento async (como en streaming, WebSockets o alta concurrencia)..
 
Por otro lado, siento que Django + DRF es mejor cuando se prefiere un framework que resuelva casi todo de entrada: panel de administración, autenticación armada, migraciones consistentes y un ecosistema de plugins. Si el proyecto va a crecer y necesita estructura, Django  te evita decisiones de diseño que FastAPI dejaría abiertas.
 
---
 
## Suite de tests
 
Incluí 10 tests utilizando el `APIClient` de DRF, todos pasando en 1.59s.
 
| Test | Qué valida |
|------|-----------|
| test_health_returns_200 | Estructura completa del /health |
| test_summary_structure | Campos esperados en /analytics/summary|
| test_top_merchants_default | Retorno del top de los 10 merchants |
| test_transactions_requires_auth | Retorno de 401 si falta el token |
| test_transactions_with_token | Respuesta correcta usando un token válido |
| test_stats_with_token | Estructura de la respuesta en /users/stats |
| test_user_not_found_404 | Manejo del error 404 para usuarios inexistentes |
| test_batch_requires_auth | Retorno de 401 al intentar un POST sin token |
| test_batch_valid | Inserción de datos con validación de conteos |
| test_batch_invalid_schema_422 | Manejo de schema incompleto con error 422 |

---

## Registro de Tiempos y Desarrollo

Por último, detallo los tiempos aproximados que invertí en el quinto ejercicio:

| Fase | Tiempo empleado |
|------|-----------------|
| Investigación previa | 4 h |
| Escritura de código | 5 h |
| Interpretación y reporte | 1.5 h |
| **Total acumulado** | **10.5 h** |

En este ejercicio, me tardé más enadaptarme a Django y su filosofía de "convención sobre configuración", porque me chocó un poco con la flexibilidad que ya veníamos manejando en FastAPI. Además, me tomó bastante tiempo de investigación entender cómo integrar su ORM con una fuente externa como DuckDB usando archivos Parquet.
