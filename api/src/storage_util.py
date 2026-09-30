"""Атомарная запись файлов JSON-хранилища: временный файл + os.replace."""
import os
import tempfile
import threading
from pathlib import Path

_lock = threading.Lock()


def atomic_write_text(path, data, encoding="utf-8"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding=encoding) as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return len(data)
