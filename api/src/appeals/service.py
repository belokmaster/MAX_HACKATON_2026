from __future__ import annotations

from src.storage_util import atomic_write_text

from datetime import datetime
import json
import logging
from pathlib import Path
import uuid

from src.appeals.schemas import Appeal, AppealStatus

logger = logging.getLogger(__name__)

_appeals: dict[str, Appeal] = {}  # Словарь всех заявок: id -> Appeal
_appeals_file: Path = Path("data/appeals.json")


def configure(appeals_file: str) -> None:
    """Настройка пути к файлу сохранения и загрузка заявок."""
    global _appeals_file
    _appeals_file = Path(appeals_file)
    _load()


def create_appeal(
    user_id: int,
    chat_id: int,
    uk_id: str,
    category: str,
    responsibility: str,
    description: str,
) -> Appeal:
    """Создание новой заявки жильца, сохранение в памяти и на диске."""
    appeal_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    appeal = Appeal(
        id=appeal_id,
        user_id=int(user_id),
        chat_id=int(chat_id),
        uk_id=str(uk_id),
        category=str(category),
        responsibility=str(responsibility),
        description=str(description),
        status=AppealStatus.OPEN,
        created_at=now,
        updated_at=now,
    )
    _appeals[appeal_id] = appeal
    _persist()
    logger.info(
        "Создана новая заявка #%s: user_id=%s, chat_id=%s, uk_id=%s, категория=%s, ответственность=%s, статус=%s",
        appeal_id, user_id, chat_id, uk_id, category, responsibility, appeal.status.value
    )
    return appeal


def get_appeal(appeal_id: str) -> Appeal | None:
    """Получение заявки по ее идентификатору."""
    return _appeals.get(appeal_id)


def get_user_appeals(user_id: int) -> list[Appeal]:
    """Получение всех заявок пользователя, отсортированных по дате создания (новые первыми)."""
    uid = int(user_id)
    user_appeals = [a for a in _appeals.values() if a.user_id == uid]
    return sorted(user_appeals, key=lambda a: a.created_at, reverse=True)


def update_status(appeal_id: str, status: AppealStatus | str) -> Appeal | None:
    """Обновление статуса заявки с сохранением на диске."""
    appeal = _appeals.get(appeal_id)
    if appeal is None:
        logger.warning("Попытка обновить статус несуществующей заявки #%s", appeal_id)
        return None
    if isinstance(status, str):
        try:
            status = AppealStatus(status.lower())
        except (ValueError, TypeError):
            pass
    prev_status = appeal.status
    appeal.status = status
    appeal.updated_at = datetime.now().isoformat()
    _persist()
    logger.info("Статус заявки #%s изменен: %s -> %s", appeal_id, prev_status, appeal.status)
    return appeal


def update_window(appeal_id: str, window_id: str, window_label: str) -> Appeal | None:
    """Назначение смены мастера и перевод заявки в статус SCHEDULED."""
    appeal = _appeals.get(appeal_id)
    if appeal is None:
        logger.warning("Попытка назначить смену для несуществующей заявки #%s", appeal_id)
        return None
    appeal.window_id = window_id
    appeal.window_label = window_label
    appeal.status = AppealStatus.SCHEDULED
    appeal.updated_at = datetime.now().isoformat()
    _persist()
    logger.info("Назначена смена для заявки #%s: window_id=%s, время='%s', статус=SCHEDULED", appeal_id, window_id, window_label)
    return appeal


def cancel_appeal(appeal_id: str) -> Appeal | None:
    """Отмена заявки жильцом или диспетчером с освобождением забронированной смены мастера."""
    appeal = _appeals.get(appeal_id)
    if appeal is None:
        logger.warning("Попытка отмены несуществующей заявки #%s", appeal_id)
        return None
    appeal.status = AppealStatus.CANCELLED
    appeal.updated_at = datetime.now().isoformat()
    _persist()
    try:
        from src.scheduler.store import unbook_appeal
        unbook_appeal(appeal_id)
    except Exception as e:
        logger.error("Ошибка при освобождении слота мастера для заявки #%s: %s", appeal_id, e)
    logger.info("Заявка #%s успешно отменена (слот мастера освобожден)", appeal_id)
    return appeal


def get_all_appeals() -> list[Appeal]:
    """Получение списка всех заявок, отсортированных по дате создания."""
    return sorted(_appeals.values(), key=lambda a: a.created_at, reverse=True)


def _persist() -> None:
    """Сохранение всех заявок в файл JSON."""
    try:
        _appeals_file.parent.mkdir(parents=True, exist_ok=True)
        data = [appeal.to_dict() for appeal in _appeals.values()]
        atomic_write_text(_appeals_file, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error("Не удалось сохранить заявки в файл %s: %s", _appeals_file, e)


def _load() -> None:
    """Загрузка заявок из файла JSON при старте сервиса."""
    global _appeals
    if not _appeals_file.exists():
        return
    try:
        with open(_appeals_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return
            data = json.loads(content)
        _appeals.clear()
        items = data.values() if isinstance(data, dict) else data
        for item in items:
            appeal = Appeal.from_dict(item)
            _appeals[appeal.id] = appeal
            if appeal.status in (AppealStatus.SCHEDULED, AppealStatus.IN_PROGRESS) and appeal.window_id:
                try:
                    from src.scheduler.store import book_window
                    book_window(appeal.window_id, appeal.id)
                except Exception:
                    pass
    except Exception as e:
        logger.error("Не удалось загрузить заявки из файла %s: %s", _appeals_file, e)


# Попытка загрузить заявки при импорте модуля
_load()
