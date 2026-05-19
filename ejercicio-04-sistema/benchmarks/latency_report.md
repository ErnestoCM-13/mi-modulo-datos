# Benchmark de Latencia

Requests por endpoint: 100  
Primera request = cold (sin cache) · Resto = warm (con cache activo)

## Resultados

| Endpoint | Cold (ms) | p50 warm (ms) | p95 warm (ms) | p99 warm (ms) |
|----------|----------|--------------|--------------|--------------|
| GET /analytics/summary | 53.87 | 2.13 | 2.45 | 2.7 |
| GET /analytics/top-merchants | 347.36 | 2.09 | 2.61 | 3.29 |
| GET /analytics/top-merchants?limit=5&country=MX | 20.62 | 2.05 | 2.35 | 2.62 |
| GET /users/1/transactions | 3.82 | 2.52 | 3.11 | 3.46 |
| GET /users/1/stats | 3.38 | 2.16 | 2.68 | 2.9 |
| GET /health | 2.32 | 2.06 | 2.57 | 2.77 |

## Análisis

### Impacto del cache en endpoints analíticos

Los endpoints analíticos promedian 140.6ms en cold y 2.1ms en warm (p50), una mejora de **67x** gracias al cache en memoria.

### Endpoints transaccionales

Los endpoints de usuario promedian 2.3ms (p50), cumpliendo el SLA de < 80ms gracias a los índices de SQLite.

### SLAs

| Endpoint | SLA | Cold | Warm p50 | Cumple |
|----------|-----|------|----------|--------|
| GET /analytics/summary | < 500ms cold / < 20ms warm | 53.87ms | 2.13ms | ✓ |
| GET /analytics/top-merchants | < 500ms cold / < 20ms warm | 347.36ms | 2.09ms | ✓ |
| GET /users/1/transactions | < 80ms | 3.82ms | 2.52ms | ✓ |
| GET /users/1/stats | < 80ms | 3.38ms | 2.16ms | ✓ |
| GET /health | < 50ms | 2.32ms | 2.06ms | ✓ |
