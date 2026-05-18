from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta

import database as db
from config import config
from keyboards.inline import manual_payment_kb, after_screenshot_kb, back_kb, admin_payment_kb
from services.channel import grant_access

router = Router()


class PaymentState(StatesGroup):
    waiting_screenshot = State()


# ─── ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: выдача доступа по 100% промокоду ────────────────

async def _grant_free_access(call: CallbackQuery, state: FSMContext, tariff: dict):
    data = await state.get_data()
    promo_code = data.get("promo_code")
    chat_index = data.get("chat_index", 0)

    payment_id = await db.create_payment(
        user_id=call.from_user.id,
        tariff_id=tariff["id"],
        amount=0,
        method="promo_100",
        promo_code=promo_code,
        chat_index=chat_index
    )
    await db.confirm_payment(payment_id, admin_id=0)
    await db.create_subscription(
        call.from_user.id,
        tariff["id"],
        tariff["days"],
        chat_index
    )

    if promo_code:
        await db.use_promo(promo_code)

    link = await grant_access(call.bot, call.from_user.id, chat_index)
    expires = datetime.utcnow() + timedelta(days=tariff["days"])

    await call.message.edit_text(
        f"🎉 <b>Промокод активирован — доступ открыт!</b>\n\n"
        f"📦 Тариф: <b>{tariff['name']}</b>\n"
        f"🔗 Ссылка для входа: {link}\n"
        f"📅 Действует до: {expires.strftime('%d.%m.%Y')}",
        parse_mode="HTML"
    )
    await state.clear()


# ─── MANUAL PAYMENT ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_manual:"))
async def cb_pay_manual(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split(":")[1])
    tariff = await db.get_tariff(tariff_id)
    data = await state.get_data()
    promo_code = data.get("promo_code")
    chat_index = data.get("chat_index", tariff.get("chat_index", 0) if tariff else 0)
    if chat_index is None:
        chat_index = 0
    final_price = data.get("final_price", tariff["price"])

    # При 100% скидке — сразу выдаём доступ, без оплаты
    if final_price == 0:
        await _grant_free_access(call, state, tariff)
        return

    payment_id = await db.create_payment(
        user_id=call.from_user.id,
        tariff_id=tariff_id,
        amount=final_price,
        method="manual",
        promo_code=promo_code,
        chat_index=chat_index
    )
    # Помечаем промокод использованным после создания платежа
    if promo_code:
        await db.use_promo(promo_code)

    # Реквизиты хранятся в БД
    payment_details = await db.get_setting("payment_details", "Реквизиты не настроены — обратитесь к администратору.")

    text = (
        f"💳 <b>Ручная оплата</b>\n\n"
        f"📦 Тариф: <b>{tariff['name']}</b>\n"
        f"💰 Сумма: <b>{final_price:.0f} ₽</b>\n\n"
        f"<b>Реквизиты для перевода:</b>\n"
        f"{payment_details}\n\n"
        f"После оплаты нажмите кнопку ниже и отправьте квитанцию/скриншот."
    )
    await state.update_data(current_payment_id=payment_id)
    await call.message.edit_text(text, reply_markup=manual_payment_kb(payment_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("send_screenshot:"))
async def cb_send_screenshot(call: CallbackQuery, state: FSMContext):
    payment_id = int(call.data.split(":")[1])
    await state.update_data(current_payment_id=payment_id)
    await state.set_state(PaymentState.waiting_screenshot)
    await call.message.edit_text(
        "📷 Пришлите квитанцию/скриншот оплаты (фото):",
        reply_markup=back_kb("main_menu")
    )


@router.message(PaymentState.waiting_screenshot, F.photo)
async def handle_screenshot(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    payment_id = data.get("current_payment_id")
    if not payment_id:
        await message.answer("❌ Ошибка. Начните заново: /start")
        return

    file_id = message.photo[-1].file_id
    await db.attach_screenshot(payment_id, file_id)

    await message.answer(
        "✅ Квитанция получена! Ожидайте подтверждения от администратора.\n"
        "Обычно это занимает от нескольких минут до нескольких часов.",
        reply_markup=back_kb()
    )

    # Уведомляем администраторов
    payment = await db.get_payment(payment_id)
    tariff = await db.get_tariff(payment["tariff_id"])
    user = message.from_user

    # chat_index: из платежа → из тарифа → 0
    chat_index = payment.get("chat_index")
    if chat_index is None:
        chat_index = tariff.get("chat_index", 0)
    chat_name = config.get_channel_name(chat_index)

    admin_text = (
        f"💰 <b>Новая оплата #{payment_id}</b>\n\n"
        f"👤 Пользователь: {user.full_name} (@{user.username or 'нет'})\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📦 Тариф: {tariff['name']}\n"
        f"📺 Канал: {chat_name}\n"
        f"💵 Сумма: {payment['amount']:.0f} ₽\n"
        f"💳 Метод: Ручной перевод"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo=file_id,
                caption=admin_text,
                reply_markup=admin_payment_kb(payment_id),
                parse_mode="HTML"
            )
        except Exception:
            pass

    await state.set_state(None)


@router.callback_query(F.data.startswith("awaiting_confirm:"))
async def cb_awaiting_confirm(call: CallbackQuery):
    await call.answer("⏳ Ожидаем подтверждения администратора. Мы уведомим Вас.", show_alert=True)


# ─── ONLINE PAYMENT (ЮКасса / Тинькофф) ────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_online:"))
async def cb_pay_online(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split(":")[1])
    tariff = await db.get_tariff(tariff_id)
    data = await state.get_data()
    promo_code = data.get("promo_code")
    chat_index = data.get("chat_index", tariff.get("chat_index", 0) if tariff else 0)
    if chat_index is None:
        chat_index = 0
    final_price = data.get("final_price", tariff["price"])

    # При 100% скидке — сразу выдаём доступ, без оплаты
    if final_price == 0:
        await _grant_free_access(call, state, tariff)
        return

    if config.YUKASSA_ENABLED:
        await _pay_yukassa(call, tariff, final_price, promo_code, chat_index, state)
    elif config.TINKOFF_ENABLED:
        await _pay_tinkoff(call, tariff, final_price, promo_code, chat_index, state)
    else:
        await call.answer(
            "Онлайн-оплата временно недоступна. Используйте ручной перевод.",
            show_alert=True
        )


async def _pay_yukassa(call: CallbackQuery, tariff, amount: float,
                       promo_code: str | None, chat_index: int, state: FSMContext):
    """Создать платёж в ЮКассе и вернуть ссылку пользователю."""
    try:
        from yookassa import Configuration, Payment
        import uuid

        Configuration.account_id = config.YUKASSA_SHOP_ID
        Configuration.secret_key = config.YUKASSA_SECRET_KEY

        payment_db_id = await db.create_payment(
            user_id=call.from_user.id,
            tariff_id=tariff["id"],
            amount=amount,
            method="yukassa",
            promo_code=promo_code,
            chat_index=chat_index
        )
        if promo_code:
            await db.use_promo(promo_code)

        payment = Payment.create({
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{(await call.bot.get_me()).username}?start=paid_{payment_db_id}"
            },
            "capture": True,
            "description": f"Подписка: {tariff['name']}",
            "metadata": {
                "payment_db_id": payment_db_id,
                "user_id": call.from_user.id
            }
        }, uuid.uuid4())

        async with __import__("aiosqlite").connect(__import__("config").config.DB_PATH) as dbc:
            await dbc.execute(
                "UPDATE payments SET external_id = ? WHERE id = ?",
                (payment.id, payment_db_id)
            )
            await dbc.commit()

        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="💳 Перейти к оплате", url=payment.confirmation.confirmation_url))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))

        await call.message.edit_text(
            f"💳 <b>Оплата через ЮКассу</b>\n\n"
            f"📦 {tariff['name']} — {amount:.0f} ₽\n\n"
            f"Нажмите кнопку для перехода к оплате.\n"
            f"После оплаты вернитесь в бот — доступ откроется автоматически.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except Exception as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)


async def _pay_tinkoff(call: CallbackQuery, tariff, amount: float,
                       promo_code: str | None, chat_index: int, state: FSMContext):
    """Создать платёж в Тинькофф и вернуть ссылку пользователю."""
    try:
        import hashlib
        import aiohttp

        payment_db_id = await db.create_payment(
            user_id=call.from_user.id,
            tariff_id=tariff["id"],
            amount=amount,
            method="tinkoff",
            promo_code=promo_code,
            chat_index=chat_index
        )
        if promo_code:
            await db.use_promo(promo_code)

        amount_kopecks = int(amount * 100)
        payload = {
            "TerminalKey": config.TINKOFF_TERMINAL_KEY,
            "Amount": amount_kopecks,
            "OrderId": str(payment_db_id),
            "Description": f"Подписка: {tariff['name']}",
            "DATA": {"UserId": str(call.from_user.id)},
        }
        token_data = {**payload, "Password": config.TINKOFF_SECRET_KEY}
        token_str = "".join(str(v) for k, v in sorted(token_data.items())
                            if isinstance(v, (str, int)))
        payload["Token"] = hashlib.sha256(token_str.encode()).hexdigest()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://securepay.tinkoff.ru/v2/Init",
                json=payload
            ) as resp:
                data = await resp.json()

        if data.get("Success"):
            pay_url = data["PaymentURL"]
            async with __import__("aiosqlite").connect(config.DB_PATH) as dbc:
                await dbc.execute(
                    "UPDATE payments SET external_id = ? WHERE id = ?",
                    (data["PaymentId"], payment_db_id)
                )
                await dbc.commit()

            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(text="💳 Перейти к оплате", url=pay_url))
            builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))

            await call.message.edit_text(
                f"💳 <b>Оплата через Тинькофф</b>\n\n"
                f"📦 {tariff['name']} — {amount:.0f} ₽\n\n"
                f"Нажмите кнопку для перехода к оплате.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            await call.answer(f"Ошибка Тинькофф: {data.get('Message')}", show_alert=True)

    except Exception as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)


# ─── WEBHOOK для автоматического подтверждения ────────────────────────────────

async def process_payment_confirmed(payment_db_id: int, bot: Bot):
    """Вызывается вебхуком после успешной онлайн-оплаты."""
    payment = await db.get_payment(payment_db_id)
    if not payment or payment["status"] == "confirmed":
        return

    await db.confirm_payment(payment_db_id, admin_id=0)
    tariff = await db.get_tariff(payment["tariff_id"])

    # chat_index: из платежа → из тарифа → 0
    chat_index = payment.get("chat_index")
    if chat_index is None:
        chat_index = tariff.get("chat_index", 0)
    if chat_index is None:
        chat_index = 0

    await db.create_subscription(payment["user_id"], payment["tariff_id"], tariff["days"], chat_index)

    link = await grant_access(bot, payment["user_id"], chat_index)
    expires = datetime.utcnow() + timedelta(days=tariff["days"])

    await bot.send_message(
        payment["user_id"],
        f"✅ <b>Оплата подтверждена!</b>\n\n"
        f"📦 Тариф: {tariff['name']}\n"
        f"🔗 Ссылка на канал: {link}\n"
        f"📅 Действует до: {expires.strftime('%d.%m.%Y')}",
        parse_mode="HTML"
    )
