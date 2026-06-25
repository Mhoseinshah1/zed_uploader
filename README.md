# zed_uploader

A production-ready Telegram file saver/uploader bot built with Python 3.11+, aiogram 3, PostgreSQL, and Redis.

> **Important:** Uploaded files are **never stored on the server**. Only Telegram `file_id` and metadata are saved in the database. Telegram itself stores the actual file content.

---

## Tech Stack

- Python 3.11+
- [aiogram 3](https://docs.aiogram.dev/) — async Telegram Bot API framework
- PostgreSQL 16 — primary database
- async SQLAlchemy 2 + asyncpg — async ORM
- Alembic — database migrations
- Redis 7 — caching and state management
- Docker + Docker Compose

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

| Variable | Description | Example |
|---|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather | `123456:ABC-DEF...` |
| `BOT_USERNAME` | Bot username without @ | `mybot` |
| `ADMIN_IDS` | JSON array of admin Telegram user IDs | `[123456789]` |
| `DATABASE_URL` | Async PostgreSQL URL | `postgresql+asyncpg://zed:pass@postgres:5432/zed_uploader` |
| `POSTGRES_USER` | PostgreSQL username | `zed` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `zedpass` |
| `POSTGRES_DB` | PostgreSQL database name | `zed_uploader` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `DEFAULT_LANGUAGE` | Default bot language (`fa` or `en`) | `fa` |

---

## Run with Docker Compose (recommended)

```bash
# 1. Copy and fill environment variables
cp .env.example .env
# Edit .env with your values

# 2. Build and start all services
docker compose up -d --build

# 3. Check logs
docker compose logs -f bot
```

This will:
- Start PostgreSQL and Redis
- Wait for them to be healthy
- Run `alembic upgrade head` to apply migrations
- Start the bot with long polling

---

## Local Development (without Docker)

```bash
# 1. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill environment variables
cp .env.example .env
# Edit .env — point DATABASE_URL to your local PostgreSQL

# 4. Run migrations
alembic upgrade head

# 5. Start the bot
python -m bot.main
```

---

## Project Structure

```
bot/
  main.py           — bot entry point, startup/shutdown hooks
  config.py         — settings loaded from environment variables
  database/
    models.py       — SQLAlchemy ORM models
    session.py      — async engine and session factory
  handlers/
    start.py        — /start command handler
  keyboards/        — inline and reply keyboards (future)
  services/         — business logic layer (future)
  middlewares/      — aiogram middlewares (future)
  locales/          — fa.json / en.json message strings
alembic/
  versions/         — migration files
  env.py            — async Alembic environment
docker-compose.yml
Dockerfile
requirements.txt
```

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration after changing models
alembic revision --autogenerate -m "description"

# Rollback one step
alembic downgrade -1
```

---

## Upcoming Features

- File upload/download via `file_id` (no server storage)
- Forced channel join verification
- Admin panel
- Broadcast system
- Per-user language selection
- File password protection
- File expiry and auto-deletion
