from pydantic_settings import BaseSettings
from typing import Optional


class Config(BaseSettings):
    # ─── BOT ───────────────────────────────────────────────
    BOT_TOKEN: str = "YOUR_BOT_TOKEN"
    ADMIN_IDS: list[int] = [123456789]          # Telegram user IDs of admins

    # ─── CHANNEL / GROUP ───────────────────────────────────
    CHANNEL_ID: int = -1001234567890             # ID закрытого канала/группы
    CHANNEL_INVITE_LINK: str = ""                # Статическая ссылка (если нужна)

    # ─── DATABASE ──────────────────────────────────────────
    DB_PATH: str = "data/vipsub.db"

    # ─── PAYMENT: ЮКасса ───────────────────────────────────
    YUKASSA_ENABLED: bool = False
    YUKASSA_SHOP_ID: str = ""
    YUKASSA_SECRET_KEY: str = ""

    # ─── PAYMENT: Тинькофф ─────────────────────────────────
    TINKOFF_ENABLED: bool = False
    TINKOFF_TERMINAL_KEY: str = ""
    TINKOFF_SECRET_KEY: str = ""

    # ─── PAYMENT: Ручной перевод ───────────────────────────
    MANUAL_PAYMENT_ENABLED: bool = True
    MANUAL_PAYMENT_DETAILS: str = (
        "💳 Сбербанк: 4276 1234 5678 9012\n"
        "💳 Тинькофф: 4377 7777 8888 9999\n"
        "👤 Получатель: Иван И.\n"
        "📌 В комментарии укажите ваш Telegram ID"
    )

    # ─── SUBSCRIPTION BEHAVIOR ─────────────────────────────
    # Действие при истечении: "kick" | "mute"  (настраивается в /admin settings)
    DEFAULT_EXPIRE_ACTION: str = "kick"

    # За сколько дней слать напоминания
    REMINDER_DAYS: list[int] = [3, 1]

    # ─── BOT MESSAGES ──────────────────────────────────────
    WELCOME_TEXT: str = (
        "👋 Привет! Это бот подписки на закрытый канал.\n\n"
        "Выбери тариф и получи доступ прямо сейчас!"
    )
    PAYMENT_SUCCESS_TEXT: str = (
        "✅ Оплата подтверждена!\n"
        "Держи ссылку на канал: {link}\n\n"
        "Подписка действует до: {expires}"
    )
    SUBSCRIPTION_EXPIRED_TEXT: str = (
        "😔 Твоя подписка закончилась.\n"
        "Чтобы продолжить — оформи новую: /start"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


config = Config()
