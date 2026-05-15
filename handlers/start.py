from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

import database as db
from keyboards.inline import main_menu_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )
    welcome = await db.get_setting("welcome_text",
        "👋 Здравствуйте! Пожалуйста, выберите чат, тариф, оплатите полписку и получите доступ к чату.")

    sub = await db.get_active_subscription(message.from_user.id)
    if sub:
        from datetime import datetime
        exp = datetime.fromisoformat(sub["expires_at"])
        text = (
            f"{welcome}\n\n"
            f"✅ У Вас активна подписка: <b>{sub['tariff_name']}</b>\n"
            f"📅 Действует до: <b>{exp.strftime('%d.%m.%Y %H:%M')}</b>"
        )
    else:
        text = welcome

    support = await db.get_setting("support_enabled", "1")
    await message.answer(text, reply_markup=main_menu_kb(support == "1"), parse_mode="HTML")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    welcome = await db.get_setting("welcome_text",
        "👋 Выберите тариф и получите доступ к каналу.")
    sub = await db.get_active_subscription(call.from_user.id)
    if sub:
        from datetime import datetime
        exp = datetime.fromisoformat(sub["expires_at"])
        text = (
            f"{welcome}\n\n"
            f"✅ Активная подписка: <b>{sub['tariff_name']}</b>\n"
            f"📅 До: <b>{exp.strftime('%d.%m.%Y %H:%M')}</b>"
        )
    else:
        text = welcome
    support = await db.get_setting("support_enabled", "1")
    await call.message.edit_text(text, reply_markup=main_menu_kb(support == "1"), parse_mode="HTML")


@router.callback_query(F.data == "my_subscription")
async def cb_my_subscription(call: CallbackQuery):
    sub = await db.get_active_subscription(call.from_user.id)
    from keyboards.inline import back_kb
    if sub:
        from datetime import datetime
        exp = datetime.fromisoformat(sub["expires_at"])
        text = (
            f"👤 <b>Ваша подписка</b>\n\n"
            f"📦 Тариф: <b>{sub['tariff_name']}</b>\n"
            f"📅 Активна до: <b>{exp.strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"⏳ Осталось: <b>{(exp - datetime.utcnow()).days} дн.</b>"
        )
    else:
        text = "❌ У Вас нет активной подписки.\nВыберите тариф, чтобы получить доступ!"
    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    from keyboards.inline import back_kb
    await call.message.edit_text(
        "📞 <b>Поддержка</b>\n\nЕсли возникли вопросы — напишите администратору: @Bulgaria_helps_Feedback_bot",
        reply_markup=back_kb(),
        parse_mode="HTML"
    )
