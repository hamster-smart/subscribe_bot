from aiogram import Router, Bot
from aiogram.types import ChatJoinRequest

import database as db
from config import config
from keyboards.inline import main_menu_kb

router = Router()


@router.chat_join_request()
async def handle_join_request(request: ChatJoinRequest, bot: Bot):
    user = request.from_user
    chat_id = request.chat.id

    # Определить какой чат
    chat_index = 0
    if chat_id == config.CHANNEL_2_ID:
        chat_index = 1

    # Зарегистрировать пользователя
    await db.upsert_user(user.id, user.username, user.full_name)

    # Проверить активную подписку
    sub = await db.get_active_subscription(user.id)
    if sub:
        # Есть подписка — одобрить заявку сразу
        try:
            await bot.approve_chat_join_request(chat_id=chat_id, user_id=user.id)
        except Exception:
            pass
        # Если пробная — мьютить после вступления (обработает chat_member handler)
        return

    # Подписки нет — отклонить заявку и отправить приветствие с меню
    try:
        await bot.decline_chat_join_request(chat_id=chat_id, user_id=user.id)
    except Exception:
        pass

    welcome = await db.get_setting(
        "welcome_text",
        "👋 Привет! Для доступа к каналу оформи подписку."
    )
    support_enabled = await db.get_setting("support_enabled", "1")

    try:
        await bot.send_message(
            user.id,
            f"{welcome}\n\n"
            f"📺 Ты пытался вступить в: <b>{request.chat.title}</b>\n\n"
            f"Выбери тариф — получишь ссылку для вступления сразу после оплаты.",
            reply_markup=main_menu_kb(support_enabled == "1"),
            parse_mode="HTML"
        )
    except Exception:
        pass
