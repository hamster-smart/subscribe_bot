from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import config
from keyboards.inline import settings_kb, back_kb

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


class SettingsState(StatesGroup):
    editing_payment_details = State()
    editing_welcome = State()


@router.callback_query(F.data == "admin_settings")
async def cb_admin_settings(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    action = await db.get_setting("expire_action", "kick")
    support = await db.get_setting("support_enabled", "1")
    support_status = "✅ включена" if support == "1" else "❌ отключена"
    text = (
        f"⚙️ <b>Настройки бота</b>\n\n"
        f"🔚 Действие при истечении подписки:\n"
        f"  {'✅ Кик (удалить из чата)' if action == 'kick' else '◻️ Кик'}\n"
        f"  {'✅ Мьют (заглушить)' if action == 'mute' else '◻️ Мьют'}\n\n"
        f"📞 Кнопка поддержки: {support_status}\n\n"
        f"Нажми, чтобы изменить:"
    )
    await call.message.edit_text(text, reply_markup=settings_kb(action, support), parse_mode="HTML")


@router.callback_query(F.data.startswith("set_action:"))
async def cb_set_action(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    action = call.data.split(":")[1]  # kick | mute
    await db.set_setting("expire_action", action)
    label = "Кик" if action == "kick" else "Мьют"
    await call.answer(f"✅ Установлено: {label}", show_alert=False)
    await cb_admin_settings(call)


@router.callback_query(F.data == "edit_payment_details")
async def cb_edit_payment_details(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    current = await db.get_setting("payment_details", config.MANUAL_PAYMENT_DETAILS)
    await state.set_state(SettingsState.editing_payment_details)
    await call.message.edit_text(
        f"✏️ <b>Редактирование реквизитов</b>\n\n"
        f"Текущий текст:\n<code>{current}</code>\n\n"
        f"Отправь новый текст реквизитов:",
        parse_mode="HTML",
        reply_markup=back_kb("admin_settings")
    )


@router.message(SettingsState.editing_payment_details)
async def save_payment_details(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await db.set_setting("payment_details", message.text)
    await state.set_state(None)
    await message.answer(
        "✅ Реквизиты обновлены!",
        reply_markup=back_kb("admin_settings")
    )


@router.callback_query(F.data == "edit_welcome")
async def cb_edit_welcome(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    current = await db.get_setting("welcome_text", "")
    await state.set_state(SettingsState.editing_welcome)
    await call.message.edit_text(
        f"✏️ <b>Редактирование приветствия</b>\n\n"
        f"Текущий текст:\n<code>{current}</code>\n\n"
        f"Отправь новый текст:",
        parse_mode="HTML",
        reply_markup=back_kb("admin_settings")
    )


@router.message(SettingsState.editing_welcome)
async def save_welcome(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await db.set_setting("welcome_text", message.text)
    await state.set_state(None)
    await message.answer(
        "✅ Приветствие обновлено!",
        reply_markup=back_kb("admin_settings")
    )


@router.callback_query(F.data == "toggle_support")
async def cb_toggle_support(call: CallbackQuery):
    if not __import__("config").config.ADMIN_IDS.__contains__(call.from_user.id):
        return
    current = await db.get_setting("support_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("support_enabled", new_val)
    status = "✅ включена" if new_val == "1" else "❌ отключена"
    await call.answer(f"Поддержка {status}", show_alert=True)
    # Обновить страницу настроек
    from handlers.settings import cb_admin_settings
    await cb_admin_settings(call)
