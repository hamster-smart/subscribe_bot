from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import config
from keyboards.inline import (
    admin_menu_kb, admin_payment_kb, back_kb,
    admin_tariffs_kb, tariff_edit_kb, promos_kb, cancel_kb
)
from services.channel import grant_access, kick_user, mute_user

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS



# ─── ADMIN MENU ────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "⚙️ <b>Панель администратора</b>",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        "⚙️ <b>Панель администратора</b>",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML"
    )


# ─── STATS ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    stats = await db.get_stats()
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"✅ Активных подписок: <b>{stats['active_subs']}</b>\n"
        f"💰 Выручка всего: <b>{stats['total_revenue']:.0f} ₽</b>\n"
        f"📅 Сегодня: <b>{stats['today_revenue']:.0f} ₽</b>\n"
        f"⏳ Ожидают подтверждения: <b>{stats['pending_count']}</b>"
    )
    await call.message.edit_text(text, reply_markup=back_kb("admin_menu"), parse_mode="HTML")


# ─── PENDING PAYMENTS ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_pending")
async def cb_admin_pending(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    payments = await db.get_pending_payments()
    if not payments:
        await call.message.edit_text(
            "✅ Нет ожидающих подтверждения платежей.",
            reply_markup=back_kb("admin_menu")
        )
        return

    await call.message.edit_text(
        f"⏳ <b>Ожидают подтверждения: {len(payments)}</b>\nОтвечаю по каждому...",
        parse_mode="HTML"
    )
    for p in payments:
        text = (
            f"💰 <b>Платёж #{p['id']}</b>\n"
            f"👤 {p['full_name']} (@{p['username'] or 'нет'}) | <code>{p['user_id']}</code>\n"
            f"📦 {p['tariff_name']} ({p['days']} дн.)\n"
            f"💵 {p['amount']:.0f} ₽ | {p['method']}\n"
            f"🕐 {p['created_at']}"
        )
        kb = admin_payment_kb(p["id"])
        if p["screenshot_file_id"]:
            await call.bot.send_photo(
                call.from_user.id,
                photo=p["screenshot_file_id"],
                caption=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        else:
            await call.bot.send_message(
                call.from_user.id,
                text,
                reply_markup=kb,
                parse_mode="HTML"
            )


@router.callback_query(F.data.startswith("admin_confirm:"))
async def cb_admin_confirm(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    payment_id = int(call.data.split(":")[1])
    payment = await db.get_payment(payment_id)
    if not payment:
        await call.answer("Платёж не найден", show_alert=True)
        return
    if payment["status"] != "pending":
        await call.answer(f"Статус: {payment['status']}", show_alert=True)
        return

    await db.confirm_payment(payment_id, call.from_user.id)
    tariff = await db.get_tariff(payment["tariff_id"])
    await db.create_subscription(payment["user_id"], payment["tariff_id"], tariff["days"])

    link = await grant_access(bot, payment["user_id"])
    from datetime import datetime, timedelta
    expires = datetime.utcnow() + timedelta(days=tariff["days"])

    try:
        await bot.send_message(
            payment["user_id"],
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"📦 Тариф: <b>{tariff['name']}</b>\n"
            f"🔗 Ссылка: {link}\n"
            f"📅 Действует до: <b>{expires.strftime('%d.%m.%Y')}</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await call.message.edit_caption(
        call.message.caption + "\n\n✅ <b>ПОДТВЕРЖДЁН</b>",
        parse_mode="HTML"
    ) if call.message.caption else await call.message.edit_text(
        call.message.text + "\n\n✅ <b>ПОДТВЕРЖДЁН</b>",
        parse_mode="HTML"
    )
    await call.answer("✅ Подтверждено!", show_alert=False)


@router.callback_query(F.data.startswith("admin_reject:"))
async def cb_admin_reject(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    payment_id = int(call.data.split(":")[1])
    payment = await db.get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await call.answer("Уже обработан", show_alert=True)
        return

    await db.reject_payment(payment_id, call.from_user.id)
    try:
        await bot.send_message(
            payment["user_id"],
            "❌ Оплата не подтверждена. Если это ошибка — напишите в поддержку."
        )
    except Exception:
        pass

    await call.answer("❌ Отклонено", show_alert=False)
    suffix = "\n\n❌ <b>ОТКЛОНЁН</b>"
    if call.message.caption:
        await call.message.edit_caption(call.message.caption + suffix, parse_mode="HTML")
    else:
        await call.message.edit_text(call.message.text + suffix, parse_mode="HTML")


# ─── SUBSCRIBERS LIST ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_subs")
async def cb_admin_subs(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    import aiosqlite as _aiosqlite
    import io
    from datetime import datetime
    from openpyxl import Workbook
    from aiogram.types import BufferedInputFile

    async with _aiosqlite.connect(config.DB_PATH) as dbc:
        dbc.row_factory = _aiosqlite.Row
        async with dbc.execute("""
            SELECT u.user_id, u.username, u.full_name, s.starts_at, s.expires_at,
                   t.name as tariff_name, s.is_active
            FROM subscriptions s
            JOIN users u ON u.user_id = s.user_id
            JOIN tariffs t ON t.id = s.tariff_id
            WHERE s.is_active = 1 AND datetime(s.expires_at) > datetime('now')
            ORDER BY s.expires_at ASC
        """) as cur:
            subs = await cur.fetchall()

    if not subs:
        await call.message.edit_text("Нет активных подписчиков.", reply_markup=back_kb("admin_menu"))
        return

    # Создать xlsx в памяти
    wb = Workbook()
    ws = wb.active
    ws.title = "Подписчики"

    # Заголовки
    headers = ["User ID", "Username", "Полное имя", "Тариф", "Начало", "Истекает", "Дней осталось"]
    ws.append(headers)

    # Стиль заголовков
    from openpyxl.styles import Font, PatternFill, Alignment
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2E86AB")
        cell.alignment = Alignment(horizontal="center")

    now = datetime.utcnow()
    for s in subs:
        exp = datetime.fromisoformat(s["expires_at"])
        start = datetime.fromisoformat(s["starts_at"])
        days_left = (exp - now).days
        ws.append([
            s["user_id"],
            f"@{s['username']}" if s["username"] else "—",
            s["full_name"] or "—",
            s["tariff_name"],
            start.strftime("%d.%m.%Y"),
            exp.strftime("%d.%m.%Y"),
            days_left,
        ])

    # Авто-ширина колонок
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 3, 40)

    # Сохранить в буфер
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    from datetime import datetime as dt
    filename = f"subscribers_{dt.now().strftime('%Y%m%d_%H%M')}.xlsx"

    await call.message.edit_text(
        f"👥 <b>Активных подписчиков: {len(subs)}</b>\n\nФормирую файл...",
        parse_mode="HTML"
    )
    await bot.send_document(
        call.from_user.id,
        document=BufferedInputFile(buf.read(), filename=filename),
        caption=f"📊 Подписчики на {dt.now().strftime('%d.%m.%Y %H:%M')} — {len(subs)} чел."
    )
    await call.message.edit_text(
        f"👥 Файл отправлен — {len(subs)} активных подписчиков.",
        reply_markup=back_kb("admin_menu"),
        parse_mode="HTML"
    )


# ─── BROADCAST ─────────────────────────────────────────────────────────────────

class BroadcastState(StatesGroup):
    waiting_message = State()


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(BroadcastState.waiting_message)
    await call.message.edit_text(
        "📢 <b>Рассылка</b>\n\nОтправь сообщение (текст, фото, видео) — оно уйдёт всем пользователям.\n\n"
        "Поддерживается HTML-разметка.",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )


@router.message(BroadcastState.waiting_message)
async def handle_broadcast(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(None)
    users = await db.get_all_users()
    sent = 0
    failed = 0
    status_msg = await message.answer(f"📢 Рассылка началась... 0/{len(users)}")

    for i, user in enumerate(users):
        try:
            if message.photo:
                await bot.send_photo(
                    user["user_id"], message.photo[-1].file_id,
                    caption=message.caption, parse_mode="HTML"
                )
            elif message.video:
                await bot.send_video(
                    user["user_id"], message.video.file_id,
                    caption=message.caption, parse_mode="HTML"
                )
            else:
                await bot.send_message(user["user_id"], message.text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

        if (i + 1) % 20 == 0:
            try:
                await status_msg.edit_text(f"📢 Отправлено: {sent}/{len(users)}")
            except Exception:
                pass
        __import__("asyncio").sleep(0.05)

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n✅ Доставлено: {sent}\n❌ Ошибок: {failed}",
        reply_markup=back_kb("admin_menu")
    )


# ─── PROMO CODES ───────────────────────────────────────────────────────────────

class PromoCreateState(StatesGroup):
    code = State()
    discount = State()
    uses = State()


@router.callback_query(F.data == "admin_promos")
async def cb_admin_promos(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    async with __import__("aiosqlite").connect(config.DB_PATH) as dbc:
        dbc.row_factory = __import__("aiosqlite").Row
        async with dbc.execute(
            "SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 15"
        ) as cur:
            promos = await cur.fetchall()

    if promos:
        lines = []
        for p in promos:
            disc = f"-{p['discount_pct']}%" if p['discount_pct'] else f"-{p['discount_rub']:.0f}₽"
            uses = f"{p['uses_left']} ост." if p["uses_left"] != -1 else "∞"
            active = "🟢" if p["is_active"] else "🔴"
            lines.append(f"{active} <code>{p['code']}</code> | {disc} | {uses} | использ.: {p['uses_total']}")
        text = "<b>🎟 Промокоды:</b>\n\n" + "\n".join(lines)
    else:
        text = "🎟 Промокодов пока нет."

    await call.message.edit_text(text, reply_markup=promos_kb(), parse_mode="HTML")


@router.callback_query(F.data == "create_promo")
async def cb_create_promo(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(PromoCreateState.code)
    await call.message.edit_text(
        "🎟 Введи код промокода (латиница/цифры):",
        reply_markup=cancel_kb()
    )


@router.message(PromoCreateState.code)
async def promo_set_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if not code.isalnum():
        await message.answer("❌ Только буквы и цифры. Попробуй ещё раз:")
        return
    await state.update_data(code=code)
    await state.set_state(PromoCreateState.discount)
    await message.answer(
        "💸 Введи скидку:\n• <b>15%</b> — скидка в процентах\n• <b>100р</b> — скидка в рублях",
        parse_mode="HTML"
    )


@router.message(PromoCreateState.discount)
async def promo_set_discount(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    disc_pct = 0
    disc_rub = 0.0
    if text.endswith("%"):
        try:
            disc_pct = int(text[:-1])
        except ValueError:
            await message.answer("❌ Неверный формат. Пример: 15%")
            return
    elif text.endswith("р") or text.endswith("руб") or text.endswith("rub"):
        try:
            disc_rub = float(text.replace("р", "").replace("руб", "").replace("rub", "").strip())
        except ValueError:
            await message.answer("❌ Неверный формат. Пример: 100р")
            return
    else:
        try:
            disc_pct = int(text)
        except ValueError:
            await message.answer("❌ Введи скидку. Пример: 15% или 100р")
            return

    await state.update_data(disc_pct=disc_pct, disc_rub=disc_rub)
    await state.set_state(PromoCreateState.uses)
    await message.answer(
        "🔢 Сколько раз можно использовать?\n<b>0</b> — неограниченно",
        parse_mode="HTML"
    )


@router.message(PromoCreateState.uses)
async def promo_set_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи число:")
        return

    data = await state.get_data()
    uses_left = -1 if uses == 0 else uses
    promo_id = await db.create_promo(
        code=data["code"],
        discount_pct=data.get("disc_pct", 0),
        discount_rub=data.get("disc_rub", 0.0),
        uses_left=uses_left
    )
    disc = f"{data['disc_pct']}%" if data.get("disc_pct") else f"{data.get('disc_rub', 0):.0f}₽"
    await message.answer(
        f"✅ Промокод создан!\n\n"
        f"<code>{data['code']}</code>\n"
        f"Скидка: {disc}\n"
        f"Использований: {'∞' if uses_left == -1 else uses_left}",
        reply_markup=back_kb("admin_menu"),
        parse_mode="HTML"
    )
    await state.set_state(None)


# ─── TARIFF MANAGEMENT ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_tariffs")
async def cb_admin_tariffs(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    tariffs = await db.get_tariffs()
    await call.message.edit_text(
        "📋 <b>Управление тарифами</b>",
        reply_markup=admin_tariffs_kb(tariffs),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_edit_tariff:"))
async def cb_edit_tariff(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    tariff_id = int(call.data.split(":")[1])
    t = await db.get_tariff(tariff_id)
    text = (
        f"📦 <b>{t['name']}</b>\n\n"
        f"📝 {t['description']}\n"
        f"⏳ Дней: {t['days']}\n"
        f"💰 Цена: {t['price']:.0f} ₽\n"
        f"Статус: {'🟢 Активен' if t['is_active'] else '🔴 Отключён'}"
    )
    await call.message.edit_text(
        text,
        reply_markup=tariff_edit_kb(tariff_id, t["is_active"]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("tariff_toggle:"))
async def cb_tariff_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    tariff_id = int(call.data.split(":")[1])
    t = await db.get_tariff(tariff_id)
    new_status = 0 if t["is_active"] else 1
    await db.update_tariff(tariff_id, is_active=new_status)
    await call.answer(f"{'🟢 Включён' if new_status else '🔴 Отключён'}")
    t2 = await db.get_tariff(tariff_id)
    await call.message.edit_reply_markup(
        reply_markup=tariff_edit_kb(tariff_id, t2["is_active"])
    )


# ─── PAYMENT METHODS MANAGEMENT ────────────────────────────────────────────────

class PaymentMethodState(StatesGroup):
    name = State()
    currency = State()
    details = State()
    is_link = State()


def payment_methods_admin_kb(methods: list) -> object:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for m in methods:
        status = "🟢" if m["is_active"] else "🔴"
        link_icon = "🔗" if m["is_link"] else "📝"
        builder.row(InlineKeyboardButton(
            text=f"{status} {link_icon} {m['name']} ({m['currency']})",
            callback_data=f"pm_toggle:{m['id']}"
        ))
    builder.row(InlineKeyboardButton(text="➕ Добавить метод", callback_data="pm_add"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_settings"))
    return builder.as_markup()


@router.callback_query(F.data == "admin_payment_methods")
async def cb_payment_methods(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    methods = await db.get_all_payment_methods()
    text = (
        "💳 <b>Методы оплаты</b>\n\n"
        "🟢/🔴 — вкл/выкл (нажми для переключения)\n"
        "🔗 — ссылка (кнопка), 📝 — текст (реквизиты)\n\n"
    )
    if methods:
        for m in methods:
            status = "🟢" if m["is_active"] else "🔴"
            text += f"{status} <b>{m['name']}</b> ({m['currency']})\n"
            preview = m["details"][:60] + "..." if len(m["details"]) > 60 else m["details"]
            text += f"   <code>{preview}</code>\n\n"
    else:
        text += "Методов пока нет. Добавь первый!"

    await call.message.edit_text(
        text,
        reply_markup=payment_methods_admin_kb(methods),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("pm_toggle:"))
async def cb_pm_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    method_id = int(call.data.split(":")[1])
    await db.toggle_payment_method(method_id)
    await cb_payment_methods(call)


@router.callback_query(F.data == "pm_add")
async def cb_pm_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(PaymentMethodState.name)
    await call.message.edit_text(
        "➕ <b>Новый метод оплаты</b>\n\nШаг 1/4: Введи название:\n"
        "<i>Например: 💳 Сбербанк, 💶 IBAN EUR, 💳 Тинькофф</i>",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )


@router.message(PaymentMethodState.name)
async def pm_set_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(pm_name=message.text.strip())
    await state.set_state(PaymentMethodState.currency)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for cur in ["RUB", "EUR", "USD"]:
        builder.row(InlineKeyboardButton(text=cur, callback_data=f"pm_currency:{cur}"))
    await message.answer(
        "Шаг 2/4: Выбери валюту:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("pm_currency:"), PaymentMethodState.currency)
async def pm_set_currency(call: CallbackQuery, state: FSMContext):
    currency = call.data.split(":")[1]
    await state.update_data(pm_currency=currency)
    await state.set_state(PaymentMethodState.details)
    await call.message.edit_text(
        "Шаг 3/4: Отправь <b>ссылку</b> или <b>реквизиты</b>:\n\n"
        "Ссылка: <code>https://www.tinkoff.ru/rm/ivanov/xxx</code>\n"
        "Реквизиты: <code>IBAN: DE89 3704...\nBIC: COBADEFF</code>",
        parse_mode="HTML"
    )


@router.message(PaymentMethodState.details)
async def pm_set_details(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    details = message.text.strip()
    is_link = 1 if details.startswith("http") else 0
    await state.update_data(pm_details=details, pm_is_link=is_link)
    await state.set_state(PaymentMethodState.is_link)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔗 Ссылка (кнопка)", callback_data="pm_type:1"),
        InlineKeyboardButton(text="📝 Текст (реквизиты)", callback_data="pm_type:0")
    )
    link_detected = "✅ Определено автоматически как ссылка" if is_link else "✅ Определено как текст"
    await message.answer(
        f"Шаг 4/4: Как показывать пользователю?\n{link_detected}\n\nПодтверди или измени:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("pm_type:"), PaymentMethodState.is_link)
async def pm_confirm(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    is_link = int(call.data.split(":")[1])
    data = await state.get_data()
    await state.set_state(None)

    method_id = await db.add_payment_method(
        name=data["pm_name"],
        currency=data["pm_currency"],
        details=data["pm_details"],
        is_link=is_link
    )
    type_label = "🔗 ссылка-кнопка" if is_link else "📝 текстовые реквизиты"
    await call.message.edit_text(
        f"✅ <b>Метод добавлен!</b>\n\n"
        f"Название: {data['pm_name']}\n"
        f"Валюта: {data['pm_currency']}\n"
        f"Тип: {type_label}",
        reply_markup=back_kb("admin_payment_methods"),
        parse_mode="HTML"
    )
