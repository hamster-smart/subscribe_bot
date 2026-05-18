"""
Webhook server для приёма уведомлений от платёжных систем.
Запускается отдельно: uvicorn webhook_server:app --host 0.0.0.0 --port 8000
"""
import hashlib
import json
import logging

from fastapi import FastAPI, Request, Response

import database as db
from config import config

logger = logging.getLogger(__name__)

app = FastAPI()


async def get_bot():
    from aiogram import Bot
    return Bot(token=config.BOT_TOKEN)


@app.post("/webhook/yukassa")
async def handle_yukassa_webhook(request: Request):
    """Вебхук от ЮКассы."""
    try:
        body = await request.body()
        data = json.loads(body)

        if data.get("event") != "payment.succeeded":
            return Response(status_code=200)

        payment_data = data.get("object", {})
        metadata = payment_data.get("metadata", {})
        payment_db_id = metadata.get("payment_db_id")

        if not payment_db_id:
            logger.warning("No payment_db_id in yukassa webhook")
            return Response(status_code=200)

        bot = await get_bot()
        from handlers.payment import process_payment_confirmed
        await process_payment_confirmed(int(payment_db_id), bot)
        await bot.session.close()

    except Exception as e:
        logger.error(f"YuKassa webhook error: {e}")

    return Response(status_code=200)


@app.post("/webhook/tinkoff")
async def handle_tinkoff_webhook(request: Request):
    """Вебхук от Тинькофф."""
    try:
        body = await request.body()
        data = json.loads(body)

        # Verify token
        token_received = data.pop("Token", "")
        check_data = {**data, "Password": config.TINKOFF_SECRET_KEY}
        token_str = "".join(str(v) for k, v in sorted(check_data.items())
                            if isinstance(v, (str, int)))
        expected_token = hashlib.sha256(token_str.encode()).hexdigest()

        if token_received != expected_token:
            logger.warning("Invalid Tinkoff token")
            return Response(status_code=200)

