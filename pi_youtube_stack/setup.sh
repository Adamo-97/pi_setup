#!/usr/bin/env bash
# ============================================================
# pi_youtube_stack — Raspberry Pi 5 Setup Script
# ============================================================
# Run once after cloning the repo:
#   chmod +x setup.sh && ./setup.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ----- 1. System dependencies -----------------------------------
info "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    docker.io docker-compose \
    libpq-dev gcc \
    curl jq

# ----- 2. Docker permissions ------------------------------------
if ! groups "$USER" | grep -qw docker; then
    info "Adding $USER to docker group (re-login required)..."
    sudo usermod -aG docker "$USER"
    warn "You may need to log out and back in for Docker group to take effect."
fi

# ----- 3. Python virtualenv -------------------------------------
if [ ! -d ".venv" ]; then
    info "Creating Python virtualenv..."
    python3 -m venv .venv
fi

info "Activating virtualenv & installing Python packages..."
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ----- 4. Environment file --------------------------------------
if [ ! -f ".env" ]; then
    info "Creating .env from .env.example..."
    cp .env.example .env
    warn "IMPORTANT: Edit .env and fill in your API keys before running the stack."
else
    info ".env already exists — skipping."
fi

# ----- 5. Output directories ------------------------------------
info "Creating output directories..."
mkdir -p output/audio output/metadata output/thumbnails logs

# ----- 6. Make scripts executable --------------------------------
info "Setting execute permissions on scripts..."
chmod +x scripts/*.py

# ----- 7. Docker Compose up -------------------------------------
info "Starting Docker containers (postgres + n8n)..."
docker-compose up -d

# Wait for Postgres to be ready
info "Waiting for PostgreSQL to become ready..."
MAX_WAIT=60
SECONDS_WAITED=0
until docker-compose exec -T postgres_youtube pg_isready -U yt_user -d youtube_rag -q 2>/dev/null; do
    sleep 2
    SECONDS_WAITED=$((SECONDS_WAITED + 2))
    if [ "$SECONDS_WAITED" -ge "$MAX_WAIT" ]; then
        error "PostgreSQL did not become ready within ${MAX_WAIT}s."
    fi
done
info "PostgreSQL is ready."

# ----- 8. Verify pgvector extension ----------------------------
info "Verifying pgvector extension..."
docker-compose exec -T postgres_youtube \
    psql -U yt_user -d youtube_rag -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';" \
    2>/dev/null | grep -q "0." && info "pgvector extension OK." || warn "pgvector may not be installed — check init.sql."

# ----- Done! ---------------------------------------------------
echo ""
info "========================================="
info "  Setup complete!"
info "========================================="
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your API keys"
echo "    2. Open n8n at http://$(hostname -I | awk '{print $1}'):5678"
echo "    3. Import the n8n workflow from n8n_workflow/workflow.json"
echo ""
echo "  Quick test:"
echo "    source .venv/bin/activate"
echo "    python3 scripts/fetch_game_data.py --type monthly_releases"
echo ""
