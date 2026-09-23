from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Параметры платформы MAX
    BOT_TOKEN: str
    WEBHOOK_SECRET: str
    WEBHOOK_URL: str
    API_BASE_URL: str = "https://platform-api2.max.ru"
    SSL_CERT_PATH: str = "/app/certs/Russian_Trusted_Root_CA.cer"

    # Список идентификаторов администраторов в .env: ADMIN_USER_IDS=123456,789012
    admin_user_ids: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_USER_IDS", "admin_user_ids"),
    )

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def _coerce_admin_ids_str(cls, v: Any) -> str:
        if isinstance(v, list):
            return ",".join(str(x) for x in v)
        if isinstance(v, str):
            return v
        return ""

    @property
    def ADMIN_USER_IDS(self) -> list[int]:
        """Возвращает список ID администраторов в виде list[int]."""
        v = self.admin_user_ids.strip() if self.admin_user_ids else ""
        if not v:
            return []
        if v.startswith("[") and v.endswith("]"):
            try:
                import json
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [int(x) for x in parsed if str(x).isdigit()]
            except Exception:
                pass
        return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]

    @ADMIN_USER_IDS.setter
    def ADMIN_USER_IDS(self, value: list[int] | str) -> None:
        """Позволяет задавать список администраторов программно."""
        if isinstance(value, list):
            self.admin_user_ids = ",".join(str(x) for x in value)
        else:
            self.admin_user_ids = str(value)

    # Настройки планировщика
    N_DAYS_AHEAD: int = 3   # Количество дней вперед для предложения смен
    MAX_CAPACITY: int = 4   # Максимальное число заявок на одну смену

    # Файлы хранения данных JSON (без использования тяжелой СУБД)
    USERS_FILE: str = "data/users.json"
    APPEALS_FILE: str = "data/appeals.json"


@lru_cache
def get_settings() -> Settings:
    """Получение кэшированного экземпляра настроек приложения."""
    return Settings()
