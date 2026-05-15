from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Awaitable, Any

import database as db


class BanCheckMiddleware(BaseMiddleware):
    """Блокирует все апдейты от забаненных пользователей."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        # Определить user_id из апдейта
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None

        if user_id:
            user = await db.get_user(user_id)
            if user and user["is_banned"]:
                # Молча игнорируем — не отвечаем забаненным
                return

        return await handler(event, data)
