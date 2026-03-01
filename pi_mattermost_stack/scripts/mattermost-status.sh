#!/usr/bin/env bash
# ============================================================================
# Pi Mattermost Stack — Status & Management Script
# ============================================================================
# Usage:
#   ./scripts/mattermost-status.sh           # Full status report
#   ./scripts/mattermost-status.sh health     # Quick health check
#   ./scripts/mattermost-status.sh channels   # List public channels
#   ./scripts/mattermost-status.sh logs       # Tail logs
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

# Load environment
if [[ -f .env ]]; then
    set -a; source .env; set +a
fi

MM_URL="http://localhost:${MATTERMOST_PORT:-8065}"

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }

# ── Status ────────────────────────────────────────────────────────────────
status() {
    echo ""
    echo "=============================================="
    echo "   Pi Mattermost Stack — Status"
    echo "=============================================="
    echo ""

    # Container health
    info "Container Status:"
    for svc in mattermost postgres_mattermost; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "not running")
        UPTIME=$(docker inspect --format='{{.State.StartedAt}}' "$svc" 2>/dev/null || echo "N/A")
        if [[ "$STATUS" == "healthy" ]]; then
            log "$svc: $STATUS (since $UPTIME)"
        elif [[ "$STATUS" == "not running" ]]; then
            err "$svc: $STATUS"
        else
            warn "$svc: $STATUS"
        fi
    done
    echo ""

    # API ping
    info "Mattermost API:"
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "$MM_URL/api/v4/system/ping" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "200" ]]; then
        log "API responding (HTTP $HTTP_CODE)"
        # Server version
        VERSION=$(curl -sf "$MM_URL/api/v4/system/ping" 2>/dev/null | grep -o '"server_version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        info "Server version: $VERSION"
    else
        err "API not responding (HTTP $HTTP_CODE)"
    fi
    echo ""

    # Push notification config
    info "Push Notifications:"
    log "TPNS endpoint: https://push-test.mattermost.com"
    log "Push enabled in container env (MM_EMAILSETTINGS_SENDPUSHNOTIFICATIONS=true)"
    echo ""

    # Disk usage
    info "NVMe Disk Usage (Mattermost):"
    NVME="${NVME_MOUNT:-/mnt/nvme}"
    for dir in data config logs plugins db; do
        if [[ -d "$NVME/mattermost/$dir" ]]; then
            SIZE=$(du -sh "$NVME/mattermost/$dir" 2>/dev/null | awk '{print $1}')
            echo "    $dir: $SIZE"
        fi
    done
    echo ""

    # Tailscale access
    info "Access URLs:"
    DETECTED_IP=$(hostname -I | awk '{print $1}')
    echo "    LAN:       http://${DETECTED_IP}:${MATTERMOST_PORT:-8065}"
    TAILSCALE_IP=$(docker exec tailscale tailscale ip -4 2>/dev/null || echo "N/A")
    if [[ "$TAILSCALE_IP" != "N/A" ]]; then
        echo "    Tailscale: http://${TAILSCALE_IP}:${MATTERMOST_PORT:-8065}"
    else
        echo "    Tailscale: Not available (is pi_remote_access_stack running?)"
    fi
    echo ""
}

# ── Health ────────────────────────────────────────────────────────────────
health() {
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "$MM_URL/api/v4/system/ping" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "200" ]]; then
        log "Mattermost is healthy (HTTP 200)"
    else
        err "Mattermost is NOT healthy (HTTP $HTTP_CODE)"
        exit 1
    fi
}

# ── Channels ──────────────────────────────────────────────────────────────
channels() {
    echo ""
    info "Listing public channels (requires admin token)..."
    echo ""

    if [[ -z "${MM_ADMIN_TOKEN:-}" ]]; then
        warn "MM_ADMIN_TOKEN not set. Export it first:"
        echo "    export MM_ADMIN_TOKEN=your_personal_access_token"
        echo ""
        echo "  Or view channels in the web UI → System Console → Channels"
        exit 1
    fi

    RESPONSE=$(curl -sf -H "Authorization: Bearer $MM_ADMIN_TOKEN" \
        "$MM_URL/api/v4/channels/search" \
        -d '{"term":"pipeline","page":0,"per_page":10}' 2>/dev/null || echo "error")

    if [[ "$RESPONSE" == "error" ]]; then
        err "Failed to query channels API"
        exit 1
    fi

    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    echo ""
}

# ── Logs ──────────────────────────────────────────────────────────────────
logs() {
    docker compose logs -f --tail 50
}

# ── Main ──────────────────────────────────────────────────────────────────
case "${1:-status}" in
    status)   status ;;
    health)   health ;;
    channels) channels ;;
    logs)     logs ;;
    *)
        echo "Usage: $0 {status|health|channels|logs}"
        echo ""
        echo "  status    Full status report (containers, API, disk, URLs)"
        echo "  health    Quick API health check"
        echo "  channels  List pipeline channels (requires MM_ADMIN_TOKEN)"
        echo "  logs      Tail Mattermost + PostgreSQL logs"
        exit 1
        ;;
esac
