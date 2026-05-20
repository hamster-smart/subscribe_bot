# VIPSub Bot

Telegram bot for selling and managing paid subscriptions to private channels or groups.

The bot supports manual and automatic payments, promo codes, subscription reminders, admin moderation, and access management for multiple chats.

## Features

### User features

- View available tariffs and prices
- Buy access with manual payment and screenshot confirmation
- Pay online via YooMoney, YooKassa, Tinkoff, or NOWPayments
- Apply promo codes, including 100% discount promo codes
- Instantly receive access after successful payment
- View current subscription and expiration date
- Receive renewal reminders before subscription expiry

### Admin features

- Admin panel with statistics
- Pending payments queue for manual confirmations
- One-click payment confirmation or rejection
- Export active subscribers by chat to Excel
- User lookup by Telegram ID, username, or name
- Grant, extend, revoke, or reset subscriptions manually
- Ban and unban users
- Broadcast text, photo, or video messages to all users
- Create and manage promo codes
- Create, edit, enable, disable, and delete tariffs
- Manage payment methods and bot settings from Telegram
- Notifications about new paid subscriptions

## Supported payment methods

- Manual bank card / bank transfer
- YooKassa
- Tinkoff
- YooMoney
- NOWPayments (crypto)

## Tech stack

- Python
- aiogram
- SQLite
- aiosqlite
- openpyxl
- Uvicorn / FastAPI-style webhook server for payment callbacks

## Project structure

```text
subscribe_bot/
├── bot.py
├── config.py
├── database.py
├── webhook_server.py
├── handlers/
│   ├── start.py
│   ├── subscription.py
│   ├── payment.py
│   ├── admin.py
│   └── settings.py
├── keyboards/
│   └── inline.py
├── services/
│   ├── channel.py
│   └── scheduler.py
├── data/
│   └── vipsub.db
├── requirements.txt
└── .env.example
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/hamster-smart/subscribe_bot.git
cd subscribe_bot
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

On Windows:

```bash
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
nano .env
```

Set the required values:

- `BOT_TOKEN` — Telegram bot token from [@BotFather](https://t.me/BotFather)
- `ADMIN_IDS` — comma-separated Telegram user IDs of bot admins
- `DB_PATH` — path to SQLite database file
- Channel / chat configuration values
- Payment provider credentials you want to use
- Webhook base URL for payment callbacks

## Basic setup

### 1. Add the bot to your private channel or group as administrator

The bot should have permission to:

- invite users
- manage invite links
- restrict or remove users if you use mute/kick logic

### 2. Start the bot

```bash
python bot.py
```

### 3. Start the webhook server

```bash
uvicorn webhook_server:app --host 0.0.0.0 --port 8080
```

## Payment providers setup

### YooKassa

Set these variables in `.env`:

- `YUKASSA_ENABLED=true`
- `YUKASSA_SHOP_ID=...`
- `YUKASSA_SECRET_KEY=...`

Webhook URL:

```text
https://your-domain.com/webhook/yukassa
```

### Tinkoff

Set these variables in `.env`:

- `TINKOFF_ENABLED=true`
- `TINKOFF_TERMINAL_KEY=...`
- `TINKOFF_SECRET_KEY=...`

Webhook URL:

```text
https://your-domain.com/webhook/tinkoff
```

### YooMoney

Set these variables in `.env`:

- `YOOMONEY_ENABLED=true`
- `YOOMONEY_RECEIVER=...`

Webhook URL:

```text
https://your-domain.com/webhook/yoomoney
```

### NOWPayments

Set these variables in `.env`:

- `NOWPAYMENTS_ENABLED=true`
- `NOWPAYMENTS_API_KEY=...`

Webhook URL:

```text
https://your-domain.com/webhook/nowpayments
```

## Database

SQLite is used as the main database.

Main tables include:

- `users`
- `tariffs`
- `subscriptions`
- `payments`
- `promocodes`
- `paymentmethods`
- `botsettings`

## Admin panel

Open the admin panel with:

```text
/admin
```

From the admin panel you can:

- review statistics
- confirm or reject manual payments
- export subscribers
- search for users
- manage subscriptions
- send broadcasts
- manage promo codes
- edit tariffs
- manage payment methods and settings

## Notes

- The bot can work with multiple chats/channels
- Trial tariffs can be handled separately from paid tariffs
- Access can be granted automatically after successful payment
- Manual payments can be confirmed from the admin panel with screenshot review

## License

This project is licensed under the [MIT License](./LICENSE).  
See the [LICENSE](./LICENSE) file for details.
