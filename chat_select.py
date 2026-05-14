"""
Заменяет старый flow выбора тарифа:
  /start → выбор чата → выбор тарифа → выбор валюты → выбор метода оплаты → оплата
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

import database as db
from config import config

router = Router()


# ─── KEYBOARDS ─────────────────────────────────────────────────────────────────

def chats_kb() -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=config.CHANNEL_1_NAME,
        callback_data="choose_chat:0"
    ))
    builder.row(InlineKeyboardButton(
        text=config.CHANNEL_2_NAME,
        callback_data="choose_chat:1"
    ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return builder.as_markup()


def currency_kb(tariff_id: int, chat_index: int, currencies: list[str]) -> object:
    builder = InlineKeyboardBuilder()
    labels = {"RUB": "🇷🇺 Рубли (RUB)", "EUR": "🇪🇺 Евро (EUR)", "USD": "🇺🇸 Доллары (USD)"}
    for cur in currencies:
        builder.row(InlineKeyboardButton(
            text=labels.get(cur, cur),
            callback_data=f"choose_currency:{tariff_id}:{chat_index}:{cur}"
        ))
    builder.row(InlineKeyboardButton(
        text="◀️ Назад",
        callback_data=f"choose_chat:{chat_index}"
    ))
    return builder.as_markup()


def payment_methods_kb(tariff_id: int, chat_index: int,
                       currency: str, methods: list) -> object:
    builder = InlineKeyboardBuilder()
    for m in methods:
        builder.row(InlineKeyboardButton(
            text=m["name"],
            callback_data=f"choose_method:{tariff_id}:{chat_index}:{currency}:{m['id']}"
        ))
    builder.row(InlineKeyboardButton(
        text="◀️ Назад",
        callback_data=f"select_tariff_chat:{tariff_id}:{chat_index}"
    ))
    return builder.as_markup()


def pay_link_kb(url: str, tariff_id: int, chat_index: int,
                payment_id: int) -> object:
    """Кнопка-ссылка на оплату + кнопка отправки скриншота."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Перейти к оплате", url=url))
    builder.row(InlineKeyboardButton(
        text="📷 Отправить скриншот",
        callback_data=f"send_screenshot:{payment_id}"
    ))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="main_menu"))
    return builder.as_markup()


def pay_text_kb(payment_id: int) -> object:
    """Кнопки для текстовых реквизитов."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📷 Отправить скриншот",
        callback_data=f"send_screenshot:{payment_id}"
    ))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="main_menu"))
    return builder.as_markup()


# ─── HANDLERS ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "show_tariffs")
async def cb_show_tariffs_entry(call: CallbackQuery):
    """Точка входа — сначала выбор чата."""
    await call.message.edit_text(
        "🏠 <b>Выбери канал</b>\n\nК какому каналу хочешь получить доступ?",
        reply_markup=chats_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("choose_chat:"))
async def cb_choose_chat(call: CallbackQuery, state: FSMContext):
    chat_index = int(call.data.split(":")[1])
    await state.update_data(chat_index=chat_index)

    tariffs = await db.get_tariffs()
    # Фильтруем тарифы по chat_index если есть привязка
    chat_tariffs = [t for t in tariffs if t["chat_index"] == chat_index] or tariffs

    if not chat_tariffs:
        await call.answer("Тарифы временно недоступны", show_alert=True)
        return

    used_trial = await db.has_used_trial(call.from_user.id)
    builder = InlineKeyboardBuilder()
    for t in chat_tariffs:
        if t["is_trial"]:
            if used_trial:
                continue  # скрыть пробный если уже использован
            label = f"{t['name']} — Бесплатно"
        else:
            label = f"{t['name']} — {t['price']:.0f} ₽"
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=f"select_tariff_chat:{t['id']}:{chat_index}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="show_tariffs"))

    chat_name = config.get_channel_name(chat_index)
    await call.message.edit_text(
        f"📋 <b>Тарифы для {chat_name}</b>\n\nВыбери план:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("select_tariff_chat:"))
async def cb_select_tariff_chat(call: CallbackQuery, state: FSMContext):
    _, tariff_id, chat_index = call.data.split(":")
    tariff_id, chat_index = int(tariff_id), int(chat_index)

    tariff = await db.get_tariff(tariff_id)
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

    await state.update_data(
        selected_tariff_id=tariff_id,
        chat_index=chat_index,
        final_price=price
    )

    # ── ПРОБНЫЙ ТАРИФ — сразу выдать доступ ──────────────────────────────────
    if tariff["is_trial"]:
        used = await db.has_used_trial(call.from_user.id)
        if used:
            await call.answer(
                "❌ Пробный тариф можно использовать только один раз.",
                show_alert=True
            )
            return
        # Создать бесплатную подписку
        await db.create_subscription(call.from_user.id, tariff_id, tariff["days"])
        from services.channel import grant_access
        from datetime import datetime, timedelta
        link = await grant_access(call.bot, call.from_user.id, chat_index)
        expires = datetime.utcnow() + timedelta(days=tariff["days"])
        chat_name = config.get_channel_name(chat_index)
        await call.message.edit_text(
            f"🎁 <b>Пробный доступ активирован!</b>

"
            f"📺 Канал: {chat_name}
"
            f"🔗 Ссылка: {link}
"
            f"📅 Действует до: <b>{expires.strftime('%d.%m.%Y %H:%M')}</b>

"
            f"После окончания пробного периода выбери платный тариф: /start",
            parse_mode="HTML"
        )
        return
    # ─────────────────────────────────────────────────────────────────────────

    # Собрать доступные валюты из методов оплаты
    methods = await db.get_payment_methods()
    currencies = list(dict.fromkeys(m["currency"] for m in methods))  # уникальные, по порядку

    chat_name = config.get_channel_name(chat_index)
    text = (
        f"📦 <b>{tariff['name']}</b> → {chat_name}\n\n"
        f"📝 {tariff['description']}\n"
        f"⏳ Срок: <b>{tariff['days']} дней</b>\n"
        f"💰 Стоимость: <b>{price:.0f} ₽</b>{promo_text}\n\n"
        f"В какой валюте оплатишь?"
    )

    if len(currencies) == 1:
        # Только одна валюта — сразу к методам
        currency_methods = await db.get_payment_methods(currencies[0])
        await call.message.edit_text(
            text + f"\n\nВыбери способ оплаты ({currencies[0]}):",
            reply_markup=payment_methods_kb(tariff_id, chat_index, currencies[0], currency_methods),
            parse_mode="HTML"
        )
    else:
        await call.message.edit_text(
            text,
            reply_markup=currency_kb(tariff_id, chat_index, currencies),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("choose_currency:"))
async def cb_choose_currency(call: CallbackQuery):
    _, tariff_id, chat_index, currency = call.data.split(":")
    tariff_id, chat_index = int(tariff_id), int(chat_index)

    methods = await db.get_payment_methods(currency)
    if not methods:
        await call.answer("Методы оплаты не настроены", show_alert=True)
        return

    tariff = await db.get_tariff(tariff_id)
    await call.message.edit_text(
        f"💱 <b>Оплата в {currency}</b>\n\n"
        f"Тариф: {tariff['name']}\n"
        f"Выбери способ:",
        reply_markup=payment_methods_kb(tariff_id, chat_index, currency, methods),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("choose_method:"))
async def cb_choose_method(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    tariff_id, chat_index, currency, method_id = int(parts[1]), int(parts[2]), parts[3], int(parts[4])

    tariff = await db.get_tariff(tariff_id)
    data = await state.get_data()
    final_price = data.get("final_price", tariff["price"])
    promo_code = data.get("promo_code")

    # Получить метод оплаты
    methods = await db.get_payment_methods(currency)
    method = next((m for m in methods if m["id"] == method_id), None)
    if not method:
        await call.answer("Метод не найден", show_alert=True)
        return

    # Создать платёж в БД
    payment_id = await db.create_payment(
        user_id=call.from_user.id,
        tariff_id=tariff_id,
        amount=final_price,
        method=f"manual_{method['name']}",
        promo_code=promo_code
    )
    if promo_code:
        await db.use_promo(promo_code)

    # Сохранить chat_index для подтверждения
    await state.update_data(
        current_payment_id=payment_id,
        pending_chat_index=chat_index
    )

    chat_name = config.get_channel_name(chat_index)

    if method["is_link"]:
        # Ссылка — показываем кнопку
        text = (
            f"💳 <b>{method['name']}</b>\n\n"
            f"📦 {tariff['name']} → {chat_name}\n"
            f"💰 Сумма: <b>{final_price:.0f} {currency}</b>\n\n"
            f"Нажми кнопку для перехода к оплате.\n"
            f"После оплаты вернись и отправь скриншот."
        )
        await call.message.edit_text(
            text,
            reply_markup=pay_link_kb(method["details"], tariff_id, chat_index, payment_id),
            parse_mode="HTML"
        )
    else:
        # Текстовые реквизиты
        text = (
            f"💳 <b>{method['name']}</b>\n\n"
            f"📦 {tariff['name']} → {chat_name}\n"
            f"💰 Сумма: <b>{final_price:.0f} {currency}</b>\n\n"
            f"<b>Реквизиты для перевода:</b>\n"
            f"{method['details']}\n\n"
            f"После оплаты отправь скриншот."
        )
        await call.message.edit_text(
            text,
            reply_markup=pay_text_kb(payment_id),
            parse_mode="HTML"
        )
