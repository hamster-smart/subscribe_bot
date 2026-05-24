from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config

import database as db
from keyboards.inline import tariffs_kb, tariff_detail_kb, back_kb

router = Router()


class PromoState(StatesGroup):
    waiting_for_promo = State()
    waiting_for_promo_for_tariff = State()


@router.callback_query(F.data.startswith("select_tariff:"))
async def cb_select_tariff(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split(":")[1])
    tariff = await db.get_tariff(tariff_id)
    if not tariff:
        await call.answer("Тариф не найден", show_alert=True)
        return

    data = await state.get_data()
    promo_code = data.get("promo_code")
    price = tariff["price"]
    promo_text = ""

    if promo_code:
        promo = await db.get_promo(promo_code)
        if promo:
            if promo["discount_pct"]:
                price = price * (1 - promo["discount_pct"] / 100)
                promo_text = f"\n🎟 Промокод <b>{promo_code}</b>: -{promo['discount_pct']}%"
            elif promo["discount_rub"]:
                price = max(0, price - promo["discount_rub"])
                promo_text = f"\n🎟 Промокод <b>{promo_code}</b>: -{promo['discount_rub']:.0f}₽"

    text = (
        f"📦 <b>{tariff['name']}</b>\n\n"
        f"📝 {tariff['description']}\n"
        f"⏳ Срок: <b>{tariff['days']} дней</b>\n"
        f"💰 Стоимость: <b>{price:.0f} ₽</b>{promo_text}\n\n"
        f"Выберите способ оплаты:"
    )
    await state.update_data(selected_tariff_id=tariff_id, final_price=price)
    await call.message.edit_text(
        text,
        reply_markup=tariff_detail_kb(tariff_id, has_promo=bool(promo_code)),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "enter_promo")
async def cb_enter_promo(call: CallbackQuery, state: FSMContext):
    await state.set_state(PromoState.waiting_for_promo)
    await call.message.edit_text(
        "🎟 Введите промокод:",
        reply_markup=back_kb()
    )


@router.callback_query(F.data.startswith("promo_for:"))
async def cb_promo_for_tariff(call: CallbackQuery, state: FSMContext):
    tariff_id = int(call.data.split(":")[1])
    await state.update_data(promo_tariff_id=tariff_id)
    await state.set_state(PromoState.waiting_for_promo_for_tariff)
    await call.message.edit_text(
        "🎟 Введите промокод для этого тарифа:",
        reply_markup=back_kb(f"select_tariff:{tariff_id}")
    )


from aiogram.types import Message


@router.message(PromoState.waiting_for_promo)
async def handle_promo_input(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    promo = await db.get_promo(code)
    if not promo:
        await message.answer(
            "❌ Промокод недействителен или уже использован.",
            reply_markup=back_kb()
        )
        await state.set_state(None)
        return

    user_uses = await db.get_user_promo_uses(message.from_user.id, code)
    max_per_user = promo["max_uses_per_user"] if promo["max_uses_per_user"] else 1
    if user_uses >= max_per_user:
        await message.answer(
            f"❌ Промокод <b>{code}</b> уже использован.",
            parse_mode="HTML",
            reply_markup=back_kb()
        )
        await state.set_state(None)
        return

    await state.update_data(promo_code=code)

    # Промокод привязан к тарифу — сразу к нему, без выбора
    if promo["tariff_id"]:
        tariff = await db.get_tariff(promo["tariff_id"])
        if tariff:
            chat_index = promo["chat_index"]
            if chat_index is None:
                chat_index = tariff["chat_index"] if tariff["chat_index"] is not None else 0

            price = tariff["price"]
            if promo["discount_pct"]:
                price = price * (1 - promo["discount_pct"] / 100)
            elif promo["discount_rub"]:
                price = max(0, price - promo["discount_rub"])

            await state.update_data(
                selected_tariff_id=tariff["id"],
                chat_index=chat_index,
                final_price=price
            )

            chat_name = config.get_channel_name(chat_index)
            disc_text = f" (-{promo['discount_pct']}%)" if promo["discount_pct"] else " (бесплатно)" if price == 0 else ""

            if price == 0:
                # 100% скидка — выдаём доступ сразу
                payment_id = await db.create_payment(
                    user_id=message.from_user.id,
                    tariff_id=tariff["id"],
                    amount=0,
                    method="promo_100",
                    promo_code=code,
                    chat_index=chat_index
                )
                await db.confirm_payment(payment_id, admin_id=0)
                await db.create_subscription(message.from_user.id, tariff["id"], tariff["days"], chat_index)
                await db.use_promo(code)

                from services.channel import grant_access
                from datetime import datetime, timedelta
                link = await grant_access(message.bot, message.from_user.id, chat_index)
                expires = datetime.utcnow() + timedelta(days=tariff["days"])

                await message.answer(
                    f"🎟 Промокод <b>{code}</b> активирован!{disc_text}\n\n"
                    f"✅ <b>Доступ выдан!</b>\n"
                    f"📺 Канал: {chat_name}\n"
                    f"🔗 Ссылка: {link}\n"
                    f"📅 До: {expires.strftime('%d.%m.%Y')}",
                    parse_mode="HTML"
                )
                await state.clear()
                
                # ─── Уведомление администраторам ──────────────────────────
                if not tariff.get("is_trial"):
                    import aiosqlite
                    async with aiosqlite.connect(config.DB_PATH) as dbc:
                        dbc.row_factory = aiosqlite.Row
                        async with dbc.execute(
                            "SELECT username, full_name FROM users WHERE user_id = ?",
                            (message.from_user.id,)
                        ) as cur:
                            user_row = await cur.fetchone()

                    username = user_row["username"] if user_row and user_row["username"] else None
                    full_name = user_row["full_name"] if user_row else str(message.from_user.id)
                    currency = tariff.get("currency") or "RUB"
                    currency_symbols = {"RUB": "₽", "EUR": "€", "USD": "$"}
                    symbol = currency_symbols.get(currency, currency)

                    admin_text = (
                        f"🆕 <b>Новая подписка!</b>\n\n"
                        f"👤 {full_name}"
                        + (f" (@{username})" if username else "")
                        + f"\n🆔 <code>{message.from_user.id}</code>\n"
                        f"📦 Тариф: <b>{tariff['name']}</b>\n"
                        f"📺 Канал: {chat_name}\n"
                        f"💵 Сумма: <b>0 {symbol}</b>\n"
                        f"🎟 Промокод: {code}\n"
                        f"📅 До: {expires.strftime('%d.%m.%Y')}"
                    )
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
                        except Exception:
                            pass
                return

            # Частичная скидка — к методам оплаты
            from handlers.chat_select import currency_kb, payment_methods_kb
            methods = await db.get_payment_methods()
            currencies = list(dict.fromkeys(m["currency"] for m in methods))

            if len(currencies) == 1:
                currency_methods = await db.get_payment_methods(currencies[0])
                await message.answer(
                    f"🎟 Промокод <b>{code}</b>{disc_text}\n\n"
                    f"📦 {tariff['name']} → {chat_name}\n"
                    f"💰 {price:.0f} {tariff['currency'] or 'RUB'}\n\n"
                    f"Выберите способ оплаты:",
                    reply_markup=payment_methods_kb(tariff["id"], chat_index, currencies[0], currency_methods),
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    f"🎟 Промокод <b>{code}</b>{disc_text}\n\n"
                    f"📦 {tariff['name']} → {chat_name}\n"
                    f"💰 {price:.0f} {tariff['currency'] or 'RUB'}\n\n"
                    f"Выберите валюту оплаты:",
                    reply_markup=currency_kb(tariff["id"], chat_index, currencies),
                    parse_mode="HTML"
                )
            await state.set_state(None)
            return

    # Промокод без привязки к тарифу — показать все тарифы
    discount_str = (
        f"-{promo['discount_pct']}%" if promo["discount_pct"]
        else f"-{promo['discount_rub']:.0f}₽"
    )
    await message.answer(
        f"✅ Промокод <b>{code}</b> принят! Скидка: <b>{discount_str}</b>\n\n"
        f"Теперь выберите тариф:",
        reply_markup=tariffs_kb(await db.get_tariffs()),
        parse_mode="HTML"
    )
    await state.set_state(None)


@router.message(PromoState.waiting_for_promo_for_tariff)
async def handle_promo_for_tariff(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    data = await state.get_data()
    tariff_id = data.get("promo_tariff_id")
    promo = await db.get_promo(code)
    if promo:
        await state.update_data(promo_code=code)
        from aiogram.types import CallbackQuery as CQ
        # Re-show tariff with promo applied
        tariff = await db.get_tariff(tariff_id)
        price = tariff["price"]
        if promo["discount_pct"]:
            price = price * (1 - promo["discount_pct"] / 100)
            promo_text = f"\n🎟 Промокод <b>{code}</b>: -{promo['discount_pct']}%"
        else:
            price = max(0, price - promo["discount_rub"])
            promo_text = f"\n🎟 Промокод <b>{code}</b>: -{promo['discount_rub']:.0f}₽"

        await state.update_data(selected_tariff_id=tariff_id, final_price=price)
        text = (
            f"📦 <b>{tariff['name']}</b>\n\n"
            f"📝 {tariff['description']}\n"
            f"⏳ Срок: <b>{tariff['days']} дней</b>\n"
            f"💰 Стоимость: <b>{price:.0f} ₽</b>{promo_text}\n\n"
            f"Выберите способ оплаты:"
        )
        await message.answer(text, reply_markup=tariff_detail_kb(tariff_id, has_promo=True), parse_mode="HTML")
    else:
        await message.answer(
            "❌ Промокод недействителен.",
            reply_markup=back_kb(f"select_tariff:{tariff_id}")
        )
    await state.set_state(None)
