#!/usr/bin/env bash
# ============================================================================
# weekend-batch-notify.sh — Weekend Publishing Approval Notifier
# ============================================================================
# Sends a batched Mattermost notification summarizing queued content from all
# n8n pipelines. Only runs on Saturday (6) and Sunday (0) — silently
# exits on weekdays.
#
# Cron (installed by setup.sh):
#   0 10 * * 6,0  /path/to/weekend-batch-notify.sh
#
# Requires: curl, jq, docker
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

MM_URL="${MATTERMOST_URL:-}"
MM_TOKEN="${MATTERMOST_BOT_TOKEN:-}"
MM_CHANNEL="${MATTERMOST_BATCH_CHANNEL_ID:-${MATTERMOST_CHANNEL_ID:-}}"
DAY_OF_WEEK=$(date +%u)  # 1=Monday ... 6=Saturday, 7=Sunday

# ── Guard: Only run on Saturday (6) or Sunday (7) ──────────────────────────
if [[ "$DAY_OF_WEEK" -lt 6 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Skipping — today is a weekday (day=$DAY_OF_WEEK)"
    exit 0
fi

if [[ -z "$MM_URL" ]] || [[ -z "$MM_TOKEN" ]] || [[ -z "$MM_CHANNEL" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: MATTERMOST_URL, MATTERMOST_BOT_TOKEN, and MATTERMOST_BATCH_CHANNEL_ID must be set in .env"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Weekend batch — collecting pipeline status..."

# ── Collect container status for all content pipelines ─────────────────────
PIPELINES=(
    "n8n_youtube:YouTube:5678"
    "n8n_tiktok:TikTok:5679"
    "n8n_instagram:Instagram:5680"
    "n8n_x:X/Twitter:5681"
)

STATUS_LINES=""
TOTAL_RUNNING=0
TOTAL_STOPPED=0

for entry in "${PIPELINES[@]}"; do
    IFS=':' read -r container label port <<< "$entry"

    # Check if container is running
    if docker inspect --format='{{.State.Running}}' "$container" 2>/dev/null | grep -q true; then
        state=":white_check_mark: Running"
        ((TOTAL_RUNNING++)) || true
    else
        state=":red_circle: Down"
        ((TOTAL_STOPPED++)) || true
    fi

    # Check n8n health endpoint
    if command -v curl &>/dev/null; then
        health=$(curl -sf "http://localhost:${port}/healthz" 2>/dev/null && echo "healthy" || echo "unreachable")
    else
        health="unknown"
    fi

    STATUS_LINES="${STATUS_LINES}\n| **${label}** | ${state} | ${health} |"
done

# ── Check database containers ──────────────────────────────────────────────
DB_CONTAINERS=(
    "postgres_youtube:YouTube DB"
    "postgres_tiktok:TikTok DB"
    "postgres_instagram:Instagram DB"
    "postgres_x:X/Twitter DB"
)

DB_LINES=""
for entry in "${DB_CONTAINERS[@]}"; do
    IFS=':' read -r container label <<< "$entry"
    if docker inspect --format='{{.State.Running}}' "$container" 2>/dev/null | grep -q true; then
        DB_LINES="${DB_LINES}\n| **${label}** | :white_check_mark: Running |"
    else
        DB_LINES="${DB_LINES}\n| **${label}** | :red_circle: Down |"
    fi
done

# ── Check Pi-hole ──────────────────────────────────────────────────────────
if docker inspect --format='{{.State.Running}}' pihole 2>/dev/null | grep -q true; then
    PIHOLE_STATUS=":white_check_mark: Running"
else
    PIHOLE_STATUS=":red_circle: Down"
fi

# ── Build Mattermost message ───────────────────────────────────────────────
DAY_NAME=$(date +%A)
DATE_STR=$(date '+%B %d, %Y')

MESSAGE="### :clipboard: Weekend Status Report — ${DAY_NAME}, ${DATE_STR}

**Content Pipelines (n8n)**

| Pipeline | Status | Health |
|:---------|:-------|:-------|${STATUS_LINES}

---

**Databases**

| Database | Status |
|:---------|:-------|${DB_LINES}

---

**Infrastructure**
- **Pi-hole DNS** — ${PIHOLE_STATUS}
- **Uptime Kuma** — check dashboard for full history

---

:bar_chart: **Summary:** ${TOTAL_RUNNING} pipelines running, ${TOTAL_STOPPED} down
:link: [Open Dashboard](http://${HOST_IP:-192.168.1.100}:3010) | [Uptime Kuma](http://${HOST_IP:-192.168.1.100}:3001)

---
_:robot: Sent by pi_command_center weekend-batch-notify.sh_"

# ── Send to Mattermost ────────────────────────────────────────────────────
# Escape the message for JSON (handle newlines, quotes)
ESCAPED_MESSAGE=$(printf '%s' "$MESSAGE" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")

PAYLOAD="{\"channel_id\": \"${MM_CHANNEL}\", \"message\": ${ESCAPED_MESSAGE}}"

HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer ${MM_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    "${MM_URL}/api/v4/posts")

if [[ "$HTTP_CODE" == "201" ]] || [[ "$HTTP_CODE" == "200" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Weekend batch notification sent to Mattermost (HTTP $HTTP_CODE)"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Mattermost API returned HTTP $HTTP_CODE"
    exit 1
fi
