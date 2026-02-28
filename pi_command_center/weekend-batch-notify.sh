#!/usr/bin/env bash
# ============================================================================
# weekend-batch-notify.sh — Weekend Publishing Approval Notifier
# ============================================================================
# Sends a batched Slack notification summarizing queued content from all
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

SLACK_WEBHOOK="${SLACK_BATCH_WEBHOOK_URL:-}"
DAY_OF_WEEK=$(date +%u)  # 1=Monday ... 6=Saturday, 7=Sunday

# ── Guard: Only run on Saturday (6) or Sunday (7) ──────────────────────────
if [[ "$DAY_OF_WEEK" -lt 6 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Skipping — today is a weekday (day=$DAY_OF_WEEK)"
    exit 0
fi

if [[ -z "$SLACK_WEBHOOK" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: SLACK_BATCH_WEBHOOK_URL not set in .env"
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

STATUS_BLOCKS=""
TOTAL_RUNNING=0
TOTAL_STOPPED=0

for entry in "${PIPELINES[@]}"; do
    IFS=':' read -r container label port <<< "$entry"

    # Check if container is running
    if docker inspect --format='{{.State.Running}}' "$container" 2>/dev/null | grep -q true; then
        state="✅ Running"
        ((TOTAL_RUNNING++)) || true
    else
        state="🔴 Down"
        ((TOTAL_STOPPED++)) || true
    fi

    # Check n8n health endpoint
    workflow_count="N/A"
    if command -v curl &>/dev/null; then
        health=$(curl -sf "http://localhost:${port}/healthz" 2>/dev/null && echo "healthy" || echo "unreachable")
    else
        health="unknown"
    fi

    STATUS_BLOCKS="${STATUS_BLOCKS}• *${label}* — ${state} (health: ${health})\n"
done

# ── Check database containers ──────────────────────────────────────────────
DB_CONTAINERS=(
    "postgres_youtube:YouTube DB"
    "postgres_tiktok:TikTok DB"
    "postgres_instagram:Instagram DB"
    "postgres_x:X/Twitter DB"
)

DB_BLOCKS=""
for entry in "${DB_CONTAINERS[@]}"; do
    IFS=':' read -r container label <<< "$entry"
    if docker inspect --format='{{.State.Running}}' "$container" 2>/dev/null | grep -q true; then
        DB_BLOCKS="${DB_BLOCKS}• *${label}* — ✅ Running\n"
    else
        DB_BLOCKS="${DB_BLOCKS}• *${label}* — 🔴 Down\n"
    fi
done

# ── Check Pi-hole ──────────────────────────────────────────────────────────
if docker inspect --format='{{.State.Running}}' pihole 2>/dev/null | grep -q true; then
    PIHOLE_STATUS="✅ Running"
else
    PIHOLE_STATUS="🔴 Down"
fi

# ── Build Slack message ────────────────────────────────────────────────────
DAY_NAME=$(date +%A)
DATE_STR=$(date '+%B %d, %Y')

PAYLOAD=$(cat <<EOF
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "📋 Weekend Status Report — ${DAY_NAME}, ${DATE_STR}"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Content Pipelines (n8n)*\n${STATUS_BLOCKS}"
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Databases*\n${DB_BLOCKS}"
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Infrastructure*\n• *Pi-hole DNS* — ${PIHOLE_STATUS}\n• *Uptime Kuma* — check dashboard for full history"
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "📊 *Summary:* ${TOTAL_RUNNING} pipelines running, ${TOTAL_STOPPED} down\n🔗 <http://${HOST_IP:-192.168.1.100}:3010|Open Dashboard> | <http://${HOST_IP:-192.168.1.100}:3001|Uptime Kuma>"
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "🤖 Sent by pi_command_center weekend-batch-notify.sh"
        }
      ]
    }
  ]
}
EOF
)

# ── Send to Slack ──────────────────────────────────────────────────────────
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    "$SLACK_WEBHOOK")

if [[ "$HTTP_CODE" == "200" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Weekend batch notification sent to Slack (HTTP $HTTP_CODE)"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Slack webhook returned HTTP $HTTP_CODE"
    exit 1
fi
