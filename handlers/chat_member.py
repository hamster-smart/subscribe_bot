from aiogram import Router, Bot, F
from aiogram.types import ChatMemberUpdated

import database as db
from config import config
from services.channel import mute_user

router = Router()


@router.chat_member()
async def handle_chat_member(update: ChatMemberUpdated, bot: Bot):
    """
    Отслеживает вступление пользователей в чат.
    Если пользователь вступил по пробному тарифу — мьютит его.
    """
    # Нас интересует только вступление (not member → member)
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    joined = old_status in ("left", "kicked") and new_status == "member"
    if not joined:
        return

    user_id = update.new_chat_member.user.id
    chat_id = update.chat.id

    # Определить chat_index
    chat_index = 0
    if chat_id == config.CHANNEL_2_ID:
        chat_index = 1
    elif chat_id != config.CHANNEL_1_ID:
        return  # Не наш чат

    # Проверить есть ли активная пробная подписка
    user = await db.get_user(user_id)
    if not user:
        return

    sub = await db.get_active_subscription(user_id)
    if not sub:
        return

    # Проверить — пробный ли тариф
    tariff = await db.get_tariff(sub["tariff_id"])
    if not tariff or not tariff["is_trial"]:
        return

    # Пробный — мьютим
    await mute_user(bot, user_id, chat_index)
