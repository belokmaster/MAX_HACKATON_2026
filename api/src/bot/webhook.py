from fastapi import APIRouter, Header, HTTPException, BackgroundTasks, Request
from src.bot.dispatcher import dispatch_update
from src.config import get_settings

router = APIRouter()

@router.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_max_bot_api_secret: str = Header(..., alias="X-Max-Bot-Api-Secret")
):
    """Обработчик входящих событий вебхука от платформы MAX."""
    settings = get_settings()
    if x_max_bot_api_secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Неверный секретный ключ вебхука")
    
    update = await request.json()
    background_tasks.add_task(dispatch_update, update)
    return {"ok": True}
