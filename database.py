import aiosqlite
import os
from datetime import datetime
from config import config

DB_PATH = config.DB_PATH


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                user_id     INTEGER UNIQUE NOT NULL,
                username    TEXT,
                full_name   TEXT,
                joined_at   TEXT DEFAULT (datetime('now')),
                is_banned   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS tariffs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                days        INTEGER NOT NULL,
                price       REAL NOT NULL,
                currency    TEXT DEFAULT 'RUB',
                is_active   INTEGER DEFAULT 1,
                sort_order  INTEGER DEFAULT 0,
                chat_index  INTEGER DEFAULT 0,
                is_trial    INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                tariff_id   INTEGER NOT NULL,
                starts_at   TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                is_active   INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (tariff_id) REFERENCES tariffs(id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                tariff_id       INTEGER NOT NULL,
                amount          REAL NOT NULL,
                currency        TEXT DEFAULT 'RUB',
                method          TEXT NOT NULL,
                status          TEXT DEFAULT 'pending',
                external_id     TEXT,
                promo_code      TEXT,
                screenshot_file_id  TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                confirmed_at    TEXT,
                confirmed_by    INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS promo_codes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT UNIQUE NOT NULL,
                discount_pct INTEGER DEFAULT 0,
                discount_rub REAL DEFAULT 0,
                uses_left   INTEGER DEFAULT -1,
                uses_total  INTEGER DEFAULT 0,
                valid_until TEXT,
                is_active   INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS pending_join_requests (
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                chat_index  INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS payment_methods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                currency    TEXT NOT NULL,
                details     TEXT NOT NULL,
                is_link     INTEGER DEFAULT 0,
                is_active   INTEGER DEFAULT 1,
                sort_order  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS bot_settings (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL
            );

            -- Default tariffs
            INSERT OR IGNORE INTO tariffs (id, name, description, days, price, sort_order, is_trial)
            VALUES
                (1, '🎁 Пробный',    '1 день бесплатно — только 1 раз',  1,    0, 0, 1),
                (2, '🗓 1 месяц',    '30 дней доступа к каналу',         30,  299, 1, 0),
                (3, '📅 3 месяца',   '90 дней — выгода 15%',             90,  749, 2, 0),
                (4, '📆 6 месяцев',  '180 дней — выгода 25%',           180, 1299, 3, 0),
                (5, '🏆 1 год',      '365 дней — выгода 40%',           365, 2149, 4, 0);

            -- Default settings
            INSERT OR IGNORE INTO bot_settings (key, value) VALUES
                ('expire_action', 'kick'),
                ('welcome_text', '👋 Привет! Выбери тариф и получи доступ.'),
                ('payment_details', '💳 Сбербанк: 4276 1234 5678 9012\n👤 Иван И.\n📌 Укажите ваш Telegram ID');
        """)
        await db.commit()

        # ── Автомиграция: добавить колонки если их нет (безопасно при повторных запусках) ──
        migrations = [
            "ALTER TABLE tariffs ADD COLUMN is_trial INTEGER DEFAULT 0",
            "ALTER TABLE tariffs ADD COLUMN chat_index INTEGER DEFAULT 0",
            "ALTER TABLE subscriptions ADD COLUMN chat_index INTEGER DEFAULT 0",
            "ALTER TABLE payments ADD COLUMN payment_method_id INTEGER DEFAULT NULL",
            "ALTER TABLE promo_codes ADD COLUMN tariff_id INTEGER DEFAULT NULL",
            "ALTER TABLE promo_codes ADD COLUMN chat_index INTEGER DEFAULT NULL",
            "ALTER TABLE promo_codes ADD COLUMN max_uses_per_user INTEGER DEFAULT 1",
        ]
        for sql in migrations:
            try:
                await db.execute(sql)
            except Exception:
                pass  # колонка уже есть
        await db.commit()


# ─── USER ──────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str | None, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
        """, (user_id, username, full_name))
        await db.commit()


async def get_user(user_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()


async def get_all_users() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE is_banned = 0") as cur:
            return await cur.fetchall()


# ─── TARIFFS ───────────────────────────────────────────────────────────────────

async def get_tariffs(chat_index: int | None = None) -> list:
    """Если chat_index указан — только тарифы этого чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if chat_index is not None:
            async with db.execute(
                "SELECT * FROM tariffs WHERE is_active = 1 AND chat_index = ? ORDER BY sort_order",
                (chat_index,)
            ) as cur:
                return await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM tariffs WHERE is_active = 1 ORDER BY sort_order"
            ) as cur:
                return await cur.fetchall()


async def get_tariff(tariff_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,)) as cur:
            return await cur.fetchone()


async def add_tariff(name: str, description: str, days: int, price: float) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tariffs (name, description, days, price) VALUES (?, ?, ?, ?)",
            (name, description, days, price)
        )
        await db.commit()
        return cur.lastrowid


async def update_tariff(tariff_id: int, **kwargs):
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [tariff_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE tariffs SET {fields} WHERE id = ?", values)
        await db.commit()


# ─── SUBSCRIPTIONS ─────────────────────────────────────────────────────────────

async def get_active_subscription(user_id: int, chat_index: int | None = None) -> aiosqlite.Row | None:
    """Если chat_index указан — ищет подписку только для этого чата."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if chat_index is not None:
            async with db.execute("""
                SELECT s.*, t.name as tariff_name, t.chat_index, t.is_trial
                FROM subscriptions s
                JOIN tariffs t ON t.id = s.tariff_id
                WHERE s.user_id = ? AND s.is_active = 1
                  AND datetime(s.expires_at) > datetime('now')
                  AND t.chat_index = ?
                ORDER BY s.expires_at DESC LIMIT 1
            """, (user_id, chat_index)) as cur:
                return await cur.fetchone()
        else:
            async with db.execute("""
                SELECT s.*, t.name as tariff_name, t.chat_index, t.is_trial
                FROM subscriptions s
                JOIN tariffs t ON t.id = s.tariff_id
                WHERE s.user_id = ? AND s.is_active = 1
                  AND datetime(s.expires_at) > datetime('now')
                ORDER BY s.expires_at DESC LIMIT 1
            """, (user_id,)) as cur:
                return await cur.fetchone()


async def create_subscription(user_id: int, tariff_id: int, days: int) -> int:
    now = datetime.utcnow()
    expires = datetime(now.year, now.month, now.day + days
                       if now.day + days <= 28 else now.day,
                       now.hour, now.minute, now.second)
    # Use timedelta to be safe
    from datetime import timedelta
    expires = now + timedelta(days=days)

    async with aiosqlite.connect(DB_PATH) as db:
        # Deactivate old subs
        await db.execute(
            "UPDATE subscriptions SET is_active = 0 WHERE user_id = ?", (user_id,)
        )
        cur = await db.execute("""
            INSERT INTO subscriptions (user_id, tariff_id, starts_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, tariff_id, now.isoformat(), expires.isoformat()))
        await db.commit()
        return cur.lastrowid


async def extend_subscription(user_id: int, days: int):
    """Продлить существующую или создать новую с текущего момента."""
    sub = await get_active_subscription(user_id)
    from datetime import timedelta
    if sub:
        new_exp = datetime.fromisoformat(sub["expires_at"]) + timedelta(days=days)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE subscriptions SET expires_at = ? WHERE id = ?",
                (new_exp.isoformat(), sub["id"])
            )
            await db.commit()
    # else create_subscription должен быть вызван снаружи


async def get_expiring_subscriptions(days_ahead: int) -> list:
    """Подписки, истекающие через ровно days_ahead дней (±1 час)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.*, u.username, u.full_name
            FROM subscriptions s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.is_active = 1
              AND datetime(s.expires_at) BETWEEN
                  datetime('now', ? || ' days', '-1 hour') AND
                  datetime('now', ? || ' days', '+1 hour')
        """, (str(days_ahead), str(days_ahead))) as cur:
            return await cur.fetchall()


async def get_expired_subscriptions() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.*, u.username, u.full_name
            FROM subscriptions s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.is_active = 1
              AND datetime(s.expires_at) <= datetime('now')
        """) as cur:
            return await cur.fetchall()


async def deactivate_subscription(sub_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET is_active = 0 WHERE id = ?", (sub_id,))
        await db.commit()


# ─── PAYMENTS ──────────────────────────────────────────────────────────────────

async def create_payment(user_id: int, tariff_id: int, amount: float,
                         method: str, promo_code: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO payments (user_id, tariff_id, amount, method, promo_code)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, tariff_id, amount, method, promo_code))
        await db.commit()
        return cur.lastrowid


async def get_payment(payment_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)) as cur:
            return await cur.fetchone()


async def get_pending_payments() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT p.*, u.username, u.full_name, t.name as tariff_name, t.days
            FROM payments p
            JOIN users u ON u.user_id = p.user_id
            JOIN tariffs t ON t.id = p.tariff_id
            WHERE p.status = 'pending'
            ORDER BY p.created_at DESC
        """) as cur:
            return await cur.fetchall()


async def confirm_payment(payment_id: int, admin_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE payments SET status = 'confirmed',
            confirmed_at = datetime('now'), confirmed_by = ?
            WHERE id = ?
        """, (admin_id, payment_id))
        await db.commit()


async def reject_payment(payment_id: int, admin_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE payments SET status = 'rejected',
            confirmed_at = datetime('now'), confirmed_by = ?
            WHERE id = ?
        """, (admin_id, payment_id))
        await db.commit()


async def attach_screenshot(payment_id: int, file_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET screenshot_file_id = ? WHERE id = ?",
            (file_id, payment_id)
        )
        await db.commit()


# ─── PROMO CODES ───────────────────────────────────────────────────────────────

async def get_promo(code: str) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM promo_codes
            WHERE code = ? AND is_active = 1
              AND (uses_left = -1 OR uses_left > 0)
              AND (valid_until IS NULL OR datetime(valid_until) > datetime('now'))
        """, (code.upper(),)) as cur:
            return await cur.fetchone()


async def use_promo(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE promo_codes
            SET uses_total = uses_total + 1,
                uses_left = CASE WHEN uses_left > 0 THEN uses_left - 1 ELSE uses_left END
            WHERE code = ?
        """, (code.upper(),))
        await db.commit()


async def create_promo(code: str, discount_pct: int = 0, discount_rub: float = 0,
                       uses_left: int = -1, valid_until: str | None = None,
                       tariff_id: int | None = None, chat_index: int | None = None,
                       max_uses_per_user: int = 1) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO promo_codes
                (code, discount_pct, discount_rub, uses_left, valid_until,
                 tariff_id, chat_index, max_uses_per_user)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (code.upper(), discount_pct, discount_rub, uses_left, valid_until,
              tariff_id, chat_index, max_uses_per_user))
        await db.commit()
        return cur.lastrowid


async def get_user_promo_uses(user_id: int, code: str) -> int:
    """Сколько раз юзер уже активировал этот промокод."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT COUNT(*) as c FROM payments
            WHERE user_id = ? AND promo_code = ? AND status = 'confirmed'
        """, (user_id, code.upper())) as cur:
            row = await cur.fetchone()
            return row["c"]


# ─── SETTINGS ──────────────────────────────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT value FROM bot_settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row["value"] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bot_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()




async def has_used_trial(user_id: int) -> bool:
    """Проверить, использовал ли юзер пробный тариф хоть раз."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT COUNT(*) as c
            FROM subscriptions s
            JOIN tariffs t ON t.id = s.tariff_id
            WHERE s.user_id = ? AND t.is_trial = 1
        """, (user_id,)) as cur:
            row = await cur.fetchone()
            return row["c"] > 0

# ─── STATS ─────────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        total_users = (await (await db.execute("SELECT COUNT(*) as c FROM users")).fetchone())["c"]
        active_subs = (await (await db.execute(
            "SELECT COUNT(*) as c FROM subscriptions WHERE is_active=1 AND datetime(expires_at)>datetime('now')"
        )).fetchone())["c"]
        total_revenue = (await (await db.execute(
            "SELECT COALESCE(SUM(amount), 0) as s FROM payments WHERE status='confirmed'"
        )).fetchone())["s"]
        today_revenue = (await (await db.execute(
            "SELECT COALESCE(SUM(amount), 0) as s FROM payments WHERE status='confirmed' AND date(confirmed_at)=date('now')"
        )).fetchone())["s"]
        pending_count = (await (await db.execute(
            "SELECT COUNT(*) as c FROM payments WHERE status='pending'"
        )).fetchone())["c"]
        return {
            "total_users": total_users,
            "active_subs": active_subs,
            "total_revenue": total_revenue,
            "today_revenue": today_revenue,
            "pending_count": pending_count,
        }


# ─── PAYMENT METHODS ───────────────────────────────────────────────────────────

async def get_payment_methods(currency: str | None = None) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if currency:
            async with db.execute("""
                SELECT * FROM payment_methods
                WHERE is_active = 1 AND currency = ?
                ORDER BY sort_order
            """, (currency,)) as cur:
                return await cur.fetchall()
        else:
            async with db.execute("""
                SELECT * FROM payment_methods
                WHERE is_active = 1
                ORDER BY currency, sort_order
            """) as cur:
                return await cur.fetchall()


async def get_all_payment_methods() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payment_methods ORDER BY currency, sort_order"
        ) as cur:
            return await cur.fetchall()


async def add_payment_method(name: str, currency: str, details: str, is_link: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO payment_methods (name, currency, details, is_link)
            VALUES (?, ?, ?, ?)
        """, (name, currency.upper(), details, is_link))
        await db.commit()
        return cur.lastrowid


async def toggle_payment_method(method_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE payment_methods SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END
            WHERE id = ?
        """, (method_id,))
        await db.commit()


async def delete_payment_method(method_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM payment_methods WHERE id = ?", (method_id,))
        await db.commit()


# ─── PENDING JOIN REQUESTS ─────────────────────────────────────────────────────

async def save_join_request(user_id: int, chat_id: int, chat_index: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO pending_join_requests (user_id, chat_id, chat_index)
            VALUES (?, ?, ?)
        """, (user_id, chat_id, chat_index))
        await db.commit()


async def get_join_request(user_id: int, chat_index: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM pending_join_requests
            WHERE user_id = ? AND chat_index = ?
        """, (user_id, chat_index)) as cur:
            return await cur.fetchone()


async def delete_join_request(user_id: int, chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM pending_join_requests WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        await db.commit()
