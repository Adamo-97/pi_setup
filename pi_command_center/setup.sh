#!/usr/bin/env bash
# ============================================================================
# Pi Command Center — Setup Script
# ============================================================================
# One-shot installer for Homepage + Uptime Kuma on Raspberry Pi 5 (ARM64).
#
# What it does:
#   1. Verifies Docker & Docker Compose are installed
#   2. Creates .env from template
#   3. Validates Homepage config directory
#   4. Pulls Docker images (ARM64)
#   5. Starts containers
#   6. Waits for health checks
#   7. Installs weekend batch cron job
#   8. Prints dashboard URLs
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# ============================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }

echo ""
echo "=============================================="
echo "   Pi Command Center — Setup"
echo "   Homepage + Uptime Kuma"
echo "=============================================="
echo ""

# ── Step 1: Docker Pre-flight ──────────────────────────────────────────────
info "Step 1/8: Checking Docker installation..."

if ! command -v docker &>/dev/null; then
    err "Docker is not installed."
    echo "    Install it with: curl -fsSL https://get.docker.com | sh"
    echo "    Then add your user: sudo usermod -aG docker \$USER"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    err "Docker Compose plugin is not installed."
    echo "    Install it with: sudo apt install docker-compose-plugin"
    exit 1
fi

log "Docker $(docker --version | grep -oP '\d+\.\d+\.\d+') detected"
log "Docker Compose $(docker compose version --short) detected"

# ── Step 2: Environment File ──────────────────────────────────────────────
info "Step 2/8: Setting up environment..."

if [[ ! -f .env ]]; then
    cp .env.example .env

    # Auto-detect host IP
    DETECTED_IP=$(hostname -I | awk '{print $1}')
    if [[ -n "$DETECTED_IP" ]]; then
        sed -i "s/HOST_IP=192.168.1.100/HOST_IP=${DETECTED_IP}/" .env
        log "Auto-detected host IP: ${DETECTED_IP}"
    fi

    warn ".env created from template — edit it to set your Mattermost connection details:"
    echo "    nano ${SCRIPT_DIR}/.env"
else
    log ".env already exists — skipping"
fi

# Source .env for later use
set -a
source .env
set +a

# ── Step 3: Validate Homepage Config ──────────────────────────────────────
info "Step 3/8: Validating Homepage configuration..."

REQUIRED_YAMLS=("settings.yaml" "services.yaml" "widgets.yaml" "bookmarks.yaml" "docker.yaml")
MISSING=0

for yaml in "${REQUIRED_YAMLS[@]}"; do
    if [[ ! -f "homepage/${yaml}" ]]; then
        err "Missing: homepage/${yaml}"
        ((MISSING++))
    fi
done

if [[ $MISSING -gt 0 ]]; then
    err "${MISSING} Homepage config file(s) missing. Cannot continue."
    exit 1
fi

log "All Homepage YAML configs present (${#REQUIRED_YAMLS[@]} files)"

# ── Step 4: Check Port Availability ───────────────────────────────────────
info "Step 4/8: Checking port availability..."

HOMEPAGE_PORT="${HOMEPAGE_PORT:-3010}"
UPTIME_KUMA_PORT="${UPTIME_KUMA_PORT:-3001}"
CONFLICTS=0

for port in "$HOMEPAGE_PORT" "$UPTIME_KUMA_PORT"; do
    if ss -lntp 2>/dev/null | grep -q ":${port} "; then
        err "Port ${port} is already in use!"
        ss -lntp | grep ":${port} " || true
        ((CONFLICTS++))
    fi
done

if [[ $CONFLICTS -gt 0 ]]; then
    err "Port conflict(s) detected. Free the ports or change them in .env"
    exit 1
fi

log "Ports ${HOMEPAGE_PORT} (Homepage) and ${UPTIME_KUMA_PORT} (Uptime Kuma) are available"

# ── Step 5: Pull Docker Images ────────────────────────────────────────────
info "Step 5/8: Pulling Docker images (ARM64)..."
docker compose pull
log "Images pulled successfully"

# ── Step 6: Start Containers ──────────────────────────────────────────────
info "Step 6/8: Starting containers..."
docker compose up -d
log "Containers started"

# ── Step 7: Wait for Health Checks ────────────────────────────────────────
info "Step 7/8: Waiting for services to become healthy..."

MAX_WAIT=120
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    HP_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' homepage 2>/dev/null || echo "starting")
    UK_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' uptime_kuma 2>/dev/null || echo "starting")

    if [[ "$HP_HEALTH" == "healthy" && "$UK_HEALTH" == "healthy" ]]; then
        log "Both services are healthy!"
        break
    fi

    echo -n "."
    sleep $INTERVAL
    ((ELAPSED += INTERVAL))
done

echo ""

if [[ $ELAPSED -ge $MAX_WAIT ]]; then
    warn "Timed out waiting for health checks (${MAX_WAIT}s)."
    warn "Services may still be starting. Check: docker compose logs"
fi

# ── Step 8: Install Weekend Batch Cron ────────────────────────────────────
info "Step 8/8: Installing weekend batch notification cron job..."

BATCH_SCRIPT="${SCRIPT_DIR}/weekend-batch-notify.sh"
chmod +x "$BATCH_SCRIPT"

CRON_LINE="0 10 * * 6,0 ${BATCH_SCRIPT} >> /var/log/pi-command-center-batch.log 2>&1"

if crontab -l 2>/dev/null | grep -qF "weekend-batch-notify.sh"; then
    log "Weekend batch cron already installed — skipping"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    log "Cron installed: Saturday & Sunday at 10:00 AM"
fi

# ── Summary ───────────────────────────────────────────────────────────────
HOST="${HOST_IP:-$(hostname -I | awk '{print $1}')}"

echo ""
echo "=============================================="
echo "   ✅ Pi Command Center — Ready!"
echo "=============================================="
echo ""
echo "  Dashboard:    http://${HOST}:${HOMEPAGE_PORT}"
echo "  Uptime Kuma:  http://${HOST}:${UPTIME_KUMA_PORT}"
echo ""
echo "  ── Next Steps ──"
echo ""
echo "  1. Open Uptime Kuma and create your admin account"
echo "  2. Add monitors for all your services (see README)"
echo "  3. Configure Mattermost webhook in Uptime Kuma settings"
echo "  4. Edit .env to set MATTERMOST_URL, MATTERMOST_BOT_TOKEN,"
echo "     MATTERMOST_CHANNEL_ID, and MATTERMOST_BATCH_CHANNEL_ID"
echo "  5. Customize Homepage: nano homepage/services.yaml"
echo ""
echo "  ── Useful Commands ──"
echo ""
echo "  docker compose logs -f        # Live logs"
echo "  docker compose restart        # Restart all"
echo "  docker compose down           # Stop all"
echo ""
