import time

class Cache:
    def __init__(self):
        self._store  = {}
        self._hits   = 0
        self._misses = 0

    def get(self, key: str):
        if key in self._store:
            entry = self._store[key]
            if time.time() < entry['expires']:
                self._hits += 1
                return entry['data']
            del self._store[key]
        self._misses += 1
        return None

    def set(self, key: str, data, ttl: int = 60):
        self._store[key] = {
            'data':    data,
            'expires': time.time() + ttl,
        }

    def invalidate_prefix(self, prefix: str):
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]

    def hit_rate(self) -> float:
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return round(self._hits / total, 4)

cache = Cache()
