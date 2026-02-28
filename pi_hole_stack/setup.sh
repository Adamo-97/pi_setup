#!/usr/bin/env bash
# =============================================================
# pi_hole_stack — Setup Script
# =============================================================
# Raspberry Pi 5 / ARM64 setup for Pi-hole + Unbound.
# Run once after cloning: chmod +x setup.sh && ./setup.sh
# =============================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
info()  { echo -e "${CYAN}[INFO]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# -----------------------------------------------------------
# 1. Pre-flight checks
# -----------------------------------------------------------
log "Running pre-flight checks..."

if ! command -v docker &> /dev/null; then
    error "Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    warn "Log out and back in for Docker group to take effect, then re-run this script."
    exit 1
fi
log "Docker: $(docker --version)"

if ! docker compose version &> /dev/null 2>&1; then
    error "Docker Compose plugin not found."
    sudo apt-get install -y docker-compose-plugin
fi
log "Docker Compose: $(docker compose version --short)"

# -----------------------------------------------------------
# 2. Resolve port 53 conflicts (systemd-resolved)
# -----------------------------------------------------------
if ss -lntu | grep -q ':53 '; then
    warn "Port 53 is already in use!"

    if systemctl is-active --quiet systemd-resolved 2>/dev/null; then
        warn "systemd-resolved is binding port 53. Disabling stub listener..."
        sudo mkdir -p /etc/systemd/resolved.conf.d
        sudo tee /etc/systemd/resolved.conf.d/pihole.conf > /dev/null <<EOF
[Resolve]
DNSStubListener=no
EOF
        sudo systemctl restart systemd-resolved
        # Point /etc/resolv.conf to real nameserver temporarily
        sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
        log "systemd-resolved stub listener disabled"
    else
        error "Something else is using port 53. Check: sudo ss -lntp | grep :53"
        error "Stop the conflicting service before proceeding."
        exit 1
    fi
else
    log "Port 53 is available"
fi

# -----------------------------------------------------------
# 3. Static IP check
# -----------------------------------------------------------
HOST_IP=$(hostname -I | awk '{print $1}')
log "Detected host IP: $HOST_IP"

# Check if IP looks like DHCP-assigned (heuristic)
if ip addr show | grep -q "dynamic"; then
    warn "Your IP appears to be DHCP-assigned."
    warn "For reliable DNS, set a static IP. See README.md for instructions."
fi

# -----------------------------------------------------------
# 4. .env file
# -----------------------------------------------------------
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    log "Creating .env from template..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    # Auto-fill HOST_IP
    sed -i "s|HOST_IP=192.168.1.100|HOST_IP=$HOST_IP|g" "$SCRIPT_DIR/.env"
    warn "Edit .env with your desired PIHOLE_PASSWORD: nano .env"
else
    log ".env already exists"
fi

# -----------------------------------------------------------
# 5. Create supporting directories
# -----------------------------------------------------------
log "Ensuring directory structure..."
mkdir -p "$SCRIPT_DIR/unbound"
mkdir -p "$SCRIPT_DIR/pihole"

# -----------------------------------------------------------
# 6. Pull images
# -----------------------------------------------------------
log "Pulling Docker images (ARM64)..."
docker compose pull

# -----------------------------------------------------------
# 7. Start containers
# -----------------------------------------------------------
log "Starting Pi-hole + Unbound..."
docker compose up -d

# Wait for healthy
log "Waiting for containers to become healthy..."
for i in {1..30}; do
    if docker inspect --format='{{.State.Health.Status}}' unbound 2>/dev/null | grep -q "healthy"; then
        log "Unbound is healthy"
        break
    fi
    sleep 2
done

sleep 5
if docker ps --filter "name=pihole" --filter "status=running" -q | grep -q .; then
    log "Pi-hole is running"
else
    error "Pi-hole failed to start. Check: docker compose logs pihole"
    exit 1
fi

# -----------------------------------------------------------
# 8. Install gravity update cron job
# -----------------------------------------------------------
CRON_SCRIPT="$SCRIPT_DIR/update-gravity.sh"
if [ -f "$CRON_SCRIPT" ]; then
    chmod +x "$CRON_SCRIPT"

    # Add weekly cron (Sunday 3:00 AM) if not already present
    CRON_LINE="0 3 * * 0 $CRON_SCRIPT >> /var/log/pihole-gravity-update.log 2>&1"
    if ! crontab -l 2>/dev/null | grep -qF "$CRON_SCRIPT"; then
        (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
        log "Cron job installed: weekly gravity update (Sunday 3:00 AM)"
    else
        log "Gravity update cron already installed"
    fi
fi

# -----------------------------------------------------------
# 9. Verify DNS resolution
# -----------------------------------------------------------
log "Testing DNS resolution..."
if docker exec pihole dig @127.0.0.1 cloudflare.com +short &> /dev/null; then
    log "DNS resolution working!"
else
    warn "DNS test failed — Pi-hole may still be initializing. Try again in 30s."
fi

# -----------------------------------------------------------
# 10. Summary
# -----------------------------------------------------------
WEB_PORT=$(grep -oP 'PIHOLE_WEB_PORT=\K.*' "$SCRIPT_DIR/.env" 2>/dev/null || echo "8080")
PIHOLE_PASS=$(grep -oP 'PIHOLE_PASSWORD=\K.*' "$SCRIPT_DIR/.env" 2>/dev/null || echo "(check .env)")

echo ""
log "============================================"
log "  pi_hole_stack setup complete!"
log "============================================"
echo ""
info "  Dashboard:  http://$HOST_IP:$WEB_PORT/admin"
info "  Password:   $PIHOLE_PASS"
info "  DNS Server: $HOST_IP (port 53)"
echo ""
echo "  Next steps:"
echo "  1. Edit .env if you haven't set a password:"
echo "     nano $SCRIPT_DIR/.env"
echo "     docker compose up -d  # to apply changes"
echo ""
echo "  2. Set your router's DNS to: $HOST_IP"
echo "     (See README.md for detailed router instructions)"
echo ""
echo "  3. Test from any device:"
echo "     nslookup google.com $HOST_IP"
echo ""
echo "  4. Verify ad blocking:"
echo "     nslookup ads.google.com $HOST_IP"
echo "     (Should return 0.0.0.0)"
echo ""
