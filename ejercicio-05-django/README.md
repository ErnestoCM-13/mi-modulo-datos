# Ejercicio 5 — El Backend con Estructura

API REST con Django y Django REST Framework que replica los 6 endpoints del E04.
Datos gestionados por el ORM de Django, autenticación por token, panel admin funcional.

## Requisitos

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- Parquet de 1M transacciones del Ejercicio 1
## Instalación

```bash
cd ejercicio-05-django
uv sync
```

## Levantar el servidor desde cero

```bash
# 1. Aplicar migraciones
uv run python manage.py migrate

# 2. Cargar transacciones desde Parquet
uv run python manage.py load_transactions --parquet ../data/transactions_1m_none.parquet

# 3. Crear superusuario para el admin
uv run python manage.py createsuperuser

# 4. Arrancar el servidor
uv run python manage.py runserver
```

El servidor arranca en `http://localhost:8000`.  
Panel admin en `http://localhost:8000/admin/`.

## Obtener un token

```bash
uv run python manage.py shell -c "
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
user = User.objects.first()
token, _ = Token.objects.get_or_create(user=user)
print(f'Token: {token.key}')
"
```

## Endpoints

| Método | Ruta | Auth | Backend |
|--------|------|------|---------|
| GET | `/health` | No | Memoria |
| GET | `/analytics/summary` | No | DuckDB + cache |
| GET | `/analytics/top-merchants?limit=N&country=XX` | No | DuckDB + cache |
| GET | `/users/{user_id}/transactions?page=N&page_size=M` | Token | ORM (SQLite) |
| GET | `/users/{user_id}/stats` | Token | ORM (SQLite) |
| POST | `/transactions/batch` | Token | ORM (SQLite) |

### Ejemplos

```bash
# Público
curl http://localhost:8000/health
curl http://localhost:8000/analytics/summary
curl "http://localhost:8000/analytics/top-merchants?limit=5&country=MX"

# Autenticado
curl -H "Authorization: Token <tu-token>" http://localhost:8000/users/1/transactions
curl -H "Authorization: Token <tu-token>" http://localhost:8000/users/1/stats
curl -X POST -H "Authorization: Token <tu-token>" \
     -H "Content-Type: application/json" \
     -d '[{"transaction_id":"test-001","timestamp":"2026-05-01 12:00:00","user_id":1,"merchant_id":1,"amount":50.0,"category":"Food","country_code":"MX","status":"completed"}]' \
     http://localhost:8000/transactions/batch
```

## Correr tests

```bash
uv run python manage.py test tests
```

## Variables de entorno
 
| Variable | Default | Descripción |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | `dev-secret-key-...` | Clave secreta de Django |
| `DJANGO_DEBUG` | `True` | Modo debug |
| `PARQUET_PATH` | `../data/transactions_1m_none.parquet` | Ruta al Parquet para DuckDB |
