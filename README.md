# zed_uploader

A production-ready Telegram file saver/uploader bot built with Python 3.11+, aiogram 3, PostgreSQL, and Redis.

> **Important:** Uploaded files are **never stored on the server**. Only Telegram `file_id` and metadata are saved in the database. Telegram itself stores the actual file content.

---

## One-Command Install (Ubuntu 20.04 / 22.04 / 24.04)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Mhoseinshah1/zed_uploader/main/install.sh)
```

The installer will:
1. Install Docker and Docker Compose if not already present
2. Clone the repository to `/opt/zed_uploader`
3. Ask for your **Telegram bot token** and **admin user ID** (numeric)
4. Auto-generate all database credentials and secrets
5. Build Docker images and start all services
6. Apply database migrations automatically on first run

On reinstall it asks whether to reconfigure credentials or just update the code.

---

## Update

```bash
bash /opt/zed_uploader/update.sh
```

Or to update from a specific branch:

```bash
INSTALL_BRANCH=mybranch bash /opt/zed_uploader/update.sh
```

---

## Uninstall

```bash
cd /opt/zed_uploader
docker compose down -v        # stop containers and remove volumes
cd /
sudo rm -rf /opt/zed_uploader
```

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

The installer auto-generates all variables. For manual setup:

| Variable | Description | Example |
|---|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather | `123456:ABC-DEF...` |
| `BOT_USERNAME` | Bot username without @ (optional, resolved via API if empty) | `mybot` |
| `ADMIN_IDS` | JSON array of admin Telegram user IDs | `[123456789]` |
| `DATABASE_URL` | Async PostgreSQL URL | `postgresql+asyncpg://user:pass@postgres:5432/zed_uploader` |
| `POSTGRES_USER` | PostgreSQL username | `zed_a1b2c3d4` |
| `POSTGRES_PASSWORD` | PostgreSQL password | auto-generated |
| `POSTGRES_DB` | PostgreSQL database name | `zed_uploader` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `DEFAULT_LANGUAGE` | Default bot language (`fa` or `en`) | `fa` |

---

## Manual Docker Compose Setup

```bash
# 1. Clone the repository
git clone https://github.com/Mhoseinshah1/zed_uploader.git
cd zed_uploader

# 2. Create .env (see table above for required variables)
cp .env.example .env
# Edit .env with your values

# 3. Build and start all services
docker compose up -d --build

# 4. Check logs
docker compose logs -f bot
```

---

## Useful Commands

```bash
cd /opt/zed_uploader

docker compose ps                  # container status
docker compose logs -f bot         # follow bot logs
docker compose restart bot         # restart bot
docker compose down                # stop everything
docker compose up -d --build       # rebuild and start
bash /opt/zed_uploader/update.sh   # update to latest version
```

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
  states.py         — FSM state groups
  database/
    models.py       — SQLAlchemy ORM models
    session.py      — async engine and session factory
  handlers/
    start.py        — /start command + deep link handler
    upload.py       — FSM file save flow
    language.py     — language selection
    admin.py        — admin panel
    menu.py         — main menu buttons
  keyboards/        — reply and inline keyboards
  services/         — business logic (user, file, text, resend)
  middlewares/      — DB session injection middleware
  locales/          — fa.json / en.json message strings
alembic/
  versions/         — migration files
  env.py            — async Alembic environment
install.sh          — one-command Ubuntu installer
update.sh           — update to latest version
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
