#!/usr/bin/env bash
# ============================================================================
# Pi Remote Access Stack — Setup Script
# ============================================================================
# One-shot installer for Tailscale + Cloudflared on Raspberry Pi 5 (ARM64).
#
# What it does:
#   1. Verifies Docker & Docker Compose
#   2. Checks kernel TUN device
#   3. Enables IP forwarding (required for subnet routing)
#   4. Creates .env from template
#   5. Pulls Docker images (ARM64)
#   6. Starts containers
#   7. Waits for Tailscale to authenticate
#   8. Approves subnet routes (instructions)
#   9. Verifies Cloudflare tunnel
#  10. Prints summary
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
echo "   Pi Remote Access Stack — Setup"
echo "   Tailscale (VPN) + Cloudflared (Tunnels)"
echo "=============================================="
echo ""

# ── Step 1: Docker Pre-flight ──────────────────────────────────────────────
info "Step 1/10: Checking Docker installation..."

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

# ── Step 2: TUN Device ────────────────────────────────────────────────────
info "Step 2/10: Checking TUN device..."

if [[ ! -c /dev/net/tun ]]; then
    warn "/dev/net/tun not found — creating it..."
    sudo mkdir -p /dev/net
    sudo mknod /dev/net/tun c 10 200
    sudo chmod 666 /dev/net/tun
    log "TUN device created"
else
    log "TUN device exists at /dev/net/tun"
fi

# Ensure tun module loads on boot
if ! lsmod | grep -q "^tun "; then
    sudo modprobe tun
    echo "tun" | sudo tee -a /etc/modules-load.d/tun.conf >/dev/null 2>&1 || true
    log "TUN kernel module loaded and set to auto-load"
else
    log "TUN kernel module already loaded"
fi

# ── Step 3: IP Forwarding ─────────────────────────────────────────────────
info "Step 3/10: Enabling IP forwarding..."

# IPv4
if [[ "$(sysctl -n net.ipv4.ip_forward)" != "1" ]]; then
    sudo sysctl -w net.ipv4.ip_forward=1
    echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.d/99-tailscale.conf >/dev/null
    log "IPv4 forwarding enabled"
else
    log "IPv4 forwarding already enabled"
fi

# IPv6
if [[ "$(sysctl -n net.ipv6.conf.all.forwarding)" != "1" ]]; then
    sudo sysctl -w net.ipv6.conf.all.forwarding=1
    echo "net.ipv6.conf.all.forwarding=1" | sudo tee -a /etc/sysctl.d/99-tailscale.conf >/dev/null
    log "IPv6 forwarding enabled"
else
    log "IPv6 forwarding already enabled"
fi

# ── Step 4: Environment File ──────────────────────────────────────────────
info "Step 4/10: Setting up environment..."

if [[ ! -f .env ]]; then
    cp .env.example .env

    # Auto-detect host IP
    DETECTED_IP=$(hostname -I | awk '{print $1}')
    if [[ -n "$DETECTED_IP" ]]; then
        sed -i "s/HOST_IP=192.168.1.100/HOST_IP=${DETECTED_IP}/" .env
        log "Auto-detected host IP: ${DETECTED_IP}"

        # Auto-detect subnet
        DETECTED_SUBNET=$(ip route | grep "proto kernel" | grep "src ${DETECTED_IP}" | awk '{print $1}' | head -1)
        if [[ -n "$DETECTED_SUBNET" ]]; then
            sed -i "s|LAN_SUBNET=192.168.1.0/24|LAN_SUBNET=${DETECTED_SUBNET}|" .env
            log "Auto-detected LAN subnet: ${DETECTED_SUBNET}"
        fi
    fi

    echo ""
    warn ".env created — you MUST edit it before starting:"
    echo ""
    echo "    nano ${PROJECT_DIR}/.env"
    echo ""
    echo "    Required values:"
    echo "    ─────────────────────────────────────────────────────"
    echo "    TAILSCALE_AUTHKEY   → Generate at login.tailscale.com/admin/settings/keys"
    echo "    CLOUDFLARE_TUNNEL_TOKEN → Create at one.dash.cloudflare.com → Tunnels"
    echo "    CLOUDFLARE_DOMAIN  → Your Cloudflare-managed domain"
    echo "    ─────────────────────────────────────────────────────"
    echo ""
    read -rp "    Have you configured .env? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        warn "Edit .env, then re-run this script."
        exit 0
    fi
else
    log ".env already exists"
fi

# Source .env
set -a; source .env; set +a

# ── Step 5: Validate Required Values ──────────────────────────────────────
info "Step 5/10: Validating configuration..."

ERRORS=0

if [[ "${TAILSCALE_AUTHKEY:-}" == *"XXXX"* || -z "${TAILSCALE_AUTHKEY:-}" ]]; then
    err "TAILSCALE_AUTHKEY is not set in .env"
    ((ERRORS++))
fi

if [[ "${CLOUDFLARE_TUNNEL_TOKEN:-}" == *"YOUR_TUNNEL"* || -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
    err "CLOUDFLARE_TUNNEL_TOKEN is not set in .env"
    ((ERRORS++))
fi

if [[ $ERRORS -gt 0 ]]; then
    err "${ERRORS} required value(s) missing. Edit .env and re-run."
    exit 1
fi

log "All required values present"

# ── Step 6: Update Cloudflared Config ─────────────────────────────────────
info "Step 6/10: Updating cloudflared ingress rules..."

HOST="${HOST_IP:-$(hostname -I | awk '{print $1}')}"
DOMAIN="${CLOUDFLARE_DOMAIN:-example.com}"

# Replace placeholder domain and host in config.yml
sed -i "s/example\.com/${DOMAIN}/g" cloudflared/config.yml
sed -i "s/host\.docker\.internal/${HOST}/g" cloudflared/config.yml 2>/dev/null || true

log "Cloudflared config updated for domain: ${DOMAIN}"

# ── Step 7: Pull Docker Images ────────────────────────────────────────────
info "Step 7/10: Pulling Docker images (ARM64)..."
docker compose pull
log "Images pulled successfully"

# ── Step 8: Start Containers ──────────────────────────────────────────────
info "Step 8/10: Starting containers..."
docker compose up -d
log "Containers started"

# ── Step 9: Wait for Tailscale ────────────────────────────────────────────
info "Step 9/10: Waiting for Tailscale to connect..."

MAX_WAIT=60
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    TS_STATUS=$(docker exec tailscale tailscale status --json 2>/dev/null | grep -o '"BackendState":"[^"]*"' | head -1 || echo "")
    if echo "$TS_STATUS" | grep -q "Running"; then
        break
    fi
    printf "."
    sleep $INTERVAL
    ((ELAPSED += INTERVAL))
done
echo ""

if [[ $ELAPSED -ge $MAX_WAIT ]]; then
    warn "Tailscale took longer than expected. Check: docker compose logs tailscale"
else
    TS_IP=$(docker exec tailscale tailscale ip -4 2>/dev/null || echo "unknown")
    log "Tailscale connected! Tailnet IP: ${TS_IP}"
fi

# ── Step 10: Summary ──────────────────────────────────────────────────────
info "Step 10/10: Verifying Cloudflare tunnel..."

sleep 5
CF_STATUS=$(docker inspect --format='{{.State.Running}}' cloudflared 2>/dev/null || echo "false")
if [[ "$CF_STATUS" == "true" ]]; then
    log "Cloudflared container is running"
else
    warn "Cloudflared may still be starting. Check: docker compose logs cloudflared"
fi

echo ""
echo "=============================================="
echo "   ✅ Pi Remote Access Stack — Ready!"
echo "=============================================="
echo ""
echo "  ── Tailscale (Private VPN) ──"
echo ""
echo "  Tailnet IP:      ${TS_IP:-check 'docker exec tailscale tailscale ip'}"
echo "  Hostname:        ${TAILSCALE_HOSTNAME:-pi5}"
echo "  Subnet routing:  ${LAN_SUBNET:-192.168.1.0/24}"
echo ""
echo "  ⚠️  IMPORTANT: Approve the subnet route in the Tailscale admin:"
echo "  → https://login.tailscale.com/admin/machines"
echo "  → Click on '${TAILSCALE_HOSTNAME:-pi5}' → Edit route settings"
echo "  → Enable '${LAN_SUBNET:-192.168.1.0/24}'"
echo ""
echo "  SSH from anywhere:  ssh ${USER}@${TAILSCALE_HOSTNAME:-pi5}"
echo ""
echo "  ── Cloudflare Tunnels (Public Web) ──"
echo ""
echo "  Tunnel:           pi5-tunnel"
echo "  Domain:           ${DOMAIN}"
echo "  Exposed services:"
echo "    cloud.${DOMAIN}   → Nextcloud (:8443)"
echo "    dash.${DOMAIN}    → Homepage  (:3010)"
echo "    status.${DOMAIN}  → Uptime Kuma (:3001)"
echo "    pihole.${DOMAIN}  → Pi-hole   (:8080)"
echo "    yt.${DOMAIN}      → n8n YouTube (:5678)"
echo "    tt.${DOMAIN}      → n8n TikTok  (:5679)"
echo "    ig.${DOMAIN}      → n8n Instagram (:5680)"
echo "    x.${DOMAIN}       → n8n X/Twitter (:5681)"
echo ""
echo "  ── Next Steps ──"
echo ""
echo "  1. Approve subnet route in Tailscale admin console"
echo "  2. Add CNAME records in Cloudflare DNS (if using CLI tunnel)"
echo "  3. Test SSH:  tailscale ssh ${TAILSCALE_HOSTNAME:-pi5}"
echo "  4. Test web:  curl https://cloud.${DOMAIN}"
echo ""
echo "  ── Useful Commands ──"
echo ""
echo "  docker exec tailscale tailscale status     # VPN status"
echo "  docker compose logs -f cloudflared         # Tunnel logs"
echo "  docker compose restart                     # Restart both"
echo ""
