#!/usr/bin/env bash
# ============================================================================
# fix-permissions.sh — Fix AI Content Directory Permissions
# ============================================================================
# The n8n pipeline containers write files as root or as the n8n user.
# Nextcloud (Apache) runs as www-data (UID 33). This script fixes ownership
# so Nextcloud can read, index, and serve those files.
#
# Run this:
#   - After n8n pipelines generate new content
#   - Before syncing to your desktop client
#   - If Nextcloud shows "access denied" on ai-content files
#
# Usage:
#   chmod +x scripts/fix-permissions.sh
#   ./scripts/fix-permissions.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source environment
if [[ -f "${PROJECT_DIR}/.env" ]]; then
    set -a; source "${PROJECT_DIR}/.env"; set +a
fi

NVME="${NVME_MOUNT:-/mnt/nvme}"
AI_DIR="${NVME}/ai-content"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fixing permissions on ${AI_DIR}..."

if [[ ! -d "$AI_DIR" ]]; then
    echo "ERROR: ${AI_DIR} does not exist."
    exit 1
fi

# Count files before
FILE_COUNT=$(find "$AI_DIR" -type f | wc -l)

# Set ownership to www-data (UID 33, GID 33)
sudo chown -R 33:33 "$AI_DIR"

# Set directory permissions: rwxrwsr-x (setgid so new files inherit group)
sudo find "$AI_DIR" -type d -exec chmod 2775 {} \;

# Set file permissions: rw-rw-r--
sudo find "$AI_DIR" -type f -exec chmod 664 {} \;

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fixed permissions for ${FILE_COUNT} files across:"

for platform in youtube tiktok instagram x; do
    if [[ -d "${AI_DIR}/${platform}" ]]; then
        count=$(find "${AI_DIR}/${platform}" -type f | wc -l)
        echo "  ${platform}/: ${count} files"
    fi
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done. Run ./scripts/scan-files.sh to update Nextcloud index."
