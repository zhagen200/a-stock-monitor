import time
from typing import Any, Optional


class DataCache:
    def __init__(self, default_ttl: int = 60):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        value, expire_at = self._store[key]
        if time.time() > expire_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (value, time.time() + ttl)

    def invalidate(self, pattern: str = ""):
        if not pattern:
            self._store.clear()
            return
        keys = [k for k in self._store if pattern in k]
        for k in keys:
            del self._store[k]

    def get_or_set(self, key: str, fn, ttl: Optional[int] = None, force_refresh: bool = False) -> Any:
        if not force_refresh:
            cached = self.get(key)
            if cached is not None:
                return cached
        value = fn()
        self.set(key, value, ttl)
        return value


cache = DataCache()
