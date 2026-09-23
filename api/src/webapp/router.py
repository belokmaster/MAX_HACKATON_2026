from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, status

from src.config import get_settings
from src.webapp.auth import get_user_role, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/me/role")
@router.get("/me/role")
def get_my_role(
    x_max_init_data: str = Header(..., alias="X-Max-Init-Data")
) -> dict:
    """Определение роли пользователя (администратор или жилец) на основе валидации initData WebApp."""
    settings = get_settings()

    try:
        params = validate_init_data(x_max_init_data, settings.BOT_TOKEN)
        user_id: int | None = None

        if "user" in params:
            user_data = json.loads(params["user"])
            if isinstance(user_data, dict) and "id" in user_data:
                user_id = int(user_data["id"])
            else:
                raise ValueError("Некорректная структура данных пользователя")
        elif "user_id" in params:
            user_id = int(params["user_id"])
        else:
            raise ValueError("Поле user отсутствует в параметрах init_data")

        if user_id is None:
            raise ValueError("Не удалось определить ID пользователя из init_data")

        role = get_user_role(user_id, settings.ADMIN_USER_IDS)
        return {"role": role, "user_id": user_id}

    except (ValueError, KeyError, json.JSONDecodeError) as e:
        logger.warning("Ошибка аутентификации WebApp: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
