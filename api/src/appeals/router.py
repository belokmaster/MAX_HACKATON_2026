from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from src.appeals.schemas import AppealStatus
from src.appeals.service import (
    cancel_appeal,
    create_appeal,
    get_all_appeals,
    get_appeal,
    get_user_appeals,
    update_status,
)

router = APIRouter()


class CreateAppealRequest(BaseModel):
    user_id: int
    chat_id: int
    uk_id: str
    category: str
    responsibility: str
    description: str


class UpdateAppealStatusRequest(BaseModel):
    status: str


@router.get("/api/health")
@router.get("/health")
def health_check() -> dict:
    """Проверка доступности API сервиса."""
    return {"status": "ok", "service": "zhkh-bot"}


@router.get("/api/appeals")
@router.get("/appeals")
def list_appeals(user_id: int | None = None) -> list[dict]:
    """Получение списка заявок (опционально по user_id)."""
    if user_id is not None:
        appeals = get_user_appeals(user_id)
    else:
        appeals = get_all_appeals()
    return [appeal.to_dict() for appeal in appeals]


@router.post("/api/appeals", status_code=status.HTTP_201_CREATED)
@router.post("/appeals", status_code=status.HTTP_201_CREATED)
def create_new_appeal(body: CreateAppealRequest) -> dict:
    """Создание новой заявки жильца."""
    appeal = create_appeal(
        user_id=body.user_id,
        chat_id=body.chat_id,
        uk_id=body.uk_id,
        category=body.category,
        responsibility=body.responsibility,
        description=body.description,
    )
    return appeal.to_dict()


@router.get("/api/appeals/{appeal_id}")
@router.get("/appeals/{appeal_id}")
def read_appeal(appeal_id: str) -> dict:
    """Получение данных заявки по идентификатору."""
    appeal = get_appeal(appeal_id)
    if appeal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )
    return appeal.to_dict()


@router.patch("/api/appeals/{appeal_id}")
@router.patch("/appeals/{appeal_id}")
def patch_appeal_status(appeal_id: str, body: UpdateAppealStatusRequest) -> dict:
    """Обновление статуса заявки."""
    try:
        new_status = AppealStatus(body.status.lower())
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимый статус заявки: {body.status}",
        )

    appeal = update_status(appeal_id, new_status)
    if appeal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )
    return appeal.to_dict()


@router.delete("/api/appeals/{appeal_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/appeals/{appeal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appeal(appeal_id: str) -> Response:
    """Отмена (удаление) заявки по идентификатору."""
    appeal = cancel_appeal(appeal_id)
    if appeal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заявка не найдена",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
