#!/usr/bin/env bash
# =============================================================
# pi_n8n_stack — Setup Script
# =============================================================
# Sets up the shared n8n instance that orchestrates all
# content-pipeline workflows (Instagram, TikTok, X, YouTube).
# =============================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()   { echo -e "${GREEN}[N8N-SETUP]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# -----------------------------------------------------------
# 1. Docker check
# -----------------------------------------------------------
if ! command -v docker &> /dev/null; then
    error "Docker not found. Install it first: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

if ! docker compose version &> /dev/null 2>&1; then
    error "Docker Compose not found. Install: sudo apt-get install docker-compose-plugin"
    exit 1
fi

log "Docker: $(docker --version)"
log "Compose: $(docker compose version)"

# -----------------------------------------------------------
# 2. .env file
# -----------------------------------------------------------
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    log "Creating .env from template..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"

    # Generate a random encryption key
    ENC_KEY=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | xxd -p | tr -d '\n' | head -c 64)
    sed -i "s/^N8N_ENCRYPTION_KEY=.*/N8N_ENCRYPTION_KEY=${ENC_KEY}/" "$SCRIPT_DIR/.env"

    warn "Edit .env and set N8N_BASIC_AUTH_PASSWORD before starting!"
else
    log ".env already exists"
fi

# -----------------------------------------------------------
# 3. Create output directories for each pipeline
# -----------------------------------------------------------
STACKS=("pi_instagram_stack" "pi_tiktok_stack" "pi_x_stack" "pi_youtube_stack")
for stack in "${STACKS[@]}"; do
    STACK_DIR="$PARENT_DIR/$stack"
    if [ -d "$STACK_DIR" ]; then
        mkdir -p "$STACK_DIR/output"
        log "Output dir ready: $stack/output"
    else
        warn "Stack not found: $stack (skipping)"
    fi
done

# -----------------------------------------------------------
# 4. Check which pipeline networks exist
# -----------------------------------------------------------
log "Checking pipeline networks..."
NETWORKS=("instagram_stack_net" "tiktok_stack_net" "x_stack_net" "youtube_stack_net")
MISSING=()
for net in "${NETWORKS[@]}"; do
    if docker network inspect "$net" &> /dev/null 2>&1; then
        log "  Network exists: $net"
    else
        MISSING+=("$net")
        warn "  Network missing: $net (start that stack first, or it will be created)"
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    warn "Some pipeline networks don't exist yet."
    warn "n8n will fail to start until those stacks are running."
    warn "Start with the stack you want to deploy first, then start n8n."
    echo ""
    echo "  Tip: To start just the Instagram stack first:"
    echo "    cd $PARENT_DIR/pi_instagram_stack && docker compose up -d"
    echo "    cd $SCRIPT_DIR && docker compose up -d"
fi

# -----------------------------------------------------------
# Done
# -----------------------------------------------------------
echo ""
log "============================================"
log "  pi_n8n_stack setup complete!"
log "============================================"
echo ""
echo "  Next steps:"
echo "  1. Edit .env — set N8N_BASIC_AUTH_PASSWORD"
echo "  2. Start at least one pipeline stack first"
echo "  3. Start n8n:"
echo "       docker compose up -d"
echo "  4. Open http://<pi-ip>:5678"
echo "  5. Import workflow JSONs from each pipeline stack"
echo ""
