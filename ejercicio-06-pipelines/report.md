# Ejercicio 6 — Reporte
 
## Pipeline ETL de transacciones
 
Pipeline: `data_source → extract → transform → load`  
Batch: 500 transacciones · Error rate: 15% · Seed: 42
 
---
 
## Resultado de ejecución
 
| Métrica | Valor |
|---------|-------|
| Filas extraídas | 500 |
| Filas válidas | 432 (86.4%) |
| Filas rechazadas | 68 (13.6%) |
| Filas insertadas | 432 |
| Filas duplicadas | 0 |
| Tiempo total | 0.072s |
 
Los números cuadran: 500 = 432 + 68 (extracted = valid + rejected), y 432 = 432 + 0 (valid = inserted + duplicate).
 
---
 
## Distribución de errores detectados
 
| Tipo de error | Cantidad | % del batch |
|---------------|----------|-------------|
| invalid category | 17 | 3.4% |
| transaction_id is not valid UUID4 | 14 | 2.8% |
| amount out of range | 12 | 2.4% |
| timestamp is in the future | 12 | 2.4% |
| user_id is null | 6 | 1.2% |
| amount is null | 3 | 0.6% |
| category is null | 3 | 0.6% |
| merchant_id is null | 1 | 0.2% |
 
El total de errores detectados (68) es más o menos consistente con el `error_rate` de 15% sobre 500 filas. Que el porcentaje real sea 13.6% en vez de 15% tiene sentido, porque `error_rate` es una probabilidad por fila — con 500 filas, el resultado real puede variar un poco por simple azar.
 
Los errores más frecuentes parecen ser las categorías inválidas y los UUIDs malformados. Quizá esto se deba a que `data_source.py` elige el tipo de error de manera uniforme entre 5 opciones, pero la detección es determinista: un UUID malo siempre se detecta, mientras que un `null_field` a veces cae en un campo sin validación estricta (como `status`). , y entonces no se rechaza.
 
---
 
## Separación de capas
 
### Extract — Normalización de formatos
 
La capa de extracción hace tres normalizaciones:
- `country_code` a mayúsculas (`'mx'` → `'MX'`)
- `amount` redondeado a 2 decimales (`123.456` → `123.46`)
- Whitespace eliminado en campos string (`'  Food  '` → `'Food'`)

En extract no se rechaza ninguna fila. Si un valor es `None` o tiene formato irreconocible, simplemente se deja pasar tal cual. Rechazar es tarea de transform. La decisión de rechazar pertenece a transform. Esta separación ayuda a que se puedan cambiar las reglas de validación sin tocar la normalización, o al revés.
 
### Transform — Validación de reglas de negocio
 
Las 5 reglas implementadas:
 
| Regla | Condición de rechazo |
|-------|---------------------|
| transaction_id | No es UUID4 válido |
| amount | Fuera del rango 0.01 - 5,000.00 o null |
| category | No está en las 10 categorías válidas o null |
| country_code | No está en los 15 países válidos o null |
| timestamp | Más de 1 hora en el futuro o formato inválido |
 
Una fila puede acumular varios motivos de rechazo. Si `amount` es null Y `category` es inválida, ambos motivos quedan registrados en cuarentena. Me parece útil para diagnosticar problemas en la fuente: si muchas filas vienen con múltiples errores, podría indicar un problema sistémico.
 
### Cuarentena
 
Las filas rechazadas se guardan en `quarantine/YYYY-MM-DD.jsonl`. Cada línea contiene la fila original completa y la lista de motivos de rechazo:
 
```json
{"row": {"transaction_id": "not-a-valid-uuid", "amount": 150.0, ...}, "reasons": ["transaction_id is not valid UUID4: not-a-valid-uuid"]}
```
 
Al usar JSONL se pueden agregar líneas sin necesidad de leer y reescribir todo el archivo anterior. Si más adelante se corrigen los datos de origen y se quiere reprocesar las filas rechazadas, el archivo de cuarentena ya tiene toda la información necesaria.
 
### Load — Inserción idempotente
 
Usar `INSERT OR IGNORE` con el `transaction_id` hace que si el pipeline se corre dos veces con los mismos datos, el resultado final sea el mismo: la primera vez inserta, la segunda ignora los duplicados. Esto es clave para cuando un pipeline falla a medias y hay que relanzarlo; así no se duplican registros.
 
La carga se hace dentro de una transacción (`with conn:`). Si algo falla durante el `executemany`, SQLite revierte todo, así que la base no queda a medias.
 
---
 
## Idempotencia
 
La idempotencia se revisa en dos niveles:
 
**En los tests:** `test_idempotency` carga la misma fila dos veces y verifica que la base tiene exactamente 1 fila, no 2. La primera ejecución inserta (`inserted=1`), la segunda ignora (`duplicates=1`).
 
**En el pipeline real:** la idempotencia depende de que los `transaction_id` sean los mismos entre ejecuciones. Con `--seed 42`, `data_source.py` produce las mismas filas con los mismos errores, pero `uuid.uuid4()` genera UUIDs diferentes en cada ejecución porque usa el generador del sistema operativo, no `random.seed()`. Por eso dos ejecuciones con el mismo seed generan datos estadísticamente idénticos (mismos montos, mismas categorías, mismos tipos de error) pero con IDs diferentes, y la segunda ejecución inserta 432 filas nuevas en lugar de detectar duplicados.
 
En un entorno real, la idempotencia debería funcionar bien porque los datos vienen con su propio `transaction_id` ya definido por el sistema fuente. Si se reprocesa el mismo batch (por un reintento después de un error), los IDs coincidirían y el `INSERT OR IGNORE` los trataría como duplicados.
 
---
 
## Suite de tests
 
14 tests, todos pasando en 0.36s.
 
| Capa | Tests | Qué validan |
|------|-------|-------------|
| Extract (3) | Normalización de country_code, redondeo de amount, strip de whitespace |
| Transform (8) | Cada tipo de error por separado: monto negativo, monto > 5000, categoría inválida, país inválido, timestamp futuro, UUID malo, amount null, fila válida |
| Load (2) | Inserción correcta e idempotencia con verificación de COUNT |
| End-to-end (1) | Invariante matemática: extracted = valid + rejected, valid = inserted + duplicate |
 
Cada test crea su propio directorio temporal con `tempfile.mkdtemp()` para la base de datos y la cuarentena. Así los tests no se pisan entre ellos ni tocan datos reales.

---

## Registro de Tiempos y Desarrollo

A continuación, detallo los tiempos aproximados que invertí en el sexto ejercicio:

| Fase | Tiempo empleado |
|------|-----------------|
| Investigación previa | 2.5 h |
| Escritura de código | 4 h |
| Interpretación y reporte | 1.5 h |
| **Total acumulado** | **8 h** |

Para este ejercicio, lo que más se me complicó fue lograr garantizar que si el código se ejecuta varias veces seguidas con los mismos datos, no meta duplicados ni rompa el sistema (una buena idempotencia). También el diseñar una zona de cuarentena bien estructurada para dejar registrado exactamente por qué se rechazó cada dato.
