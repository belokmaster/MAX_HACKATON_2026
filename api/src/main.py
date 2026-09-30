from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Добавляем директории 'src' и корень в sys.path для корректных импортов
_SRC_DIR = Path(__file__).resolve().parent
_APP_DIR = _SRC_DIR.parent
for _dir in (_SRC_DIR, _APP_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.bot.client import MaxBotClient
from src.bot import dispatcher
from src.bot.webhook import router as webhook_router
from src.appeals.router import router as appeals_router
from src.webapp.router import router as webapp_router
from src.conversation import store as conv_store
from src.appeals import service as appeal_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Загрузка конфигурации
    settings = get_settings()

    # 2. Инициализация хранилища диалогов
    conv_store.configure(settings.USERS_FILE)

    # 3. Инициализация сервиса заявок
    appeal_service.configure(settings.APPEALS_FILE)

    # 4. Загрузка существующих заявок из файла
    appeal_service._load()

    # 5. Создание клиента MaxBotClient в контексте приложения
    bot_client = MaxBotClient()
    app.state.bot_client = bot_client
    await bot_client.__aenter__()

    # 5.1. Получение и логирование информации о боте (/me)
    try:
        me_info = await bot_client.get_me()
        if me_info:
            logger.info("Информация о боте (/me): %s", me_info)
        else:
            logger.warning("Не удалось получить информацию о боте (/me): пустой ответ")
    except Exception as e:
        logger.error("Ошибка при запросе информации о боте (/me): %s", e)

    # 6. Передача клиента в диспетчер событий
    dispatcher.set_client(app.state.bot_client)

    # 7. Регистрация вебхука в платформе MAX
    try:
        logger.info("Регистрация вебхука: %s", settings.WEBHOOK_URL)
        if settings.BOT_TOKEN and settings.WEBHOOK_URL and "your-domain" not in settings.WEBHOOK_URL:
            await bot_client.set_webhook(settings.WEBHOOK_URL, settings.WEBHOOK_SECRET)
        else:
            logger.warning("WEBHOOK_URL не задан — вебхук не регистрируется (локальный режим)")
    except Exception as e:
        logger.error("Не удалось зарегистрировать вебхук: %s", e)

    # 8. Установка меню команд бота (только публичные команды, /admin не показываем)
    try:
        logger.info("Установка списка команд бота")
        await bot_client.set_commands([
            {"name": "start", "description": "Главное меню"},
            {"name": "help", "description": "Справка и контакты"},
            {"name": "status", "description": "Мои заявки"},
        ])
    except Exception as e:
        logger.error("Не удалось установить команды бота: %s", e)

    yield

    # При завершении работы: закрытие сессии клиента бота
    logger.info("Завершение работы клиента бота...")
    try:
        await bot_client.__aexit__(None, None, None)
    except Exception as e:
        logger.error("Ошибка при закрытии клиента бота: %s", e)


app = FastAPI(
    title="MAX ЖКХ Бот API",
    lifespan=lifespan,
)

# Middleware CORS (разрешение запросов для WebApp и локальной разработки)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение модулей маршрутизации
app.include_router(webhook_router)
app.include_router(appeals_router)
app.include_router(webapp_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
