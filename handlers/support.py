"""
support.py — модуль поддержки пользователей.

Схема работы:
  1. Пользователь нажимает кнопку "Поддержка" → входит в режим диалога.
  2. Каждое сообщение пересылается в личку админу (SUPPORT_CHAT_ID из конфига).
  3. Под сообщением у админа — кнопки "↩️ Ответить" и "🚫 Забанить".
  4. Админ жмёт "↩️ Ответить" → вводит текст → бот доставляет ответ пользователю.
  5. "🚫 Забанить" — выставляет is_banned=1 в БД (юзер теряет возможность писать в поддержку).

Требования к config.py:
  SUPPORT_CHAT_ID: int   # Telegram ID личного аккаунта поддержки (без дефолта, только из .env)

Подключение в bot.py / main.py:
  from handlers import support
  dp.include_router(support.router)
"""

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import aiosqlite
from config import config

router = Router()

# ─── FSM ─────────────────────────────────────────────────────────────────────

class SupportState(StatesGroup):
    in_dialog  = State()   # пользователь пишет в поддержку
    wait_reply = State()   # админ вводит ответ


class SupportReplyState(StatesGroup):
    typing = State()       # админ набирает ответ конкретному юзеру


# ─── HELPERS ─────────────────────────────────────────────────────────────────

async def _is_banned(user_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as dbc:
        dbc.row_factory = aiosqlite.Row
        async with dbc.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
    return bool(row and row["is_banned"])


async def _ban_user(user_id: int) -> None:
    async with aiosqlite.connect(config.DB_PATH) as dbc:
        await dbc.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
        await dbc.commit()


def _support_msg_kb(user_id: int) -> object:
    """Клавиатура под сообщением пользователя в чате поддержки."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="↩️ Ответить", callback_data=f"support_reply:{user_id}"),
        InlineKeyboardButton(text="🚫 Забанить", callback_data=f"support_ban:{user_id}"),
    )
    return builder.as_markup()


# ─── ВХОД В ПОДДЕРЖКУ (callback от кнопки в главном меню) ───────────────────

@router.callback_query(F.data == "support")
async def cb_support_enter(call: CallbackQuery, state: FSMContext):
    """Пользователь нажал кнопку 'Поддержка'."""
    user_id = call.from_user.id

    if await _is_banned(user_id):
        await call.answer("🚫 Вы не можете обращаться в поддержку.", show_alert=True)
        return

    await state.set_state(SupportState.in_dialog)
    await call.message.edit_text(
        "💬 <b>Поддержка</b>\n\n"
        "Напишите ваш вопрос — мы ответим в ближайшее время.\n\n"
        "Вы можете отправить текст, фото или скриншот.",
        reply_markup=_exit_kb(),
        parse_mode="HTML"
    )


@router.message(F.text == "/support")
async def cmd_support(message: Message, state: FSMContext):
    """Команда /support как альтернативный вход."""
    user_id = message.from_user.id

    if await _is_banned(user_id):
        await message.answer("🚫 Вы не можете обращаться в поддержку.")
        return

    await state.set_state(SupportState.in_dialog)
    await message.answer(
        "💬 <b>Поддержка</b>\n\n"
        "Напишите ваш вопрос — мы ответим в ближайшее время.\n\n"
        "Вы можете отправить текст, фото или скриншот.",
        reply_markup=_exit_kb(),
        parse_mode="HTML"
    )


def _exit_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Закрыть", callback_data="support_exit"))
    return builder.as_markup()


@router.callback_query(F.data == "support_exit")
async def cb_support_exit(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("✅ Диалог с поддержкой закрыт.")


# ─── СООБЩЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ → ПЕРЕСЫЛКА АДМИНУ ──────────────────────────

@router.message(SupportState.in_dialog)
async def user_message_to_support(message: Message, state: FSMContext, bot: Bot):
    """Любое сообщение пользователя в режиме поддержки — пересылаем админу."""
    user_id = message.from_user.id

    if await _is_banned(user_id):
        await state.clear()
        await message.answer("🚫 Вы заблокированы.")
        return

    uname = f"@{message.from_user.username}" if message.from_user.username else f"id{user_id}"
    full_name = message.from_user.full_name or "—"
    header = (
        f"💬 <b>Обращение в поддержку</b>\n"
        f"👤 {full_name} {uname}\n"
        f"🆔 <code>{user_id}</code>"
    )
    kb = _support_msg_kb(user_id)

    try:
        if message.photo:
            await bot.send_photo(
                config.SUPPORT_CHAT_ID,
                photo=message.photo[-1].file_id,
                caption=f"{header}\n\n{message.caption or ''}",
                reply_markup=kb,
                parse_mode="HTML"
            )
        elif message.document:
            await bot.send_document(
                config.SUPPORT_CHAT_ID,
                document=message.document.file_id,
                caption=f"{header}\n\n{message.caption or ''}",
                reply_markup=kb,
                parse_mode="HTML"
            )
        elif message.video:
            await bot.send_video(
                config.SUPPORT_CHAT_ID,
                video=message.video.file_id,
                caption=f"{header}\n\n{message.caption or ''}",
                reply_markup=kb,
                parse_mode="HTML"
            )
        elif message.text:
            await bot.send_message(
                config.SUPPORT_CHAT_ID,
                f"{header}\n\n{message.text}",
                reply_markup=kb,
                parse_mode="HTML"
            )
        else:
            # голосовые, стикеры и пр.
            await message.forward(config.SUPPORT_CHAT_ID)
            await bot.send_message(
                config.SUPPORT_CHAT_ID,
                header,
                reply_markup=kb,
                parse_mode="HTML"
            )
    except Exception:
        await message.answer("⚠️ Не удалось отправить сообщение в поддержку. Попробуйте позже.")
        return

    await message.answer(
        "✅ Сообщение отправлено. Ожидайте ответа.",
        reply_markup=_exit_kb()
    )


# ─── ОТВЕТ АДМИНА ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("support_reply"))
async def cb_support_reply(call: CallbackQuery, state: FSMContext):
    """Админ нажал '↩️ Ответить' под сообщением пользователя."""
    if call.from_user.id != config.SUPPORT_CHAT_ID:
        # защита: только тот аккаунт, которому пересылаются сообщения
        await call.answer("⛔ Недостаточно прав.", show_alert=True)
        return

    user_id = int(call.data.split(":")[1])
    await state.update_data(reply_to_user=user_id)
    await state.set_state(SupportReplyState.typing)

    await call.message.answer(
        f"✏️ Введите ответ пользователю <code>{user_id}</code>.\n\n"
        f"Отправьте /cancel для отмены.",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(SupportReplyState.typing)
async def handle_admin_reply(message: Message, state: FSMContext, bot: Bot):
    """Админ написал ответ — доставляем пользователю."""
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ Ответ отменён.")
        return

    data = await state.get_data()
    user_id = data.get("reply_to_user")
    if not user_id:
        await state.clear()
        return

    await state.clear()

    try:
        if message.photo:
            await bot.send_photo(
                user_id,
                photo=message.photo[-1].file_id,
                caption=f"💬 <b>Ответ поддержки:</b>\n\n{message.caption or ''}",
                parse_mode="HTML"
            )
        elif message.text:
            await bot.send_message(
                user_id,
                f"💬 <b>Ответ поддержки:</b>\n\n{message.text}",
                parse_mode="HTML"
            )
        else:
            await message.forward(user_id)

        await message.answer(f"✅ Ответ доставлен пользователю <code>{user_id}</code>.", parse_mode="HTML")
    except Exception:
        await message.answer(f"⚠️ Не удалось доставить ответ пользователю <code>{user_id}</code>. Возможно, он заблокировал бота.", parse_mode="HTML")


# ─── БАН ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("support_ban"))
async def cb_support_ban(call: CallbackQuery, bot: Bot):
    """Админ нажал '🚫 Забанить' под сообщением пользователя."""
    if call.from_user.id != config.SUPPORT_CHAT_ID:
        await call.answer("⛔ Недостаточно прав.", show_alert=True)
        return

    user_id = int(call.data.split(":")[1])
    await _ban_user(user_id)

    # убираем кнопки под сообщением
    try:
        if call.message.caption:
            await call.message.edit_caption(
                call.message.caption + "\n\n🚫 <b>Пользователь забанен</b>",
                parse_mode="HTML"
            )
        else:
            await call.message.edit_text(
                call.message.text + "\n\n🚫 <b>Пользователь забанен</b>",
                parse_mode="HTML"
            )
    except Exception:
        pass

    await call.answer(f"🚫 Пользователь {user_id} забанен в боте.", show_alert=True)

    # уведомляем пользователя
    try:
        await bot.send_message(user_id, "🚫 Ваш аккаунт заблокирован. Обратитесь к администратору.")
    except Exception:
        pass
