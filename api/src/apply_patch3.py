#!/usr/bin/env python3
"""Патч 3: дедупликация входящих событий, отмена заявок «Требует уточнения»."""
import os, py_compile, shutil, sys

BAK = ".bak_dedup"

DEDUP_PY = '''from __future__ import annotations

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
'''


def rd(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def wr(p, t):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)


def once(t, old, new, what):
    n = t.count(old)
    if n != 1:
        raise RuntimeError(f"{what}: якорь найден {n} раз (нужен 1)")
    return t.replace(old, new)


def edit(path, fn):
    t = rd(path)
    new = fn(t)
    if new == t:
        print(f"[SKIP] {path}")
        return
    shutil.copy2(path, path + BAK)
    wr(path, new)
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(path + BAK, path)
        raise RuntimeError(f"{path}: синтаксическая ошибка, восстановлено: {e}")
    print(f"[ OK ] {path}")


LOG = "log = logging.getLogger(__name__)\n"
INIT = LOG + "\n_seen = SeenCache()\n"
IMPORT = "from src.bot.dedup import SeenCache\n"


def patch_message(t):
    if "_seen = SeenCache()" in t:
        return t
    t = once(t, LOG, IMPORT + INIT, "logger в message.py") if False else t
    # импорт добавляем перед строкой logger, чтобы он оказался в блоке импортов
    t = once(t, LOG, IMPORT + "\n" + LOG + "\n_seen = SeenCache()\n", "logger в message.py")
    anchor = "    log.info(\"Получено текстовое сообщение: user_id=%s, chat_id=%s, текст='%s', mid=%s\", user_id, chat_id, text, mid)\n"
    add = (
        "    if mid and _seen.seen(f\"m:{mid}\"):\n"
        "        log.info(\"Дубликат сообщения mid=%s проигнорирован: user_id=%s\", mid, user_id)\n"
        "        return\n"
    )
    return once(t, anchor, anchor + add, "лог получения сообщения")


def patch_callback(t):
    if "_seen = SeenCache()" in t:
        t2 = t
    else:
        t2 = once(t, LOG, IMPORT + "\n" + LOG + "\n_seen = SeenCache()\n", "logger в callback.py")
        anchor = "    # КРИТИЧНО: всегда первым делом подтверждаем получение callback\n"
        add = (
            "    if callback_id and _seen.seen(f\"c:{callback_id}\"):\n"
            "        log.info(\"Дубликат callback %s проигнорирован: user_id=%s\", callback_id, user_id)\n"
            "        return\n\n"
        )
        t2 = once(t2, anchor, add + anchor, "комментарий КРИТИЧНО")
    old = "elif appeal.status not in (AppealStatus.OPEN, AppealStatus.SCHEDULED):"
    new = "elif appeal.status not in (AppealStatus.OPEN, AppealStatus.SCHEDULED, AppealStatus.NEEDS_CLARIFICATION):"
    if old in t2:
        t2 = t2.replace(old, new)
    return t2


def main():
    if not os.path.isdir("bot") or not os.path.isdir("appeals"):
        sys.exit("Запускайте из api/src.")
    p = "bot/dedup.py"
    if not os.path.exists(p):
        wr(p, DEDUP_PY)
        py_compile.compile(p, doraise=True)
        print("[ OK ] bot/dedup.py создан")
    edit("bot/handlers/message.py", patch_message)
    edit("bot/handlers/callback.py", patch_callback)
    print("\nПеред коммитом: find . -name '*%s' -delete; rm -f apply_patch3.py" % BAK)


if __name__ == "__main__":
    main()
