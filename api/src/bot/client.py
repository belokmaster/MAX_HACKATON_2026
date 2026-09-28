import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


class MaxBotClient:
    def __init__(self):
        self.settings = get_settings()
        cert_path = self.settings.SSL_CERT_PATH
        verify: Any = cert_path
        if cert_path and not Path(cert_path).exists():
            logger.warning("Файл сертификата %s не найден, используется системное хранилище CA", cert_path)
            verify = True

        self.client = httpx.AsyncClient(
            base_url=self.settings.API_BASE_URL,
            headers={
                "Authorization": self.settings.BOT_TOKEN,
                "Content-Type": "application/json",
            },
            verify=verify,
        )
        self._chat_locks: dict[int, asyncio.Lock] = {}

    def _get_chat_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._chat_locks:
            self._chat_locks[chat_id] = asyncio.Lock()
        return self._chat_locks[chat_id]

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

    async def _safe_request(self, method: str, url: str, **kwargs) -> dict | None:
        """Безопасное выполнение запроса к API MAX с логированием ошибок."""
        try:
            response = await self.client.request(method, url, **kwargs)
            if not response.is_success:
                logger.error(f"Ошибка MAX API {response.status_code} при {method} {url}: {response.text}")
                return None
            
            if response.status_code == 204:
                return {}
                
            return response.json()
        except Exception:
            logger.exception(f"Исключение при выполнении {method} {url}")
            return None

    async def _rate_limited_send(self, chat_id: int, method: str, url: str, **kwargs) -> dict | None:
        """Отправка сообщений с ограничением частоты (не чаще 1 запроса в 500 мс на чат)."""
        lock = self._get_chat_lock(chat_id)
        async with lock:
            res = await self._safe_request(method, url, **kwargs)
            await asyncio.sleep(0.5)
            return res

    async def get_me(self) -> dict | None:
        """Получение информации о текущем боте."""
        return await self._safe_request("GET", "/me")

    async def set_commands(self, commands: list[dict]) -> dict | None:
        """Установка списка команд бота."""
        return await self._safe_request("PATCH", "/me/commands", json={"commands": commands})

    async def set_webhook(self, url: str, secret: str, update_types: list[str] | None = None) -> dict | None:
        """Регистрация вебхука на платформе MAX."""
        if update_types is None:
            update_types = ["message_created", "message_callback", "bot_started", "bot_stopped", "bot_added"]
        payload = {
            "url": url,
            "secret": secret,
            "update_types": update_types
        }
        return await self._safe_request("POST", "/subscriptions", json=payload)

    async def delete_webhook(self, subscription_id: str) -> dict | None:
        """Удаление подписки на вебхук."""
        return await self._safe_request("DELETE", f"/subscriptions/{subscription_id}")

    async def send_message(self, *, user_id: int | None = None, chat_id: int | None = None, text: str, format: str = "markdown", attachments: list[dict] | None = None, reply_to_mid: str | None = None) -> dict | None:
        """Отправка сообщения пользователю или в чат."""
        target_id = chat_id or user_id
        if not target_id:
            logger.error("send_message: необходимо указать user_id или chat_id")
            return None
            
        params: dict[str, Any] = {"disable_link_preview": "false"}
        if user_id and (not chat_id or chat_id == user_id):
            params["user_id"] = str(user_id)
        elif chat_id:
            params["chat_id"] = str(chat_id)
        elif user_id:
            params["user_id"] = str(user_id)

        payload: dict[str, Any] = {
            "text": text,
            "format": format,
            "notify": True,
        }
        if attachments:
            payload["attachments"] = attachments
        if reply_to_mid:
            payload["link"] = {"type": "reply", "mid": reply_to_mid}

        preview = text.replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:57] + "..."
        logger.info("Отправка сообщения target=%s (params=%s): '%s' (вложений: %d)", target_id, params, preview, len(attachments) if attachments else 0)

        res = await self._rate_limited_send(target_id, "POST", "/messages", params=params, json=payload)
        if res is None:
            alt_params = None
            if "chat_id" in params and user_id and str(user_id) != params.get("chat_id"):
                alt_params = {"user_id": str(user_id), "disable_link_preview": "false"}
            elif "user_id" in params and chat_id and str(chat_id) != params.get("user_id"):
                alt_params = {"chat_id": str(chat_id), "disable_link_preview": "false"}
            elif "chat_id" in params and chat_id and chat_id > 0:
                alt_params = {"user_id": str(chat_id), "disable_link_preview": "false"}

            if alt_params:
                logger.info("Повторная попытка отправки с альтернативными параметрами: %s", alt_params)
                res = await self._rate_limited_send(target_id, "POST", "/messages", params=alt_params, json=payload)

        return res

    async def edit_message(self, message_id: str, text: str | None = None, format: str = "markdown", attachments: list[dict] | None = None) -> dict | None:
        """Редактирование ранее отправленного сообщения."""
        payload = {}
        if text is not None:
            payload["text"] = text
            payload["format"] = format
        if attachments is not None:
            payload["attachments"] = attachments
            
        logger.info("Редактирование сообщения mid=%s", message_id)
        return await self._safe_request("PUT", "/messages", params={"message_id": str(message_id)}, json=payload)

    async def answer_callback(self, callback_id: str, notification: str = "", message: dict | None = None) -> dict | None:
        """Ответ на callback от кнопки (обязателен для снятия индикатора загрузки).
        Платформа MAX требует обязательное поле notification или message в теле запроса.
        """
        payload: dict = {"notification": notification}
        if message:
            payload["message"] = message
        logger.info("Подтверждение callback_id=%s (POST /answers)", callback_id)
        return await self._safe_request("POST", "/answers", params={"callback_id": str(callback_id)}, json=payload)

    async def send_action(self, chat_id: int, action: str = "typing_on") -> None:
        """Отправка действия в чат (например, набор текста)."""
        await self._rate_limited_send(chat_id, "POST", f"/chats/{chat_id}/actions", json={"action": action})
