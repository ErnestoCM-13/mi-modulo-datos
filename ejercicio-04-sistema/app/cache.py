import time

class Cache:
    def __init__(self):
        self._store = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str):
        """Devuelve el valor cacheado si existe y no expiró. None si no."""
        if key in self._store:
            entry = self._store[key]
            if time.time() < entry['expires']:
                self._hits += 1
                return entry['data']
            del self._store[key]
        self._misses += 1
        return None

    def set(self, key: str, data, ttl: int = 60):
        """Guarda un valor con tiempo de expiración en segundos."""
        self._store[key] = {
            'data': data,
            'expires': time.time() + ttl,
        }

    def hit_rate(self) -> float:
        """Porcentaje de aciertos desde el arranque del servidor."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return round(self._hits / total, 4)

    def clear(self):
        """Limpia todo el cache (útil para benchmarks cold vs warm)."""
        self._store.clear()

cache = Cache()
