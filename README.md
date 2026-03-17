# pi_setup

Raspberry Pi 5 — stack index & operations cheatsheet.

**Tailscale IP:** `100.113.255.62`  
**LAN IP:** `192.168.0.11`

> Use the Tailscale IP from your phone/laptop. Use the LAN IP for container-to-container communication.

---

## Stacks

| Stack | Description | Deployed |
|-------|-------------|----------|
| `pi_hole_stack` | Pi-hole + Unbound — DNS / ad blocking | ✅ Yes |
| `pi_mattermost_stack` | Mattermost + PostgreSQL — approval hub | ✅ Yes |
| `pi_remote_access_stack` | Tailscale (host) + Cloudflared — remote access | ✅ Yes (Tailscale on host, not Docker) |
| `pi_n8n_stack` | n8n (shared instance) — workflow orchestration | ✅ Yes |
| `pi_instagram_stack` | PostgreSQL + Redis — Instagram Reels pipeline | ✅ Yes |
| `pi_command_center` | Homepage + Uptime Kuma — dashboard & alerts | ❌ No |
| `pi_nextcloud_stack` | Nextcloud + PostgreSQL + Redis + Caddy — cloud storage | ❌ No |
| `pi_tiktok_stack` | n8n + PostgreSQL + Redis — TikTok pipeline | ✅ Yes |
| `pi_x_stack` | n8n + PostgreSQL + Redis — X/Twitter pipeline | ❌ No |
| `pi_youtube_stack` | n8n + PostgreSQL + Redis — YouTube pipeline (in progress) | ❌ No |

---

## Web UIs (via Tailscale)

Open these in any browser on a device connected to your Tailscale network:

| Service | URL | Notes |
|---------|-----|-------|
| **n8n** | http://100.113.255.62:5678 | Workflow editor, executions, logs |
| **Mattermost** | http://100.113.255.62:8065 | Pipeline approval channels |
| **Pi-hole** | http://100.113.255.62:8080/admin | DNS dashboard |

---

## Running Containers

```bash
# List all running containers with ports and health
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check a specific container
docker inspect <name> --format '{{.State.Health.Status}}'

# View logs (last 50 lines, follow)
docker logs <name> --tail 50 -f

# Restart a container (re-reads compose file for env changes)
cd ~/pi_setup/<stack_folder> && docker compose up -d

# Stop a stack
cd ~/pi_setup/<stack_folder> && docker compose down

# Shell into a container
docker exec -it <name> sh
```

### Current Containers

| Container | Port | Stack | Purpose |
|-----------|------|-------|---------|
| `n8n` | 5678 (host net) | pi_n8n_stack | Workflow engine |
| `mattermost` | 8065 | pi_mattermost_stack | Approval UI |
| `postgres_mattermost` | internal | pi_mattermost_stack | Mattermost DB |
| `postgres_instagram` | 5435 | pi_instagram_stack | Instagram RAG DB |
| `redis_instagram` | 6381 | pi_instagram_stack | Pipeline cache |
| `pihole` | 53 (DNS), 8080 (web) | pi_hole_stack | Ad blocking |
| `autoheal` | — | pi_hole_stack | Auto-restart unhealthy containers |

---

## Database Access

### Instagram RAG Database

```bash
# Connect via psql on host
docker exec -it postgres_instagram psql -U ig_user -d instagram_rag

# Or from any machine on Tailscale
psql -h 100.113.255.62 -p 5435 -U ig_user -d instagram_rag
# Password: ig_secure_pass_2025
```

**Useful queries:**
```sql
-- Recent scripts
SELECT id, title, status, overall_score, created_at
FROM generated_scripts ORDER BY created_at DESC LIMIT 10;

-- Recent videos
SELECT id, script_id, status, platform, created_at
FROM published_videos ORDER BY created_at DESC LIMIT 10;

-- Budget usage
SELECT * FROM budget_usage ORDER BY created_at DESC LIMIT 10;

-- RAG embeddings count
SELECT source_type, COUNT(*) FROM rag_embeddings GROUP BY source_type;

-- Feedback log (human comments from Mattermost)
SELECT id, feedback_type, feedback_text, source, created_at
FROM feedback_log ORDER BY created_at DESC LIMIT 10;

-- Check all tables
\dt
```

### Mattermost Database

```bash
docker exec -it postgres_mattermost psql -U mm_user -d mattermost
```

---

## n8n Workflow Management

### Access n8n

Open http://100.113.255.62:5678 in your browser (Tailscale required).

### Instagram Pipeline (7-Gate HITL)

**Workflow ID:** `sqViD3E6dz0znM8y`

| Gate | Channel | What Happens |
|------|---------|--------------|
| 0 | #plan | Content plan approval |
| 1 | #news | News sources review |
| 2 | #script | Script + validation scores (must score 90+) |
| 3 | #voiceover | Listen to generated audio (file attached) |
| 4 | #footage | Review downloaded footage (file attached) |
| 5 | #video | Watch assembled video (file attached) |
| 6 | #publish | Confirm publish + attach thumbnail |

### Trigger the Pipeline

```bash
# Manual trigger via webhook
curl -X POST http://192.168.0.11:5678/webhook/instagram-manual

# Check latest executions
curl -s -H "X-N8N-API-KEY: $(grep N8N_API_KEY ~/pi_setup/pi_n8n_stack/.env | cut -d= -f2)" \
  "http://192.168.0.11:5678/api/v1/executions?workflowId=sqViD3E6dz0znM8y&limit=5" \
  | python3 -m json.tool
```

### Update Workflow from JSON

```bash
# Extract API key
N8N_KEY=$(grep N8N_API_KEY ~/pi_setup/pi_n8n_stack/.env | cut -d= -f2)

# Upload updated workflow (strips read-only fields automatically)
cd ~/pi_setup/pi_instagram_stack
python3 -c "
import json
wf = json.load(open('n8n_workflow.json'))
clean = {k: wf[k] for k in ['name','nodes','connections','settings'] if k in wf}
json.dump(clean, open('/tmp/wf_upload.json','w'))
"
curl -s -H "X-N8N-API-KEY: $N8N_KEY" -H "Content-Type: application/json" \
  -X PUT "http://192.168.0.11:5678/api/v1/workflows/sqViD3E6dz0znM8y" \
  -d @/tmp/wf_upload.json

# Activate
curl -s -H "X-N8N-API-KEY: $N8N_KEY" \
  -X POST "http://192.168.0.11:5678/api/v1/workflows/sqViD3E6dz0znM8y/activate"
```

---

## Mattermost

### Web/Desktop

http://100.113.255.62:8065

### Mobile App (Push Notifications)

1. Install **Mattermost** from Play Store / App Store
2. On the login screen tap **"Connect to a server"**
3. Enter: `http://100.113.255.62:8065`
4. Log in with your credentials
5. Push notifications are enabled (mode: `full` via TPNS test server)
6. Make sure **Tailscale is running** on your phone — the app connects via Tailscale IP

> Push notifications use Mattermost's free test push server (push-test.mattermost.com).
> Limit: ~500 notifications/day (plenty for personal use).
> Notifications include the full message text so they work even without server connectivity.

### Channels

| Channel | Purpose |
|---------|---------|
| #plan | Pipeline content plans |
| #news | Scraped news review |
| #script | Script text + quality scores |
| #voiceover | Generated audio files |
| #footage | Downloaded game footage |
| #video | Assembled final videos |
| #publish | Publish confirmations |

---

## Troubleshooting

### Check if a service is down

```bash
# Quick health check
docker ps --format "{{.Names}}: {{.Status}}" | sort

# Detailed health
docker inspect <name> --format '{{json .State.Health}}' | python3 -m json.tool
```

### Restart a stack

```bash
cd ~/pi_setup/pi_mattermost_stack && docker compose up -d
cd ~/pi_setup/pi_n8n_stack && docker compose up -d
cd ~/pi_setup/pi_instagram_stack && docker compose up -d
cd ~/pi_setup/pi_hole_stack && docker compose up -d
```

### Check n8n execution errors

```bash
N8N_KEY=$(grep N8N_API_KEY ~/pi_setup/pi_n8n_stack/.env | cut -d= -f2)

# List recent executions (shows status: success/error/waiting)
curl -s -H "X-N8N-API-KEY: $N8N_KEY" \
  "http://192.168.0.11:5678/api/v1/executions?limit=5" \
  | python3 -c "
import json,sys
for ex in json.load(sys.stdin).get('data',[]):
    print(f'{ex[\"id\"]:>4}  {ex[\"status\"]:>10}  {ex.get(\"startedAt\",\"?\")[:19]}  wf={ex.get(\"workflowId\",\"?\")}')"
```

### View container logs

```bash
docker logs n8n --tail 50                          # n8n
docker logs mattermost --tail 50                   # Mattermost
docker logs postgres_instagram --tail 20           # Instagram DB
docker logs pihole --tail 20                       # Pi-hole
```

### Disk usage

```bash
df -h /opt                    # NVMe SSD (databases & data)
df -h /                       # SD card (OS)
docker system df              # Docker disk usage
```

### Tailscale status

```bash
tailscale status              # Connected devices
tailscale ip -4               # This Pi's Tailscale IP
```

---

## Rebuilding the n8n Container (Python support)

The n8n container uses a custom image (`pi_n8n_stack/Dockerfile`) that adds Python 3
and all pipeline dependencies. Rebuild whenever `pi_n8n_stack/requirements.txt` changes.

```bash
cd /home/adam/pi_setup/pi_n8n_stack
docker compose down
docker compose build   # ~5 min first time (compiles psycopg2 on ARM)
docker compose up -d
```

---

## Quick Reference

```
Tailscale IP:  100.113.255.62
LAN IP:        192.168.0.11

n8n:           http://100.113.255.62:5678
Mattermost:    http://100.113.255.62:8065
Pi-hole:       http://100.113.255.62:8080/admin

Instagram DB:  port 5435  (ig_user / instagram_rag)
Redis:         port 6381
```
