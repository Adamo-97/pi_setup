#!/usr/bin/env bash
# ============================================================================
# Pi Nextcloud Stack — Setup Script
# ============================================================================
# One-shot installer for Nextcloud + PostgreSQL + Redis + Caddy on RPi 5.
#
# What it does:
#   1. Verifies Docker & Docker Compose
#   2. Detects and validates NVMe mount
#   3. Creates directory structure on NVMe
#   4. Sets correct permissions (www-data UID 33)
#   5. Creates .env from template
#   6. Pulls Docker images (ARM64)
#   7. Starts containers
#   8. Waits for health checks
#   9. Configures Redis caching in Nextcloud
#  10. Installs file-scan cron job
#  11. Prints summary & URLs
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
echo "   Pi Nextcloud Stack — Setup"
echo "   Nextcloud + PostgreSQL + Redis + Caddy"
echo "=============================================="
echo ""

# ── Step 1: Docker Pre-flight ──────────────────────────────────────────────
info "Step 1/11: Checking Docker installation..."

if ! command -v docker &>/dev/null; then
    err "Docker is not installed."
    echo "    Install: curl -fsSL https://get.docker.com | sh"
    echo "    Then:    sudo usermod -aG docker \$USER"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    err "Docker Compose plugin is not installed."
    echo "    Install: sudo apt install docker-compose-plugin"
    exit 1
fi

log "Docker $(docker --version | grep -oP '\d+\.\d+\.\d+') detected"
log "Docker Compose $(docker compose version --short) detected"

# ── Step 2: NVMe Detection ────────────────────────────────────────────────
info "Step 2/11: Checking NVMe mount..."

# Source .env if exists to get NVME_MOUNT
if [[ -f .env ]]; then
    set -a; source .env; set +a
fi

NVME="${NVME_MOUNT:-/mnt/nvme}"

if mountpoint -q "$NVME" 2>/dev/null; then
    NVME_SIZE=$(df -h "$NVME" | awk 'NR==2{print $2}')
    NVME_AVAIL=$(df -h "$NVME" | awk 'NR==2{print $4}')
    log "NVMe mounted at ${NVME} (${NVME_SIZE} total, ${NVME_AVAIL} available)"
elif [[ -d "$NVME" ]]; then
    warn "${NVME} exists but is NOT a mount point."
    warn "This may be using the SD card instead of the NVMe SSD!"
    echo ""
    read -rp "    Continue anyway? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "    Aborting. Mount your NVMe first, then re-run."
        exit 1
    fi
else
    warn "${NVME} does not exist."
    echo ""
    echo "    To mount your NVMe SSD:"
    echo "    1. sudo fdisk -l                      # Find the NVMe device (e.g. /dev/nvme0n1p1)"
    echo "    2. sudo mkdir -p ${NVME}"
    echo "    3. sudo mount /dev/nvme0n1p1 ${NVME}"
    echo "    4. Add to /etc/fstab for auto-mount:"
    echo "       /dev/nvme0n1p1 ${NVME} ext4 defaults,noatime 0 2"
    echo ""
    read -rp "    Create ${NVME} as a regular directory for now? (y/N): " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        sudo mkdir -p "$NVME"
        warn "Created ${NVME} as a regular directory (NOT NVMe-backed)"
    else
        echo "    Aborting. Mount your NVMe first."
        exit 1
    fi
fi

# ── Step 3: Create Directory Structure ─────────────────────────────────────
info "Step 3/11: Creating directory structure on NVMe..."

DIRS=(
    "${NVME}/nextcloud/html"
    "${NVME}/nextcloud/data"
    "${NVME}/nextcloud/db"
    "${NVME}/ai-content/youtube"
    "${NVME}/ai-content/tiktok"
    "${NVME}/ai-content/instagram"
    "${NVME}/ai-content/x"
)

for dir in "${DIRS[@]}"; do
    sudo mkdir -p "$dir"
done

log "Directory structure created (${#DIRS[@]} directories)"

# ── Step 4: Set Permissions ────────────────────────────────────────────────
info "Step 4/11: Setting file permissions..."

# www-data = UID 33, GID 33 (Apache inside Nextcloud container)
sudo chown -R 33:33 "${NVME}/nextcloud/html"
sudo chown -R 33:33 "${NVME}/nextcloud/data"
sudo chown -R 33:33 "${NVME}/ai-content"

# PostgreSQL = UID 999 in the postgres:16-alpine image
sudo chown -R 999:999 "${NVME}/nextcloud/db"

# Ensure group write for ai-content (n8n containers need write access)
sudo chmod -R 2775 "${NVME}/ai-content"

log "Permissions set (www-data:33 for Nextcloud, postgres:999 for DB)"

# ── Step 5: Environment File ──────────────────────────────────────────────
info "Step 5/11: Setting up environment..."

if [[ ! -f .env ]]; then
    cp .env.example .env

    # Auto-detect host IP
    DETECTED_IP=$(hostname -I | awk '{print $1}')
    if [[ -n "$DETECTED_IP" ]]; then
        sed -i "s/HOST_IP=192.168.1.100/HOST_IP=${DETECTED_IP}/" .env
        log "Auto-detected host IP: ${DETECTED_IP}"
    fi

    # Set NVMe path if non-default
    if [[ "$NVME" != "/mnt/nvme" ]]; then
        sed -i "s|NVME_MOUNT=/mnt/nvme|NVME_MOUNT=${NVME}|" .env
    fi

    warn ".env created — you MUST edit it before production use:"
    echo "    nano ${PROJECT_DIR}/.env"
    echo "    → Set POSTGRES_PASSWORD, NEXTCLOUD_ADMIN_PASSWORD"
    echo "    → Set NEXTCLOUD_DOMAIN for external access"
else
    log ".env already exists — skipping"
fi

# Re-source with updated values
set -a; source .env; set +a

# ── Step 6: Check Port Availability ───────────────────────────────────────
info "Step 6/11: Checking port availability..."

PORTS=(
    "${NEXTCLOUD_PORT:-8443}:Nextcloud"
    "${CADDY_HTTP_PORT:-80}:Caddy HTTP"
    "${CADDY_HTTPS_PORT:-443}:Caddy HTTPS"
    "${POSTGRES_PORT:-5437}:PostgreSQL"
)
CONFLICTS=0

for entry in "${PORTS[@]}"; do
    IFS=':' read -r port name <<< "$entry"
    if ss -lntp 2>/dev/null | grep -q ":${port} "; then
        err "Port ${port} (${name}) is already in use!"
        ((CONFLICTS++))
    fi
done

if [[ $CONFLICTS -gt 0 ]]; then
    err "Port conflict(s) detected. Free the ports or change them in .env"
    exit 1
fi

log "All ports available"

# ── Step 7: Pull Docker Images ────────────────────────────────────────────
info "Step 7/11: Pulling Docker images (ARM64)..."
docker compose pull
log "Images pulled successfully"

# ── Step 8: Start Containers ──────────────────────────────────────────────
info "Step 8/11: Starting containers..."
docker compose up -d
log "Containers started"

# ── Step 9: Wait for Health Checks ────────────────────────────────────────
info "Step 9/11: Waiting for Nextcloud to initialize..."
echo "    (first startup can take 2-3 minutes on Pi 5)"

MAX_WAIT=300
ELAPSED=0
INTERVAL=10

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    NC_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' nextcloud 2>/dev/null || echo "starting")

    if [[ "$NC_HEALTH" == "healthy" ]]; then
        log "Nextcloud is healthy!"
        break
    fi

    printf "."
    sleep $INTERVAL
    ((ELAPSED += INTERVAL))
done
echo ""

if [[ $ELAPSED -ge $MAX_WAIT ]]; then
    warn "Timed out waiting for Nextcloud (${MAX_WAIT}s)."
    warn "It may still be initializing. Check: docker compose logs nextcloud"
fi

# ── Step 10: Configure Redis Caching ──────────────────────────────────────
info "Step 10/11: Configuring Redis caching in Nextcloud..."

docker exec -u www-data nextcloud php occ config:system:set memcache.local --value='\OC\Memcache\APCu' 2>/dev/null || true
docker exec -u www-data nextcloud php occ config:system:set memcache.distributed --value='\OC\Memcache\Redis' 2>/dev/null || true
docker exec -u www-data nextcloud php occ config:system:set memcache.locking --value='\OC\Memcache\Redis' 2>/dev/null || true
docker exec -u www-data nextcloud php occ config:system:set redis host --value='redis_nextcloud' 2>/dev/null || true
docker exec -u www-data nextcloud php occ config:system:set redis port --value='6379' --type=integer 2>/dev/null || true

# Set background job mode to cron (uses nextcloud_cron container)
docker exec -u www-data nextcloud php occ background:cron 2>/dev/null || true

# Set default phone region
docker exec -u www-data nextcloud php occ config:system:set default_phone_region --value='SA' 2>/dev/null || true

log "Redis caching and background jobs configured"

# ── Step 11: Install File-Scan Cron ───────────────────────────────────────
info "Step 11/11: Installing file-scan cron job..."

SCAN_SCRIPT="${PROJECT_DIR}/scripts/scan-files.sh"
chmod +x "$SCAN_SCRIPT"
chmod +x "${PROJECT_DIR}/scripts/fix-permissions.sh"

CRON_LINE="*/15 * * * * ${SCAN_SCRIPT} >> /var/log/nextcloud-scan.log 2>&1"

if crontab -l 2>/dev/null | grep -qF "scan-files.sh"; then
    log "File-scan cron already installed — skipping"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    log "Cron installed: file scan every 15 minutes"
fi

# ── Summary ───────────────────────────────────────────────────────────────
HOST="${HOST_IP:-$(hostname -I | awk '{print $1}')}"
DOMAIN="${NEXTCLOUD_DOMAIN:-cloud.example.com}"
NC_PORT="${NEXTCLOUD_PORT:-8443}"

echo ""
echo "=============================================="
echo "   ✅ Pi Nextcloud Stack — Ready!"
echo "=============================================="
echo ""
echo "  ── Access ──"
echo ""
echo "  LAN (direct):     http://${HOST}:${NC_PORT}"
echo "  External (HTTPS): https://${DOMAIN}"
echo "  PostgreSQL:       ${HOST}:${POSTGRES_PORT:-5437}"
echo ""
echo "  Login:  ${NEXTCLOUD_ADMIN_USER:-admin}"
echo "  Pass:   (set in .env)"
echo ""
echo "  ── NVMe Paths ──"
echo ""
echo "  Nextcloud data:   ${NVME}/nextcloud/data"
echo "  AI content:       ${NVME}/ai-content/{youtube,tiktok,instagram,x}"
echo "  Database:         ${NVME}/nextcloud/db"
echo ""
echo "  ── Next Steps ──"
echo ""
echo "  1. Edit .env with real passwords:  nano .env"
echo "  2. For external access:"
echo "     a. Set NEXTCLOUD_DOMAIN in .env"
echo "     b. Point DNS A record → your public IP"
echo "     c. Forward router ports 80,443 → ${HOST}"
echo "     d. docker compose restart caddy_nextcloud"
echo "  3. Install Nextcloud desktop client on your PC"
echo "     → https://nextcloud.com/install/#install-clients"
echo "  4. Fix n8n output permissions after first content run:"
echo "     ./scripts/fix-permissions.sh"
echo ""
echo "  ── Useful Commands ──"
echo ""
echo "  docker compose logs -f nextcloud   # Nextcloud logs"
echo "  docker compose logs -f caddy_nextcloud  # Caddy/SSL logs"
echo "  ./scripts/scan-files.sh            # Force file scan"
echo "  ./scripts/fix-permissions.sh       # Fix AI content perms"
echo ""
