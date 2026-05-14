from aiogram import Bot
from aiogram.types import ChatPermissions
from config import config
import logging

logger = logging.getLogger(__name__)


async def grant_access(bot: Bot, user_id: int) -> str:
    """
    Выдать доступ пользователю. Сначала пробуем снять мьют (на случай если был мьют),
    затем создаём одноразовую invite-ссылку.
    """
    try:
        # Снять мьют если был
        await bot.restrict_chat_member(
            chat_id=config.CHANNEL_ID,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )
    except Exception:
        pass  # Мог не быть в чате

    try:
        # Одноразовая invite-ссылка
        link = await bot.create_chat_invite_link(
            chat_id=config.CHANNEL_ID,
            member_limit=1,
            name=f"user_{user_id}"
        )
        return link.invite_link
    except Exception as e:
        logger.warning(f"Could not create invite link: {e}")
        # Fallback на статическую ссылку
        if config.CHANNEL_INVITE_LINK:
            return config.CHANNEL_INVITE_LINK
        return "Обратитесь к администратору для получения ссылки."


async def kick_user(bot: Bot, user_id: int):
    """Удалить пользователя из канала/группы."""
    try:
        await bot.ban_chat_member(chat_id=config.CHANNEL_ID, user_id=user_id)
        # Сразу разбанить, чтобы мог вернуться при продлении
        await bot.unban_chat_member(
            chat_id=config.CHANNEL_ID,
            user_id=user_id,
            only_if_banned=True
        )
        logger.info(f"Kicked user {user_id} from channel")
    except Exception as e:
        logger.error(f"Failed to kick user {user_id}: {e}")


async def mute_user(bot: Bot, user_id: int):
    """Заглушить пользователя в группе (не может писать, но остаётся)."""
    try:
        await bot.restrict_chat_member(
            chat_id=config.CHANNEL_ID,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
        )
        logger.info(f"Muted user {user_id} in channel")
    except Exception as e:
        logger.error(f"Failed to mute user {user_id}: {e}")


async def is_member(bot: Bot, user_id: int) -> bool:
    """Проверить, состоит ли пользователь в чате."""
    try:
        member = await bot.get_chat_member(chat_id=config.CHANNEL_ID, user_id=user_id)
        return member.status not in ("left", "kicked")
    except Exception:
        return False
