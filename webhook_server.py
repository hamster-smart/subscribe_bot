"""
Webhook server для приёма уведомлений от платёжных систем.
Запускается отдельно: uvicorn webhook_server:app --host 0.0.0.0 --port 8000
"""
import hashlib
import json
import logging

from fastapi import FastAPI, Request, Response

from config import config

logger = logging.getLogger(__name__)

app = FastAPI()


async def get_bot():
    from aiogram import Bot
    return Bot(token=config.BOT_TOKEN)


@app.post("/webhook/yukassa")
async def handle_yukassa_webhook(request: Request):
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

@app.post("/webhook/yoomoney")
async def handle_yoomoney_webhook(request: Request):
    try:
        import hmac
        from urllib.parse import parse_qs
        body = await request.body()
        # ЮМани шлёт form-encoded, не JSON
        data = {k: v[0] for k, v in parse_qs(body.decode()).items()}

        # Проверка подписи
        # sha1(type&operation_id&amount&currency&datetime&sender&codepro&secret&label)
        check_str = "&".join([
            data.get("notification_type", ""),
            data.get("operation_id", ""),
            data.get("amount", ""),
            data.get("currency", ""),
            data.get("datetime", ""),
            data.get("sender", ""),
            data.get("codepro", ""),
            config.YOOMONEY_SECRET,
            data.get("label", ""),
        ])
        expected = hashlib.sha1(check_str.encode()).hexdigest()

        # YooMoney в тестовых уведомлениях шлёт поле "sign",
        # в реальных — "sha1_hash". Поддерживаем оба варианта.
        received = data.get("sha1_hash") or data.get("sign", "")

        if not received:
            logger.warning("ЮМани: отсутствует подпись")
            return Response(status_code=401)

        if not hmac.compare_digest(expected, received):
            logger.warning("ЮМани: неверная подпись")
            return Response(status_code=401)

        payment_db_id = data.get("label")
        if not payment_db_id:
            logger.warning("ЮМани: нет label")
            return Response(status_code=200)

        import aiosqlite
        async with aiosqlite.connect(config.DB_PATH) as dbc:
            await dbc.execute(
                "UPDATE payments SET paid_amount=? WHERE id=?",
                (data.get("amount"), int(payment_db_id))
            )
            await dbc.commit()

        bot = await get_bot()
        from handlers.payment import process_payment_confirmed
        await process_payment_confirmed(int(payment_db_id), bot)
        await bot.session.close()
    except Exception as e:
        logger.error(f"YooMoney webhook error: {e}")
    return Response(status_code=200)

@app.post("/webhook/tinkoff")
async def handle_tinkoff_webhook(request: Request):
    try:
        body = await request.body()
        data = json.loads(body)
        token_received = data.pop("Token", "")
        check_data = {**data, "Password": config.TINKOFF_SECRET_KEY}
        token_str = "".join(str(v) for k, v in sorted(check_data.items())
                            if isinstance(v, (str, int)))
        expected_token = hashlib.sha256(token_str.encode()).hexdigest()
        if token_received != expected_token:
            logger.warning("Invalid Tinkoff token")
            return Response(status_code=200)
        if data.get("Status") != "CONFIRMED":
            return Response(status_code=200)
        payment_db_id = int(data.get("OrderId", 0))
        if not payment_db_id:
            return Response(status_code=200)
        bot = await get_bot()
        from handlers.payment import process_payment_confirmed
        await process_payment_confirmed(payment_db_id, bot)
        await bot.session.close()
    except Exception as e:
        logger.error(f"Tinkoff webhook error: {e}")
    return Response(status_code=200)

@app.post("/webhook/nowpayments")
async def handle_nowpayments_webhook(request: Request):
    try:
        import hmac
        body = await request.read()
        sig = request.headers.get("x-nowpayments-sig", "")
        expected = hmac.new(
            config.NOWPAYMENTS_IPN_SECRET.encode(),
            body,
            hashlib.sha512
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            logger.warning("NOWPayments: неверная подпись")
            return Response(status_code=401)
        data = json.loads(body)
        if data.get("payment_status") not in ("finished", "confirmed"):
            return Response(status_code=200)
        payment_db_id = data.get("order_id")
        if not payment_db_id:
            logger.warning("NOWPayments: нет order_id")
            return Response(status_code=200)
        import aiosqlite
        async with aiosqlite.connect(config.DB_PATH) as dbc:
            await dbc.execute(
                "UPDATE payments SET paid_amount=? WHERE id=?",
                (data.get("actually_paid"), int(payment_db_id))
            )
            await dbc.commit()

        bot = await get_bot()
        from handlers.payment import process_payment_confirmed
        await process_payment_confirmed(int(payment_db_id), bot)
        await bot.session.close()
    except Exception as e:
        logger.error(f"NOWPayments webhook error: {e}")
    return Response(status_code=200)
