import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
import aiosqlite
import asyncio

import database as db
from config import config
from services.channel import kick_user, mute_user

logger = logging.getLogger(__name__)


def setup_scheduler(scheduler: AsyncIOScheduler, bot: Bot):
    """Зарегистрировать все задачи планировщика."""

    # Каждый час проверять истёкшие подписки
    scheduler.add_job(
        check_expired,
        "interval",
        hours=1,
        args=[bot],
        id="check_expired",
        replace_existing=True
    )

    # Каждый час слать напоминания
    scheduler.add_job(
        send_reminders,
        "interval",
        hours=1,
        args=[bot],
        id="send_reminders",
        replace_existing=True
    )

    # Раз в сутки чистить брошенные онлайн-платежи (юкасса/тинькофф/юмани/крипта),
    # по которым пользователь создал инвойс, но так и не оплатил.
    # Ручные платежи (manual_*) не трогаем — там своя логика через скриншот/админа.
    scheduler.add_job(
        cleanup_stale_payments,
        "interval",
        hours=24,
        id="cleanup_stale_payments",
        replace_existing=True
    )

    logger.info("Scheduler jobs registered")


async def check_expired(bot: Bot):
    """Кикнуть/мьютнуть пользователей с истёкшей подпиской."""
    expired = await db.get_expired_subscriptions()
    if not expired:
        return

    action = await db.get_setting("expire_action", "kick")
    logger.info(f"Processing {len(expired)} expired subscriptions, action={action}")

    for sub in expired:
        user_id = sub["user_id"]
        try:
            # Уведомить пользователя
            expire_text = await db.get_setting(
                "expire_text",
                "😔 Твоя подписка закончилась.\nЧтобы продолжить — оформи новую: /start"
            )
            await bot.send_message(user_id, expire_text)
        except Exception:
            pass

        # Кик или мьют
        if action == "kick":
            await kick_user(bot, user_id)
        else:
            await mute_user(bot, user_id)

        # Деактивировать подписку в БД
        await db.deactivate_subscription(sub["id"])
        logger.info(f"Processed expired sub for user {user_id}: {action}")

        await asyncio.sleep(0.5)  # защита от flood control Telegram


async def send_reminders(bot: Bot):
    """Напомнить пользователям об истечении подписки."""
    for days in config.REMINDER_DAYS:
        subs = await db.get_expiring_subscriptions(days)
        for sub in subs:
            try:
                day_word = _day_word(days)
                await bot.send_message(
                    sub["user_id"],
                    f"⏰ <b>Напоминание</b>\n\n"
                    f"Твоя подписка истекает через <b>{days} {day_word}</b>!\n\n"
                    f"Продли сейчас, чтобы не потерять доступ: /start",
                    parse_mode="HTML"
                )
                logger.info(f"Sent {days}d reminder to user {sub['user_id']}")
            except Exception as e:
                logger.warning(f"Could not send reminder to {sub['user_id']}: {e}")


async def cleanup_stale_payments():
    """
    Перевести в 'expired' брошенные онлайн-платежи (yukassa/tinkoff/yoomoney/nowpayments),
    которые провисели в 'pending' больше 24 часов без подтверждения по вебхуку.
    Ручные (manual_*) платежи не трогаем — там своя логика через скриншот/админа.
    """
    async with aiosqlite.connect(config.DB_PATH) as dbc:
        cursor = await dbc.execute(
            "UPDATE payments SET status = 'expired' "
            "WHERE status = 'pending' "
            "AND method NOT LIKE 'manual%' "
            "AND datetime(created_at) < datetime('now', '-24 hours')"
        )
        await dbc.commit()
        count = cursor.rowcount

    if count:
        logger.info(f"Cleaned up {count} stale online payment(s) → expired")


def _day_word(days: int) -> str:
    if days == 1:
        return "день"
    elif days in (2, 3, 4):
        return "дня"
    else:
        return "дней"
