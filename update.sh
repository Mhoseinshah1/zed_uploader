#!/usr/bin/env bash
# ==============================================================================
#  zed_uploader — update script
#  Usage: bash /opt/zed_uploader/update.sh
# ==============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${RESET}\n"; }

INSTALL_DIR="/opt/zed_uploader"
BRANCH="${INSTALL_BRANCH:-main}"

if [[ $EUID -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

[[ -d "$INSTALL_DIR/.git" ]] || error "No installation found at $INSTALL_DIR. Run install.sh first."

header "Pulling latest code"
git -C "$INSTALL_DIR" fetch origin
git -C "$INSTALL_DIR" checkout "$BRANCH" 2>/dev/null || true
git -C "$INSTALL_DIR" pull origin "$BRANCH"
success "Code updated."

cd "$INSTALL_DIR"

header "Rebuilding containers"
$SUDO docker compose build --pull

header "Restarting services"
$SUDO docker compose up -d --remove-orphans
success "Services restarted."

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║        ✅  Update complete!                          ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
$SUDO docker compose ps
