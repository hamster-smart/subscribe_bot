from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

import database as db
from keyboards.inline import main_menu_kb, back_kb
from config import config

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )

    # Проверить deep link — промокод (?start=PROMO)
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""
    if args and not args.startswith("paid_"):
        promo_code = args.upper()
        promo = await db.get_promo(promo_code)
        if promo:
            user_uses = await db.get_user_promo_uses(message.from_user.id, promo_code)
            max_per_user = promo["max_uses_per_user"] if promo["max_uses_per_user"] else 1
            if user_uses >= max_per_user:
                support = await db.get_setting("support_enabled", "1")
                await message.answer(
                    f"❌ Промокод <b>{promo_code}</b> уже использован.",
                    parse_mode="HTML",
                    reply_markup=main_menu_kb(support == "1")
                )
                return

            await state.update_data(promo_code=promo_code)

            # Если промокод привязан к конкретному тарифу — сразу к нему
            if promo["tariff_id"]:
                tariff = await db.get_tariff(promo["tariff_id"])
                # chat_index: из промокода → из тарифа → 0
                chat_index = promo.get("chat_index")
                if chat_index is None:
                    chat_index = tariff.get("chat_index", 0) if tariff else 0
                if chat_index is None:
                    chat_index = 0

                if tariff:
                    price = tariff["price"]
                    if promo["discount_pct"]:
                        price = price * (1 - promo["discount_pct"] / 100)
                    await state.update_data(
                        promo_code=promo_code,
                        selected_tariff_id=tariff["id"],
                        chat_index=chat_index,
                        final_price=price
                    )
                    disc_text = f" (-{promo['discount_pct']}%)" if promo["discount_pct"] else " (бесплатно)" if price == 0 else ""
                    chat_name = config.get_channel_name(chat_index)

                    if price == 0:
                        # 100% скидка — создаём запись, выдаём доступ, сжигаем промокод
                        payment_id = await db.create_payment(
                            user_id=message.from_user.id,
                            tariff_id=tariff["id"],
                            amount=0,
                            method="promo_100",
                            promo_code=promo_code,
                            chat_index=chat_index
                        )
                        await db.confirm_payment(payment_id, admin_id=0)
                        await db.create_subscription(message.from_user.id, tariff["id"], tariff["days"], chat_index)
                        # Помечаем использованным только после успешной активации
                        await db.use_promo(promo_code)

                        from services.channel import grant_access
                        from datetime import datetime, timedelta
                        link = await grant_access(message.bot, message.from_user.id, chat_index)
                        expires = datetime.utcnow() + timedelta(days=tariff["days"])

                        await message.answer(
                            f"🎟 Промокод <b>{promo_code}</b> активирован! (бесплатный доступ)\n\n"
                            f"✅ <b>Доступ выдан!</b>\n"
                            f"📺 Канал: {chat_name}\n"
                            f"🔗 Ссылка: {link}\n"
                            f"📅 До: {expires.strftime('%d.%m.%Y')}",
                            parse_mode="HTML"
                        )
                        await state.clear()
                        return

                    # Частичная скидка — показываем методы оплаты
                    methods = await db.get_payment_methods()
                    currencies = list(dict.fromkeys(m["currency"] for m in methods))

                    from handlers.chat_select import currency_kb, payment_methods_kb
                    if len(currencies) == 1:
                        currency_methods = await db.get_payment_methods(currencies[0])
                        await message.answer(
                            f"🎟 Промокод <b>{promo_code}</b>{disc_text}\n\n"
                            f"📦 {tariff['name']} → {chat_name}\n"
                            f"💰 {price:.0f} {tariff['currency'] or 'RUB'}\n\n"
                            f"Выберите способ оплаты:",
                            reply_markup=payment_methods_kb(tariff["id"], chat_index, currencies[0], currency_methods),
                            parse_mode="HTML"
                        )
                    else:
                        await message.answer(
                            f"🎟 Промокод <b>{promo_code}</b>{disc_text}\n\n"
                            f"📦 {tariff['name']} → {chat_name}\n"
                            f"💰 {price:.0f} {tariff['currency'] or 'RUB'}\n\n"
                            f"Выберите валюту оплаты:",
                            reply_markup=currency_kb(tariff["id"], chat_index, currencies),
                            parse_mode="HTML"
                        )
                    return

            # Промокод без тарифа — показать меню
            await message.answer(
                f"🎟 Промокод <b>{promo_code}</b> активирован! Скидка применится при выборе тарифа.",
                parse_mode="HTML"
            )
            return

    welcome = await db.get_setting("welcome_text", "👋 Приветствуем! Выберите тариф и получите доступ к чату.")
    support = await db.get_setting("support_enabled", "1")

    from datetime import datetime
    lines = []
    for idx in range(2):
        sub = await db.get_active_subscription(message.from_user.id, chat_index=idx)
        if sub:
            exp = datetime.fromisoformat(sub["expires_at"])
            chat_name = config.get_channel_name(idx)
            lines.append(f"✅ <b>{chat_name}</b>: до {exp.strftime('%d.%m.%Y')}")

    text = welcome + ("\n\n" + "\n".join(lines) if lines else "")
    await message.answer(text, reply_markup=main_menu_kb(support == "1"), parse_mode="HTML")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    welcome = await db.get_setting("welcome_text", "👋 Выберите тариф и получите доступ к чату.")
    support = await db.get_setting("support_enabled", "1")

    from datetime import datetime
    lines = []
    for idx in range(2):
        sub = await db.get_active_subscription(call.from_user.id, chat_index=idx)
        if sub:
            exp = datetime.fromisoformat(sub["expires_at"])
            chat_name = config.get_channel_name(idx)
            lines.append(f"✅ <b>{chat_name}</b>: до {exp.strftime('%d.%m.%Y')}")

    text = welcome + ("\n\n" + "\n".join(lines) if lines else "")
    await call.message.edit_text(text, reply_markup=main_menu_kb(support == "1"), parse_mode="HTML")


@router.callback_query(F.data == "my_subscription")
async def cb_my_subscription(call: CallbackQuery):
    from datetime import datetime
    lines = []
    for idx in range(2):
        sub = await db.get_active_subscription(call.from_user.id, chat_index=idx)
        if sub:
            exp = datetime.fromisoformat(sub["expires_at"])
            chat_name = config.get_channel_name(idx)
            lines.append(
                f"📺 <b>{chat_name}</b>\n"
                f"  📦 {sub['tariff_name']}\n"
                f"  📅 До: {exp.strftime('%d.%m.%Y')}\n"
                f"  ⏳ Осталось: {(exp - datetime.utcnow()).days} дн."
            )

    if lines:
        text = "👤 <b>Ваши подписки</b>\n\n" + "\n\n".join(lines)
    else:
        text = "❌ У Вас нет активных подписок.\nВыберите тариф, чтобы получить доступ!"
    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery, state: FSMContext):
    support_enabled = await db.get_setting("support_enabled", "1")
    if support_enabled != "1":
        await call.answer("Поддержка временно недоступна.", show_alert=True)
        return

    from handlers.support import SupportState
    await state.set_state(SupportState.waiting_message)
    await call.message.edit_text(
        "📞 <b>Поддержка</b>\n\n"
        "Опишите свой вопрос — мы ответим в ближайшее время.\n\n"
        "Отправьте сообщение (текст или фото):",
        reply_markup=back_kb("main_menu"),
        parse_mode="HTML"
    )
