from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Тарифы", callback_data="show_tariffs"))
    builder.row(InlineKeyboardButton(text="👤 Моя подписка", callback_data="my_subscription"))
    builder.row(InlineKeyboardButton(text="🎟 Промокод", callback_data="enter_promo"))
    builder.row(InlineKeyboardButton(text="📞 Поддержка", callback_data="support"))
    return builder.as_markup()


def tariffs_kb(tariffs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in tariffs:
        builder.row(InlineKeyboardButton(
            text=f"{t['name']} — {t['price']:.0f} ₽",
            callback_data=f"select_tariff:{t['id']}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return builder.as_markup()


def tariff_detail_kb(tariff_id: int, has_promo: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="💳 Оплатить вручную",
        callback_data=f"pay_manual:{tariff_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="🏦 ЮКасса / Тинькофф",
        callback_data=f"pay_online:{tariff_id}"
    ))
    if not has_promo:
        builder.row(InlineKeyboardButton(
            text="🎟 Ввести промокод",
            callback_data=f"promo_for:{tariff_id}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="show_tariffs"))
    return builder.as_markup()


def manual_payment_kb(payment_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📷 Отправить скриншот оплаты",
        callback_data=f"send_screenshot:{payment_id}"
    ))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="main_menu"))
    return builder.as_markup()


def after_screenshot_kb(payment_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✅ Я оплатил, жду подтверждения",
        callback_data=f"awaiting_confirm:{payment_id}"
    ))
    return builder.as_markup()


def admin_payment_kb(payment_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm:{payment_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject:{payment_id}")
    )
    return builder.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="⏳ Ожидают оплаты", callback_data="admin_pending"))
    builder.row(InlineKeyboardButton(text="👥 Подписчики", callback_data="admin_subs"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin_promos"))
    builder.row(InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings"))
    return builder.as_markup()


def settings_kb(current_action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    kick_mark = "✅" if current_action == "kick" else "◻️"
    mute_mark = "✅" if current_action == "mute" else "◻️"
    builder.row(
        InlineKeyboardButton(text=f"{kick_mark} Кик", callback_data="set_action:kick"),
        InlineKeyboardButton(text=f"{mute_mark} Мьют", callback_data="set_action:mute")
    )
    builder.row(InlineKeyboardButton(text="💳 Методы оплаты", callback_data="admin_payment_methods"))
    builder.row(InlineKeyboardButton(text="✏️ Приветствие", callback_data="edit_welcome"))
    builder.row(InlineKeyboardButton(text="📋 Тарифы", callback_data="admin_tariffs"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu"))
    return builder.as_markup()


def back_kb(callback: str = "main_menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=callback))
    return builder.as_markup()


def admin_tariffs_kb(tariffs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in tariffs:
        status = "🟢" if t["is_active"] else "🔴"
        builder.row(InlineKeyboardButton(
            text=f"{status} {t['name']} — {t['price']:.0f}₽",
            callback_data=f"admin_edit_tariff:{t['id']}"
        ))
    builder.row(InlineKeyboardButton(text="➕ Новый тариф", callback_data="admin_add_tariff"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_settings"))
    return builder.as_markup()


def tariff_edit_kb(tariff_id: int, is_active: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "🔴 Отключить" if is_active else "🟢 Включить"
    builder.row(InlineKeyboardButton(
        text=toggle_text, callback_data=f"tariff_toggle:{tariff_id}"
    ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_tariffs"))
    return builder.as_markup()


def promos_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Создать промокод", callback_data="create_promo"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu"))
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_menu"))
    return builder.as_markup()
