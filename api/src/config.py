from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import field_validator
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

    # Список идентификаторов администраторов через запятую в .env: ADMIN_USER_IDS=123456,789012
    ADMIN_USER_IDS: list[int] = []

    @field_validator("ADMIN_USER_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> list[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str) and v.strip():
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []

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
