from pydantic_settings import BaseSettings
from typing import Optional


class Config(BaseSettings):
    # ─── BOT ───────────────────────────────────────────────
    BOT_TOKEN: str = "YOUR_BOT_TOKEN"
    ADMIN_IDS: list[int] = [123456789]
    WEBHOOK_BASE_URL: str = "https://bot.your-domain.com"
    
    # ─── CHANNELS ──────────────────────────────────────────
    CHANNEL_1_ID: int = -1001234567890
    CHANNEL_1_NAME: str = "💎 VIP Чат 1"
    CHANNEL_1_DESCRIPTION: str = "Основной закрытый канал"

    CHANNEL_2_ID: int = -1009876543210
    CHANNEL_2_NAME: str = "🔥 VIP Чат 2"
    CHANNEL_2_DESCRIPTION: str = "Второй закрытый канал"

    # ─── DATABASE ──────────────────────────────────────────
    DB_PATH: str = "data/vipsub.db"

    # ─── PAYMENT: ЮКасса ───────────────────────────────────
    YUKASSA_ENABLED: bool = False
    YUKASSA_SHOP_ID: str = ""
    YUKASSA_SECRET_KEY: str = ""

     # ─── PAYMENT: ЮМани ────────────────────────────────────
    YOOMONEY_ENABLED: bool = False
    YOOMONEY_RECEIVER: str = ""
    YOOMONEY_SECRET: str = ""

    # ─── PAYMENT: Тинькофф ─────────────────────────────────
    TINKOFF_ENABLED: bool = False
    TINKOFF_TERMINAL_KEY: str = ""
    TINKOFF_SECRET_KEY: str = ""

    # ─── PAYMENT: NOWPayments ──────────────────────────────
    NOWPAYMENTS_ENABLED: bool = False
    NOWPAYMENTS_API_KEY: str = ""
    NOWPAYMENTS_IPN_SECRET: str = ""

    # ─── PAYMENT: Ручной перевод ───────────────────────────
    MANUAL_PAYMENT_ENABLED: bool = True

    # ─── SUBSCRIPTION BEHAVIOR ─────────────────────────────
    DEFAULT_EXPIRE_ACTION: str = "kick"
    REMINDER_DAYS: list[int] = [3, 1]

    # ─── SUPPORT ───────────────────────────────────────────────
    SUPPORT_CHAT_ID: Optional[int] = None

    # ─── BOT MESSAGES ──────────────────────────────────────
    WELCOME_TEXT: str = (
        "👋 Привет! Это бот подписки на закрытые каналы.\n\n"
        "Выбери чат и тариф — получи доступ прямо сейчас!"
    )

    def get_channel_id(self, chat_index: int) -> int:
        return self.CHANNEL_1_ID if chat_index == 0 else self.CHANNEL_2_ID

    def get_channel_name(self, chat_index: int) -> str:
        return self.CHANNEL_1_NAME if chat_index == 0 else self.CHANNEL_2_NAME

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


config = Config()
