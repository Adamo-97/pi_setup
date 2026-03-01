#!/usr/bin/env bash
# ============================================================================
# cloudflare-status.sh — Cloudflare Tunnel Diagnostics
# ============================================================================
# View tunnel connection status, test public endpoints, and troubleshoot.
#
# Usage:
#   ./scripts/cloudflare-status.sh           # Full status & endpoint test
#   ./scripts/cloudflare-status.sh test      # Test all public endpoints
#   ./scripts/cloudflare-status.sh logs      # Tail cloudflared logs
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

DOMAIN="${CLOUDFLARE_DOMAIN:-example.com}"
ACTION="${1:-status}"

# ── Check container is running ─────────────────────────────────────────────
if ! docker inspect --format='{{.State.Running}}' cloudflared 2>/dev/null | grep -q true; then
    echo -e "${RED}[✗]${NC} Cloudflared container is not running."
    echo "    Start it: cd ${PROJECT_DIR} && docker compose up -d cloudflared"
    exit 1
fi

test_endpoint() {
    local subdomain=$1
    local full="${subdomain}.${DOMAIN}"
    local code

    code=$(curl -sf -o /dev/null -w "%{http_code}" --connect-timeout 5 "https://${full}" 2>/dev/null || echo "000")

    if [[ "$code" =~ ^(200|301|302|303|307|308)$ ]]; then
        echo -e "  ${GREEN}✓${NC} https://${full}  (HTTP ${code})"
    elif [[ "$code" == "000" ]]; then
        echo -e "  ${RED}✗${NC} https://${full}  (unreachable)"
    else
        echo -e "  ${YELLOW}?${NC} https://${full}  (HTTP ${code})"
    fi
}

case "$ACTION" in
    status)
        echo ""
        echo "=============================================="
        echo "   Cloudflare Tunnel — Status Report"
        echo "=============================================="
        echo ""

        # Container health
        HEALTH=$(docker inspect --format='{{.State.Health.Status}}' cloudflared 2>/dev/null || echo "unknown")
        if [[ "$HEALTH" == "healthy" ]]; then
            echo -e "  Container:    ${GREEN}Healthy${NC}"
        else
            echo -e "  Container:    ${YELLOW}${HEALTH}${NC}"
        fi

        UPTIME=$(docker inspect --format='{{.State.StartedAt}}' cloudflared 2>/dev/null | cut -d'.' -f1 || echo "N/A")
        echo "  Started:      ${UPTIME}"
        echo "  Domain:       ${DOMAIN}"
        echo ""

        echo "  ── Public Endpoints ──"
        test_endpoint "cloud"
        test_endpoint "dash"
        test_endpoint "status"
        test_endpoint "pihole"
        test_endpoint "yt"
        test_endpoint "tt"
        test_endpoint "ig"
        test_endpoint "x"
        echo ""

        echo "  ── Ingress Rules (from config.yml) ──"
        grep "hostname:" "${PROJECT_DIR}/cloudflared/config.yml" | sed 's/.*hostname: /  /' | grep -v "^$"
        echo ""

        echo "  ── Recent Logs ──"
        docker compose -f "${PROJECT_DIR}/docker-compose.yml" logs --tail=10 cloudflared 2>/dev/null
        echo ""
        ;;

    test)
        echo ""
        echo "  Testing all public endpoints..."
        echo ""
        test_endpoint "cloud"
        test_endpoint "dash"
        test_endpoint "status"
        test_endpoint "pihole"
        test_endpoint "yt"
        test_endpoint "tt"
        test_endpoint "ig"
        test_endpoint "x"
        echo ""
        ;;

    logs)
        docker compose -f "${PROJECT_DIR}/docker-compose.yml" logs -f cloudflared
        ;;

    *)
        echo "Usage: $0 {status|test|logs}"
        echo ""
        echo "  status  — Full status report with endpoint tests"
        echo "  test    — Test all public endpoints"
        echo "  logs    — Tail cloudflared logs"
        exit 1
        ;;
esac
