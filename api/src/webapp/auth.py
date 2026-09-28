from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl


def validate_init_data(init_data_raw: str, bot_token: str, max_age: int = 86400) -> dict:
    """Криптографическая проверка подписи HMAC-SHA256 и времени жизни initData WebApp платформы MAX.

    Алгоритм контракта:
    1. parse_qsl(init_data_raw) — парсинг параметров строки
    2. Извлечение хэша (hash)
    3. Проверка актуальности auth_date
    4. Сортировка ключей и сборка строки 'key=value\n'
    5. secret_key = HMAC-SHA256(key="WebAppData", data=bot_token)
    6. calculated = HMAC-SHA256(key=secret_key, data=data_check_string)
    7. compare_digest(calculated, received_hash)
    8. Возврат словаря проверенных параметров
    При ошибке проверки выбрасывает исключение ValueError.
    """
    if not init_data_raw:
        raise ValueError("Строка init_data пуста")

    params = dict(parse_qsl(init_data_raw, keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        raise ValueError("Отсутствует параметр hash")

    auth_date_raw = params.get("auth_date")
    if not auth_date_raw:
        raise ValueError("Отсутствует параметр auth_date")

    try:
        auth_date = int(auth_date_raw)
    except (ValueError, TypeError):
        raise ValueError("Некорректный параметр auth_date")

    if time.time() - auth_date > max_age:
        raise ValueError("Срок действия init_data истек")

    check_pairs = [f"{k}={params[k]}" for k in sorted(params.keys())]
    data_check_string = "\n".join(check_pairs)

    # 1. secret_key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()

    # 2. calculated = HMAC-SHA256(secret_key, data_check_string)
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Недействительная подпись HMAC-SHA256")

    return params


def validate_max_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """Алиас для validate_init_data по спецификации AGENTS.md."""
    return validate_init_data(init_data_raw=init_data, bot_token=bot_token, max_age=max_age_seconds)


def get_user_role(user_id: int, admin_ids: list[int]) -> str:
    """Определение роли пользователя ('admin' или 'resident') по списку администраторов."""
    try:
        uid = int(user_id)
        admin_set = {int(x) for x in admin_ids}
        return "admin" if uid in admin_set else "resident"
    except (ValueError, TypeError):
        return "resident"
