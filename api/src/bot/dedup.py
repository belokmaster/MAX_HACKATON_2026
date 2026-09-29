from __future__ import annotations

import time
from collections import OrderedDict


class SeenCache:
    """Запоминает недавно обработанные идентификаторы событий (защита от повторной доставки)."""

    def __init__(self, ttl: float = 600.0, maxsize: int = 5000) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._items: OrderedDict[str, float] = OrderedDict()

    def seen(self, key: str) -> bool:
        """True, если ключ уже встречался; иначе запоминает его и возвращает False."""
        now = time.monotonic()
        while self._items:
            k, ts = next(iter(self._items.items()))
            if now - ts > self._ttl or len(self._items) > self._maxsize:
                self._items.popitem(last=False)
            else:
                break
        if key in self._items:
            return True
        self._items[key] = now
        return False
