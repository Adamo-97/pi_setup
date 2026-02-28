#!/usr/bin/env bash
# =============================================================
# pi_instagram_stack — Setup Script
# =============================================================
# Raspberry Pi 5 / ARM64 setup for Instagram Reels pipeline.
# Run once after cloning: chmod +x setup.sh && ./setup.sh
# =============================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()   { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# -----------------------------------------------------------
# 1. System packages
# -----------------------------------------------------------
log "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    libpq-dev \
    fonts-dejavu-core \
    fonts-noto-color-emoji \
    curl \
    jq

# -----------------------------------------------------------
# 2. yt-dlp (latest binary for ARM64)
# -----------------------------------------------------------
if ! command -v yt-dlp &> /dev/null; then
    log "Installing yt-dlp..."
    sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
        -o /usr/local/bin/yt-dlp
    sudo chmod a+rx /usr/local/bin/yt-dlp
else
    log "yt-dlp already installed: $(yt-dlp --version)"
fi

# -----------------------------------------------------------
# 3. Python virtual environment
# -----------------------------------------------------------
VENV_DIR="$(dirname "$0")/venv"
if [ ! -d "$VENV_DIR" ]; then
    log "Creating Python venv..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q

# -----------------------------------------------------------
# 4. Python dependencies
# -----------------------------------------------------------
log "Installing Python packages..."
pip install -r "$(dirname "$0")/requirements.txt" -q

# -----------------------------------------------------------
# 5. .env file
# -----------------------------------------------------------
ENV_FILE="$(dirname "$0")/.env"
if [ ! -f "$ENV_FILE" ]; then
    log "Creating .env from template..."
    cp "$(dirname "$0")/.env.example" "$ENV_FILE"
    warn "Edit .env with your API keys before running!"
else
    log ".env already exists"
fi

# -----------------------------------------------------------
# 6. Create output directories
# -----------------------------------------------------------
log "Creating output directories..."
mkdir -p "$(dirname "$0")/output"/{videos,voiceovers,scripts,subtitles,temp}
mkdir -p "$(dirname "$0")/footage"

# -----------------------------------------------------------
# 7. Docker check
# -----------------------------------------------------------
if command -v docker &> /dev/null; then
    log "Docker found: $(docker --version)"
    if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
        log "Docker Compose available"
    else
        warn "Docker Compose not found — install: sudo apt-get install docker-compose-plugin"
    fi
else
    warn "Docker not found — install: curl -fsSL https://get.docker.com | sh"
fi

# -----------------------------------------------------------
# 8. FFmpeg check
# -----------------------------------------------------------
if command -v ffmpeg &> /dev/null; then
    log "FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    error "FFmpeg not found!"
fi

# -----------------------------------------------------------
# 9. Arabic fonts check
# -----------------------------------------------------------
if fc-list | grep -qi "arabic\|noto.*arab\|dejavu"; then
    log "Arabic-compatible fonts found"
else
    warn "No Arabic fonts detected. Installing..."
    sudo apt-get install -y -qq fonts-noto fonts-noto-cjk fonts-arabeyes
fi

# -----------------------------------------------------------
# Done
# -----------------------------------------------------------
echo ""
log "============================================"
log "  pi_instagram_stack setup complete!"
log "============================================"
echo ""
echo "  Next steps:"
echo "  1. Edit .env with your API keys"
echo "  2. Start services:"
echo "     docker compose up -d"
echo "  3. Import n8n workflow:"
echo "     Open http://<pi-ip>:5680"
echo "     Import n8n_workflow.json"
echo "  4. Test pipeline:"
echo "     source venv/bin/activate"
echo "     python -m pipeline.step1_scrape_news"
echo ""
