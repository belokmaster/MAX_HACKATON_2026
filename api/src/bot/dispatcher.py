import logging
from typing import Any

from src.bot.client import MaxBotClient

logger = logging.getLogger(__name__)

_client: MaxBotClient | None = None

def set_client(client: MaxBotClient) -> None:
    """Установка глобального клиента бота для диспетчеризации событий."""
    global _client
    _client = client

def get_client() -> MaxBotClient:
    """Получение инициализированного клиента бота."""
    if _client is None:
        raise RuntimeError("Клиент MaxBotClient не инициализирован")
    return _client

async def dispatch_update(update: dict[str, Any]) -> None:
    """Маршрутизация входящих событий платформы MAX по соответствующим обработчикам."""
    try:
        client = get_client()
        update_type = update.get("update_type")
        logger.info("Диспетчеризация события платформы MAX: update_type=%s", update_type)
        
        if update_type == "message_created":
            from src.bot.handlers.message import handle_message
            await handle_message(client, update)
        elif update_type == "message_callback":
            from src.bot.handlers.callback import handle_callback
            await handle_callback(client, update)
        elif update_type == "bot_started":
            logger.info("Пользователь запустил бота (событие bot_started)")
            from src.bot.handlers.commands import handle_start
            await handle_start(client, update)
        elif update_type in ("bot_stopped", "bot_added", "bot_removed"):
            logger.info("Получено сервисное событие %s: %s", update_type, update)
        else:
            logger.warning("Получен неизвестный тип события update_type: %s", update_type)
    except Exception:
        logger.exception("Ошибка при обработке входящего события: %s", update)
