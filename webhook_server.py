"""
Запускается ОТДЕЛЬНО от бота для приёма вебхуков от платёжных систем.
Пример: uvicorn webhook_server:app --host 0.0.0.0 --port 8000
"""
import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager

from aiohttp import web
from aiogram import Bot

import database as db
from config import config

logger = logging.getLogger(__name__)
bot: Bot | None = None


async def handle_yukassa_webhook(request: web.Request) -> web.Response:
    """Вебхук от ЮКассы."""
    try:
        body = await request.text()
        data = json.loads(body)

        if data.get("event") != "payment.succeeded":
            return web.Response(status=200)

        payment_data = data.get("object", {})
        metadata = payment_data.get("metadata", {})
        payment_db_id = metadata.get("payment_db_id")

        if not payment_db_id:
            logger.warning("No payment_db_id in yukassa webhook")
            return web.Response(status=200)

        from handlers.payment import process_payment_confirmed
        await process_payment_confirmed(int(payment_db_id), bot)

    except Exception as e:
        logger.error(f"YuKassa webhook error: {e}")

    return web.Response(status=200)


async def handle_tinkoff_webhook(request: web.Request) -> web.Response:
    """Вебхук от Тинькофф."""
    try:
        body = await request.text()
        data = json.loads(body)

        # Verify token
        token_received = data.pop("Token", "")
        check_data = {**data, "Password": config.TINKOFF_SECRET_KEY}
        token_str = "".join(str(v) for k, v in sorted(check_data.items())
                            if isinstance(v, (str, int)))
        expected_token = hashlib.sha256(token_str.encode()).hexdigest()

        if token_received != expected_token:
            logger.warning("Invalid Tinkoff token")
            return web.Response(status=200)

        if data.get("Status") != "CONFIRMED":
            return web.Response(status=200)

        payment_db_id = int(data.get("OrderId", 0))
        if not payment_db_id:
            return web.Response(status=200)

        from handlers.payment import process_payment_confirmed
        await process_payment_confirmed(payment_db_id, bot)

    except Exception as e:
        logger.error(f"Tinkoff webhook error: {e}")

    return web.Response(status=200)


def create_webhook_app(bot_instance: Bot) -> web.Application:
    global bot
    bot = bot_instance
    app = web.Application()
    app.router.add_post("/webhook/yukassa", handle_yukassa_webhook)
    app.router.add_post("/webhook/tinkoff", handle_tinkoff_webhook)
    return app
