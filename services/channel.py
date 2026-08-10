from aiogram import Bot
from aiogram.types import ChatPermissions
from config import config
import logging

logger = logging.getLogger(__name__)


def get_channel_id(chat_index: int) -> int:
    return config.get_channel_id(chat_index)


async def grant_access(bot: Bot, user_id: int, chat_index: int = 0) -> str:
    channel_id = get_channel_id(chat_index)
    try:
        await bot.restrict_chat_member(
            chat_id=channel_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=False,
                can_add_web_page_previews=True,
                can_send_photos=True,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_audios=False,
                can_send_voice_notes=False,
                can_send_documents=True,
                can_send_polls=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            )
        )
    except Exception:
        pass

    link = await bot.create_chat_invite_link(
        chat_id=channel_id,
        member_limit=1,
        name=f"user_{user_id}"
    )
    return link.invite_link


async def kick_user(bot: Bot, user_id: int, chat_index: int = 0):
    channel_id = get_channel_id(chat_index)
    from datetime import datetime, timedelta
    try:
        await bot.ban_chat_member(
            chat_id=channel_id,
            user_id=user_id,
            until_date=datetime.utcnow() + timedelta(seconds=35)
        )
        logger.info(f"Kicked user {user_id} from channel {chat_index}")
    except Exception as e:
        logger.error(f"Failed to kick user {user_id} from channel {chat_index}: {e}")


async def mute_user(bot: Bot, user_id: int, chat_index: int = 0):
    channel_id = get_channel_id(chat_index)
    try:
        await bot.restrict_chat_member(
            chat_id=channel_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
        )
        logger.info(f"Muted user {user_id} in channel {chat_index}")
    except Exception as e:
        logger.error(f"Failed to mute user {user_id} in channel {chat_index}: {e}")


async def unmute_user(bot: Bot, user_id: int, chat_index: int = 0):
    """Снять мьют — восстановить полный доступ к чату."""
    channel_id = get_channel_id(chat_index)
    try:
        from aiogram.types import ChatPermissions
        await bot.restrict_chat_member(
            chat_id=channel_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=False,
                can_add_web_page_previews=True,
                can_send_photos=True,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_audios=False,
                can_send_voice_notes=False,
                can_send_documents=True,
                can_send_polls=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            )
        )
        logger.info(f"Unmuted user {user_id} in channel {chat_index}")
    except Exception as e:
        logger.error(f"Failed to unmute user {user_id}: {e}")


async def grant_trial_access(bot: Bot, user_id: int, chat_index: int = 0) -> str:
    """
    Выдать пробный доступ — только invite-ссылка.
    Мьют применяется позже через chat_member handler когда юзер вступит.
    """
    channel_id = get_channel_id(chat_index)
    logger.info(f"grant_trial_access: user={user_id} chat_index={chat_index} channel_id={channel_id}")
    link = await bot.create_chat_invite_link(
        chat_id=channel_id,
        member_limit=1,
        name=f"trial_{user_id}"
    )
    logger.info(f"Trial invite link created: {link.invite_link}")
    return link.invite_link
