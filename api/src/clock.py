"""Единое «текущее время» сервиса: московское (UTC+3), независимо от часового пояса контейнера."""
from datetime import date, datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))


def now_msk() -> datetime:
    """Текущее время по Москве без tzinfo: формат isoformat() совместим с уже сохранёнными заявками."""
    return datetime.now(MSK).replace(tzinfo=None)


def today_msk() -> date:
    return now_msk().date()
