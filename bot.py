import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config
from database import init_db
import database as db
from handlers import start, subscription, payment, admin, settings, chat_select, join_request, chat_member
from services.scheduler import setup_scheduler
from middlewares.ban_check import BanCheckMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Init DB
    await init_db()

    # Middlewares
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())

    # Register routers
    dp.include_router(start.router)
    dp.include_router(subscription.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    dp.include_router(settings.router)
    dp.include_router(chat_select.router)
    dp.include_router(join_request.router)
    dp.include_router(chat_member.router)

    # Scheduler
    scheduler = AsyncIOScheduler()
    setup_scheduler(scheduler, bot)
    scheduler.start()

    me = await bot.get_me()
    await db.set_setting("bot_username", me.username)
    logger.info("Bot started!")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_join_request", "chat_member"])


if __name__ == "__main__":
    asyncio.run(main())
