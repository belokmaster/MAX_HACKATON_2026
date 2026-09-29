#!/usr/bin/env python3
"""Патч 2: город+адрес, /address, подсказка про адрес, защита address:. Запускать из api/src."""
import os
import py_compile
import shutil
import sys

ROOT = os.getcwd()
BAK = ".bak_addr"


def P(*a):
    return os.path.join(ROOT, *a)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, t):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)


HOUSING_ADD = r'''

# ---- город демо-реестра (модельные данные) ----
DEMO_CITY = "Москва"


def strip_demo_city(text: str) -> str:
    """Убирает в начале запроса город демо-реестра: «Москва, ул. Пушкина, д. 10»."""
    parts = [p.strip() for p in (text or "").split(",", 1)]
    if len(parts) == 2:
        head = re.sub(r"^(г|город)\s+", "", _normalize(parts[0]))
        if head == _normalize(DEMO_CITY):
            return parts[1]
    return text
'''

ADDRESS_HINT = '''            if result.category == Category.UNKNOWN and find_uk(strip_demo_city(text)):
                state.step = DialogStep.AWAIT_PROBLEM
                conv_store.save(state)
                await client.send_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=(
                        "Похоже, вы прислали адрес. Дом уже выбран, чтобы сменить его, отправьте /address. "
                        "А пока опишите, что случилось (например: «течёт кран», «не горит свет в подъезде»)."
                    ),
                )
                return
'''

HANDLE_ADDRESS = '''


async def handle_address(client: MaxBotClient, update: dict) -> None:
    """Смена адреса дома (/address): сбрасывает привязку к УК и запрашивает адрес заново."""
    user_id, chat_id = extract_ids(update)
    log.info("Команда /address: смена адреса user_id=%s", user_id)
    state = conv_store.get_or_create(user_id, chat_id)
    state.step = DialogStep.AWAIT_ADDRESS
    state.uk_id = None
    state.pending_appeal_id = None
    state.category = None
    state.responsibility = None
    state.original_text = ""
    conv_store.save(state)
    await client.send_message(
        chat_id=chat_id,
        user_id=user_id,
        text="Напишите город и адрес вашего дома (например: «Москва, ул. Пушкина, д. 10»):",
    )
'''

NOT_FOUND_OLD = 'text="Адрес не найден в базе. Попробуйте уточнить (например: «ул. Пушкина, д. 10») или свяжитесь с диспетчерской УК."'
NOT_FOUND_NEW = ('text="Адрес не найден в демо-реестре. Сейчас в нём только г. Москва, например: '
                 '«Москва, ул. Пушкина, д. 10». Проверьте написание и отправьте адрес ещё раз."')


class Skip(Exception):
    pass


def edit(path, fn):
    """fn(text)->new_text; при ошибке файл не меняется."""
    text = read(path)
    new = fn(text)
    if new == text:
        raise Skip("нечего менять")
    bak = path + BAK
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    write(path, new)
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(bak, path)
        raise RuntimeError(f"синтаксическая ошибка, файл восстановлен: {e}")


def replace_once(t, old, new, what):
    n = t.count(old)
    if n != 1:
        raise RuntimeError(f"{what}: якорь найден {n} раз (нужен ровно 1)")
    return t.replace(old, new)


def patch_housing(t):
    if "def strip_demo_city" in t:
        return t
    return t.rstrip("\n") + "\n" + HOUSING_ADD


def patch_message(t):
    if "strip_demo_city" in t:
        return t
    t = replace_once(t, "from src.data.housing import find_uk, get_uk_by_id",
                     "from src.data.housing import find_uk, get_uk_by_id, strip_demo_city", "импорт housing")
    t = replace_once(t, "        matches = find_uk(text)\n",
                     "        matches = find_uk(strip_demo_city(text))\n", "поиск адреса")
    t = replace_once(t, NOT_FOUND_OLD, NOT_FOUND_NEW, "сообщение «адрес не найден»")
    t = replace_once(t, "            if result.category == Category.UNKNOWN:\n",
                     ADDRESS_HINT + "            if result.category == Category.UNKNOWN:\n", "ветка UNKNOWN")
    t = replace_once(t, '        elif cmd == "/admin":\n',
                     '        elif cmd == "/address":\n'
                     '            from src.bot.handlers.commands import handle_address\n'
                     '            await handle_address(client, update)\n'
                     '        elif cmd == "/admin":\n', "диспетчер команд")
    if "/start, /help, /status\"" in t:
        t = t.replace("/start, /help, /status\"", "/start, /address, /help, /status\"")
    return t


def patch_commands(t):
    if "def handle_address" in t:
        return t
    old = "укажите адрес вашего дома (например: «ул. Пушкина, д. 10»):"
    new = "напишите город и адрес вашего дома (например: «Москва, ул. Пушкина, д. 10»):"
    t = replace_once(t, old, new, "приветствие /start")
    return t.rstrip("\n") + "\n" + HANDLE_ADDRESS


def patch_callback(t):
    if '"address:": (DialogStep.AWAIT_ADDRESS,)' in t:
        return t
    old = '        "book:": (DialogStep.AWAIT_BOOKING,),\n'
    new = old + '        "address:": (DialogStep.AWAIT_ADDRESS,),\n'
    return replace_once(t, old, new, "allowed_steps в callback.py")


def main():
    if not all(os.path.isdir(p) for p in (P("bot"), P("data"), P("conversation"))):
        sys.exit("Запускайте из api/src.")
    steps = [
        ("data/housing.py", patch_housing),
        ("bot/handlers/message.py", patch_message),
        ("bot/handlers/commands.py", patch_commands),
        ("bot/handlers/callback.py", patch_callback),
    ]
    for rel, fn in steps:
        try:
            edit(P(*rel.split("/")), fn)
            print(f"[ OK ] {rel}")
        except Skip as e:
            print(f"[SKIP] {rel}: {e}")
        except Exception as e:
            print(f"[FAIL] {rel}: {e}")
            sys.exit("Остановился. Уже изменённые файлы можно откатить командой ниже.")

    # быстрая самопроверка
    try:
        sys.path.insert(0, os.path.dirname(ROOT))
        from src.data.housing import find_uk, strip_demo_city
        print("\nСамопроверка:")
        print("  strip_demo_city:", repr(strip_demo_city("Москва, ул. Пушкина, д. 10")))
        for q in ("Москва, ул. Пушкина, д. 10", "копа", "караваевская", "Казань, ул. Ленина, д. 5"):
            print(f"  find_uk({q!r}) ->", [m.address for m in find_uk(strip_demo_city(q))])
    except Exception as e:
        print("Самопроверку пропустил:", e)

    print("\nОткат: for f in $(find . -name '*%s'); do mv \"$f\" \"${f%%%s}\"; done" % (BAK, BAK))
    print("Перед коммитом: find . -name '*%s' -delete; rm -f apply_patch2.py" % BAK)


if __name__ == "__main__":
    main()
