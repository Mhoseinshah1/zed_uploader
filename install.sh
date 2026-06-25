#!/usr/bin/env bash
# ==============================================================================
#  zed_uploader — one-command Ubuntu installer
#  Usage: bash <(curl -fsSL https://raw.githubusercontent.com/Mhoseinshah1/zed_uploader/main/install.sh)
# ==============================================================================
set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${RESET}\n"; }

# ── Constants ──────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/Mhoseinshah1/zed_uploader.git"
INSTALL_DIR="/opt/zed_uploader"
BRANCH="${INSTALL_BRANCH:-main}"          # override with INSTALL_BRANCH=mybranch

# ── Root / sudo handling ───────────────────────────────────────────────────────
if [[ $EUID -eq 0 ]]; then
    SUDO=""
else
    if ! command -v sudo &>/dev/null; then
        error "Not running as root and 'sudo' is not installed. Run as root or install sudo first."
    fi
    SUDO="sudo"
fi

# ── OS check ──────────────────────────────────────────────────────────────────
if [[ ! -f /etc/os-release ]]; then
    error "Cannot detect OS. This installer requires Ubuntu 20.04 / 22.04 / 24.04."
fi
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
    error "This installer only supports Ubuntu. Detected: ${ID:-unknown}"
fi
case "${VERSION_ID:-}" in
    20.04|22.04|24.04) success "Ubuntu ${VERSION_ID} detected." ;;
    *) warn "Ubuntu ${VERSION_ID} is not officially tested. Proceeding anyway." ;;
esac

# ── 1. System packages ─────────────────────────────────────────────────────────
header "Installing system packages"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq curl git ca-certificates openssl gnupg lsb-release
success "System packages ready."

# ── 2. Docker ─────────────────────────────────────────────────────────────────
header "Checking Docker"
if ! command -v docker &>/dev/null; then
    info "Docker not found — installing via official script..."
    curl -fsSL https://get.docker.com | $SUDO sh
    $SUDO systemctl enable --now docker
    # Allow current user to use docker without sudo (if not root)
    if [[ $EUID -ne 0 ]]; then
        $SUDO usermod -aG docker "$USER" || true
        warn "Added $USER to 'docker' group. You may need to log out and back in for this to take effect outside this session."
    fi
    success "Docker installed."
else
    success "Docker already installed: $(docker --version)"
fi

# ── 3. Docker Compose plugin ───────────────────────────────────────────────────
header "Checking Docker Compose"
if ! docker compose version &>/dev/null 2>&1; then
    info "Docker Compose plugin not found — installing..."
    COMPOSE_VERSION="v2.27.0"
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  COMPOSE_ARCH="x86_64" ;;
        aarch64) COMPOSE_ARCH="aarch64" ;;
        *)        error "Unsupported architecture: $ARCH" ;;
    esac
    COMPOSE_URL="https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${COMPOSE_ARCH}"
    $SUDO mkdir -p /usr/local/lib/docker/cli-plugins
    $SUDO curl -fsSL "$COMPOSE_URL" -o /usr/local/lib/docker/cli-plugins/docker-compose
    $SUDO chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    success "Docker Compose plugin installed."
else
    success "Docker Compose already installed: $(docker compose version --short)"
fi

# ── 4. Clone or update repository ─────────────────────────────────────────────
header "Setting up repository"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Existing installation found at $INSTALL_DIR — pulling latest code..."
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" checkout "$BRANCH" 2>/dev/null || true
    git -C "$INSTALL_DIR" pull origin "$BRANCH"
    success "Repository updated."
else
    info "Cloning repository into $INSTALL_DIR ..."
    $SUDO git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    # Fix ownership so current user can work inside the dir
    if [[ $EUID -ne 0 ]]; then
        $SUDO chown -R "$USER":"$USER" "$INSTALL_DIR"
    fi
    success "Repository cloned."
fi

cd "$INSTALL_DIR"

# ── 5. .env configuration ──────────────────────────────────────────────────────
header "Environment configuration"

RECONFIGURE=true
if [[ -f "$INSTALL_DIR/.env" ]]; then
    echo -e "${YELLOW}Existing configuration found at $INSTALL_DIR/.env${RESET}"
    read -rp "Reconfigure bot token and admin ID? [y/N]: " RECONF_ANSWER
    case "${RECONF_ANSWER,,}" in
        y|yes) RECONFIGURE=true  ;;
        *)     RECONFIGURE=false ;;
    esac
fi

if [[ "$RECONFIGURE" == true ]]; then
    # ── Ask only two questions ────────────────────────────────────────────────
    echo ""
    while true; do
        read -rp "$(echo -e "${BOLD}Enter your Telegram bot token:${RESET} ")" BOT_TOKEN
        BOT_TOKEN="${BOT_TOKEN// /}"          # strip accidental spaces
        if [[ "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{35,}$ ]]; then
            break
        fi
        warn "Token format looks wrong (expected: 123456789:ABC...). Try again."
    done

    while true; do
        read -rp "$(echo -e "${BOLD}Enter your Telegram admin user ID (numeric):${RESET} ")" ADMIN_ID
        ADMIN_ID="${ADMIN_ID// /}"
        if [[ "$ADMIN_ID" =~ ^[0-9]+$ ]]; then
            break
        fi
        warn "Admin ID must be a number. Try again."
    done

    # ── Auto-generate secrets ─────────────────────────────────────────────────
    POSTGRES_USER="zed_$(openssl rand -hex 4)"
    POSTGRES_PASSWORD="$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 40)"
    POSTGRES_DB="zed_uploader"
    DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"
    REDIS_URL="redis://redis:6379/0"

    info "Writing .env ..."
    cat > "$INSTALL_DIR/.env" <<EOF
# Generated by install.sh — $(date -u '+%Y-%m-%d %H:%M UTC')

# Telegram
BOT_TOKEN=${BOT_TOKEN}
BOT_USERNAME=
ADMIN_IDS=[${ADMIN_ID}]

# Database
DATABASE_URL=${DATABASE_URL}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB}

# Redis
REDIS_URL=${REDIS_URL}

# Bot Settings
DEFAULT_LANGUAGE=fa
EOF
    success ".env created."
else
    info "Keeping existing .env — only updating code and rebuilding containers."
fi

# ── 6. Build and start containers ─────────────────────────────────────────────
header "Building Docker images"
docker compose build --pull

header "Starting services"
# Start postgres and redis first so the healthcheck passes before bot starts
docker compose up -d postgres redis
info "Waiting for postgres to be healthy..."
WAIT=0
until docker compose exec -T postgres pg_isready -U "$(grep POSTGRES_USER "$INSTALL_DIR/.env" | cut -d= -f2)" &>/dev/null; do
    sleep 2
    WAIT=$((WAIT+2))
    if [[ $WAIT -ge 60 ]]; then
        error "Postgres did not become healthy within 60 seconds. Check: docker compose logs postgres"
    fi
done
success "Postgres is healthy."

# Start the bot (docker-compose.yml already runs 'alembic upgrade head && python -m bot.main')
docker compose up -d bot
success "All containers started."

# ── 7. Verify bot is running ───────────────────────────────────────────────────
header "Verifying deployment"
sleep 5
BOT_STATUS=$(docker compose ps --format '{{.Name}} {{.Status}}' 2>/dev/null | grep bot || echo "unknown")
if echo "$BOT_STATUS" | grep -qi "up"; then
    success "Bot container is running."
else
    warn "Bot container may not be running. Check logs:"
    docker compose logs --tail=30 bot || true
fi

# ── 8. Summary ────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║        ✅  Bot installed successfully!               ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Project path:${RESET}  $INSTALL_DIR"
echo -e "  ${BOLD}Branch:${RESET}        $BRANCH"
echo ""
docker compose ps
echo ""
echo -e "${BOLD}Useful commands:${RESET}"
echo -e "  ${CYAN}cd $INSTALL_DIR${RESET}"
echo -e "  ${CYAN}docker compose ps${RESET}                  — container status"
echo -e "  ${CYAN}docker compose logs -f bot${RESET}         — follow bot logs"
echo -e "  ${CYAN}docker compose restart bot${RESET}         — restart bot"
echo -e "  ${CYAN}docker compose down${RESET}                — stop everything"
echo -e "  ${CYAN}docker compose up -d --build${RESET}       — rebuild and start"
echo -e "  ${CYAN}bash $INSTALL_DIR/update.sh${RESET}        — update to latest version"
echo ""
