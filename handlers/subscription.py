from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

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
    if promo:
        await state.update_data(promo_code=code)
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
    else:
        await message.answer(
            "❌ Промокод недействителен или уже использован.",
            reply_markup=back_kb()
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
