#!/usr/bin/env bash
# ============================================================================
# Pi Mattermost Stack — Setup Script
# ============================================================================
# One-shot installer for Mattermost Team Edition + PostgreSQL on RPi 5.
#
# What it does:
#   1. Verifies Docker & Docker Compose
#   2. Detects and validates NVMe mount
#   3. Creates directory structure on NVMe
#   4. Sets correct permissions (UID 2000 — Mattermost default)
#   5. Creates .env from template
#   6. Pulls Docker images (ARM64)
#   7. Starts containers
#   8. Waits for health checks
#   9. Prints Site URL & Tailscale instructions
#
# Usage:
#   chmod +x scripts/setup.sh
#   ./scripts/setup.sh
# ============================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }

echo ""
echo "=============================================="
echo "   Pi Mattermost Stack — Setup"
echo "   Mattermost Team Edition + PostgreSQL 16"
echo "=============================================="
echo ""

# ── Step 1: Docker Pre-flight ──────────────────────────────────────────────
info "Step 1/9: Checking Docker installation..."

if ! command -v docker &>/dev/null; then
    err "Docker is not installed."
    echo "    Install: curl -fsSL https://get.docker.com | sh"
    echo "    Then:    sudo usermod -aG docker \$USER && newgrp docker"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    err "Docker Compose v2 is not installed."
    echo "    Install: sudo apt install docker-compose-plugin"
    exit 1
fi

log "Docker $(docker --version | awk '{print $3}') ready"
log "Docker Compose $(docker compose version --short) ready"

# ── Step 2: NVMe Detection ────────────────────────────────────────────────
info "Step 2/9: Detecting NVMe mount..."

# Default mount or override from env
NVME_MOUNT="${NVME_MOUNT:-/mnt/nvme}"

if mountpoint -q "$NVME_MOUNT" 2>/dev/null; then
    NVME_SIZE=$(df -h "$NVME_MOUNT" | awk 'NR==2{print $2}')
    NVME_AVAIL=$(df -h "$NVME_MOUNT" | awk 'NR==2{print $4}')
    log "NVMe mounted at $NVME_MOUNT (${NVME_SIZE} total, ${NVME_AVAIL} available)"
else
    warn "NVMe not detected at $NVME_MOUNT (not a mountpoint)"
    warn "Will use $NVME_MOUNT as a regular directory — mount NVMe for production use"
fi

# ── Step 3: Directory Structure ───────────────────────────────────────────
info "Step 3/9: Creating Mattermost directories on NVMe..."

DIRS=(
    "$NVME_MOUNT/mattermost/data"
    "$NVME_MOUNT/mattermost/config"
    "$NVME_MOUNT/mattermost/logs"
    "$NVME_MOUNT/mattermost/plugins"
    "$NVME_MOUNT/mattermost/client-plugins"
    "$NVME_MOUNT/mattermost/db"
)

for dir in "${DIRS[@]}"; do
    sudo mkdir -p "$dir"
done

log "Directory structure created"

# ── Step 4: Permissions ──────────────────────────────────────────────────
info "Step 4/9: Setting Mattermost file permissions..."

# Mattermost container runs as UID 2000
sudo chown -R 2000:2000 "$NVME_MOUNT/mattermost/data"
sudo chown -R 2000:2000 "$NVME_MOUNT/mattermost/config"
sudo chown -R 2000:2000 "$NVME_MOUNT/mattermost/logs"
sudo chown -R 2000:2000 "$NVME_MOUNT/mattermost/plugins"
sudo chown -R 2000:2000 "$NVME_MOUNT/mattermost/client-plugins"

log "Ownership set to UID 2000 (mattermost)"

# ── Step 5: Environment File ──────────────────────────────────────────────
info "Step 5/9: Configuring environment..."

if [[ -f .env ]]; then
    warn ".env already exists — skipping (edit manually if needed)"
else
    cp .env.example .env

    # Auto-detect Host IP
    DETECTED_IP=$(hostname -I | awk '{print $1}')
    if [[ -n "$DETECTED_IP" ]]; then
        sed -i "s|HOST_IP=192.168.1.100|HOST_IP=$DETECTED_IP|g" .env
        sed -i "s|MM_SITEURL=http://192.168.1.100:8065|MM_SITEURL=http://$DETECTED_IP:8065|g" .env
        log "Detected Pi IP: $DETECTED_IP"
    fi

    warn "IMPORTANT: Edit .env and set a strong POSTGRES_PASSWORD"
    warn "    nano .env"
fi

# Validate password is not default
source .env
if [[ "${POSTGRES_PASSWORD}" == "changeme_db_password" ]]; then
    err "POSTGRES_PASSWORD is still the default — change it in .env before continuing!"
    echo "    nano .env"
    exit 1
fi

log "Environment configured"

# ── Step 6: Pull Images ──────────────────────────────────────────────────
info "Step 6/9: Pulling Docker images (ARM64)..."

docker compose pull
log "Images pulled successfully"

# ── Step 7: Start Containers ─────────────────────────────────────────────
info "Step 7/9: Starting containers..."

docker compose up -d
log "Containers starting..."

# ── Step 8: Wait for Health Checks ───────────────────────────────────────
info "Step 8/9: Waiting for Mattermost to become healthy..."

TIMEOUT=120
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $TIMEOUT ]]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' mattermost 2>/dev/null || echo "starting")
    if [[ "$STATUS" == "healthy" ]]; then
        log "Mattermost is healthy!"
        break
    fi
    echo -ne "    Waiting... ${ELAPSED}s / ${TIMEOUT}s (status: $STATUS)\r"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [[ $ELAPSED -ge $TIMEOUT ]]; then
    warn "Mattermost did not become healthy within ${TIMEOUT}s"
    warn "Check logs: docker compose logs -f mattermost"
fi

# ── Step 9: Summary ─────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "   Setup Complete!"
echo "=============================================="
echo ""
log "Mattermost Team Edition is running"
echo ""
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │  Web UI:  http://${DETECTED_IP:-$HOST_IP}:${MATTERMOST_PORT:-8065}           │"
echo "  │  API:     http://${DETECTED_IP:-$HOST_IP}:${MATTERMOST_PORT:-8065}/api/v4    │"
echo "  │  PgSQL:   localhost:${POSTGRES_PORT:-5438}                       │"
echo "  └─────────────────────────────────────────────────────┘"
echo ""
info "NEXT STEPS:"
echo "  1. Open http://${DETECTED_IP:-$HOST_IP}:${MATTERMOST_PORT:-8065} in browser"
echo "  2. Create your admin account (first signup = admin)"
echo "  3. Create channels: #pipeline-youtube, #pipeline-tiktok,"
echo "     #pipeline-instagram, #pipeline-x"
echo "  4. Generate 4 Personal Access Tokens for n8n bots"
echo "  5. Install Mattermost app on iOS/Android"
echo "     (push notifications are pre-configured via TPNS)"
echo ""
info "TAILSCALE ACCESS:"
echo "  If Tailscale is running (pi_remote_access_stack):"
echo "    → Access from anywhere: http://100.x.x.x:${MATTERMOST_PORT:-8065}"
echo "    → Update MM_SITEURL in .env to your Tailscale IP"
echo "    → Restart: docker compose restart mattermost"
echo ""
info "See README.md for the full channel & bot setup checklist."
echo ""
