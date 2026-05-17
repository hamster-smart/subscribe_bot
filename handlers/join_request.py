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
    if chat_id == config.CHANNEL_1_ID:
        chat_index = 0
    elif chat_id == config.CHANNEL_2_ID:
        chat_index = 1
    else:
        return  # Не наш чат — не трогаем

    # Зарегистрировать пользователя
    await db.upsert_user(user.id, user.username, user.full_name)

    # Проверить подписку СТРОГО по этому чату
    sub = await db.get_active_subscription(user.id, chat_index=chat_index)

    if sub:
        # Есть подписка на ЭТОТ чат — одобрить
        try:
            await bot.approve_chat_join_request(chat_id=chat_id, user_id=user.id)
        except Exception:
            pass
        # Если пробная — chat_member handler замьютит
        return

    # Подписки на этот чат нет — отклонить и показать меню
    try:
        await bot.decline_chat_join_request(chat_id=chat_id, user_id=user.id)
    except Exception:
        pass

    welcome = await db.get_setting(
        "welcome_text",
        "👋 Привет! Для доступа к каналу оформи подписку."
    )
    support_enabled = await db.get_setting("support_enabled", "1")
    chat_name = config.get_channel_name(chat_index)

    try:
        await bot.send_message(
            user.id,
            f"{welcome}\n\n"
            f"📺 Канал: <b>{chat_name}</b>\n\n"
            f"Выбери тариф — получишь ссылку сразу после оплаты.",
            reply_markup=main_menu_kb(support_enabled == "1"),
            parse_mode="HTML"
        )
    except Exception:
        pass
