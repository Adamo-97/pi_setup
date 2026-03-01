#!/usr/bin/env bash
# ============================================================================
# tailscale-status.sh — Tailscale Diagnostics & Management
# ============================================================================
# View Tailscale connection status, manage the node, and troubleshoot.
#
# Usage:
#   ./scripts/tailscale-status.sh           # Full status report
#   ./scripts/tailscale-status.sh reauth    # Re-authenticate (new key)
#   ./scripts/tailscale-status.sh down      # Disconnect from tailnet
#   ./scripts/tailscale-status.sh up        # Reconnect to tailnet
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source environment
if [[ -f "${PROJECT_DIR}/.env" ]]; then
    set -a; source "${PROJECT_DIR}/.env"; set +a
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ACTION="${1:-status}"

# ── Check container is running ─────────────────────────────────────────────
if ! docker inspect --format='{{.State.Running}}' tailscale 2>/dev/null | grep -q true; then
    echo -e "${RED}[✗]${NC} Tailscale container is not running."
    echo "    Start it: cd ${PROJECT_DIR} && docker compose up -d tailscale"
    exit 1
fi

case "$ACTION" in
    status)
        echo ""
        echo "=============================================="
        echo "   Tailscale — Status Report"
        echo "=============================================="
        echo ""

        # Backend state
        STATE=$(docker exec tailscale tailscale status --json 2>/dev/null | grep -o '"BackendState":"[^"]*"' | cut -d'"' -f4)
        if [[ "$STATE" == "Running" ]]; then
            echo -e "  State:        ${GREEN}${STATE}${NC}"
        else
            echo -e "  State:        ${RED}${STATE:-Unknown}${NC}"
        fi

        # IPs
        TS_IPV4=$(docker exec tailscale tailscale ip -4 2>/dev/null || echo "N/A")
        TS_IPV6=$(docker exec tailscale tailscale ip -6 2>/dev/null || echo "N/A")
        echo "  Tailnet IPv4: ${TS_IPV4}"
        echo "  Tailnet IPv6: ${TS_IPV6}"

        # Hostname
        TS_HOST=$(docker exec tailscale tailscale status --json 2>/dev/null | grep -o '"Self":{"ID":"[^"]*","PublicKey":"[^"]*","HostName":"[^"]*"' | grep -o '"HostName":"[^"]*"' | cut -d'"' -f4 || echo "N/A")
        echo "  Hostname:     ${TS_HOST}"
        echo "  SSH:          tailscale ssh ${TS_HOST}"
        echo ""

        # Peer list
        echo "  ── Connected Peers ──"
        docker exec tailscale tailscale status 2>/dev/null | head -20
        echo ""

        # Subnet routes
        echo "  ── Advertised Routes ──"
        echo "  ${LAN_SUBNET:-192.168.1.0/24}"
        echo ""
        echo -e "  ${YELLOW}Approve routes at: https://login.tailscale.com/admin/machines${NC}"
        echo ""
        ;;

    reauth)
        echo -e "${CYAN}[i]${NC} Re-authenticating Tailscale..."

        if [[ -z "${TAILSCALE_AUTHKEY:-}" || "${TAILSCALE_AUTHKEY}" == *"XXXX"* ]]; then
            echo ""
            echo "  Generate a new auth key:"
            echo "  → https://login.tailscale.com/admin/settings/keys"
            echo ""
            read -rp "  Paste new auth key: " NEW_KEY
            if [[ -z "$NEW_KEY" ]]; then
                echo "  Aborted — no key provided."
                exit 1
            fi
        else
            NEW_KEY="${TAILSCALE_AUTHKEY}"
        fi

        docker exec tailscale tailscale up \
            --authkey="$NEW_KEY" \
            --advertise-routes="${LAN_SUBNET:-192.168.1.0/24}" \
            --ssh \
            --accept-dns=false \
            --reset

        echo -e "${GREEN}[✓]${NC} Re-authenticated successfully"
        ;;

    down)
        echo -e "${YELLOW}[!]${NC} Disconnecting Tailscale..."
        docker exec tailscale tailscale down
        echo -e "${GREEN}[✓]${NC} Tailscale disconnected (container still running)"
        ;;

    up)
        echo -e "${CYAN}[i]${NC} Reconnecting Tailscale..."
        docker exec tailscale tailscale up \
            --advertise-routes="${LAN_SUBNET:-192.168.1.0/24}" \
            --ssh \
            --accept-dns=false
        echo -e "${GREEN}[✓]${NC} Tailscale reconnected"
        ;;

    *)
        echo "Usage: $0 {status|reauth|down|up}"
        echo ""
        echo "  status  — Show connection details and peers"
        echo "  reauth  — Re-authenticate with a new auth key"
        echo "  down    — Disconnect from the tailnet"
        echo "  up      — Reconnect to the tailnet"
        exit 1
        ;;
esac
