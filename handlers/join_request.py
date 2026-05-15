from aiogram import Router, Bot, F
from aiogram.types import ChatJoinRequest

import database as db
from config import config
from keyboards.inline import main_menu_kb

router = Router()


@router.chat_join_request()
async def handle_join_request(request: ChatJoinRequest, bot: Bot):
    """
    Перехватывает заявки на вступление в закрытый канал/группу.
    Отклоняет заявку и отправляет пользователю приветствие с тарифами.
    """
    user = request.from_user
    chat_id = request.chat.id

    # Определить к какому чату относится заявка
    chat_index = 0
    if chat_id == config.CHANNEL_2_ID:
        chat_index = 1

    # Отклонить заявку — пусть сначала оплатит
    try:
        await bot.decline_chat_join_request(chat_id=chat_id, user_id=user.id)
    except Exception:
        pass

    # Зарегистрировать пользователя если новый
    await db.upsert_user(user.id, user.username, user.full_name)

    # Проверить есть ли активная подписка
    sub = await db.get_active_subscription(user.id)
    if sub:
        # Подписка есть — выдать доступ напрямую
        from services.channel import grant_access
        link = await grant_access(bot, user.id, chat_index)
        try:
            await bot.send_message(
                user.id,
                f"✅ <b>У вас есть активная подписка!</b>\n\n"
                f"Вот ваша ссылка для вступления:\n{link}",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return

    # Подписки нет — отправить приветствие с меню
    welcome = await db.get_setting(
        "welcome_text",
        "👋 Привет! Для доступа к каналу оформи подписку."
    )
    support_enabled = await db.get_setting("support_enabled", "1")

    # Сохранить какой чат запрашивал — пригодится при выборе тарифа
    try:
        from aiogram.fsm.storage.memory import MemoryStorage
        # Просто отправим приветствие, chat_index пользователь выберет сам
        await bot.send_message(
            user.id,
            f"{welcome}\n\n"
            f"📺 Вы пытались вступить в: <b>{request.chat.title}</b>",
            reply_markup=main_menu_kb(support_enabled == "1"),
            parse_mode="HTML"
        )
    except Exception:
        # Пользователь заблокировал бота — ничего не делаем
        pass
