# pi_setup

Raspberry Pi 5 — stack index.

| Stack | Description | Deployed |
|-------|-------------|----------|
| `pi_hole_stack` | Pi-hole + Unbound — DNS / ad blocking | ✅ Yes |
| `pi_mattermost_stack` | Mattermost + PostgreSQL — approval hub | ✅ Yes |
| `pi_remote_access_stack` | Tailscale (host) + Cloudflared — remote access | ✅ Yes (Tailscale on host, not Docker) |
| `pi_command_center` | Homepage + Uptime Kuma — dashboard & alerts | ❌ No |
| `pi_nextcloud_stack` | Nextcloud + PostgreSQL + Redis + Caddy — cloud storage | ❌ No |
| `pi_instagram_stack` | n8n + PostgreSQL + Redis — Instagram Reels pipeline | ❌ No |
| `pi_tiktok_stack` | n8n + PostgreSQL + Redis — TikTok pipeline | ❌ No |
| `pi_x_stack` | n8n + PostgreSQL + Redis — X/Twitter pipeline | ❌ No |
| `pi_youtube_stack` | n8n + PostgreSQL + Redis — YouTube pipeline (in progress) | ❌ No |

## n8n Workflow Downloads

Start a temporary HTTP server on the Pi, then grab the JSON file:

```bash
# On the Pi — run from /home/adam/pi_setup
cd /home/adam/pi_setup && python3 -m http.server 8899 &
# Kill when done
pkill -f "http.server 8899"
```

| Pipeline | URL |
|----------|-----|
| Instagram | http://192.168.0.11:8899/pi_instagram_stack/n8n_workflow.json |
| TikTok | http://192.168.0.11:8899/pi_tiktok_stack/n8n_workflow.json |
| X/Twitter | http://192.168.0.11:8899/pi_x_stack/n8n_workflow.json |
| YouTube | http://192.168.0.11:8899/pi_youtube_stack/n8n_workflow/workflow.json |

Import in n8n: **Workflows → Import from URL** or download + **Import from File**.

## Rebuilding the n8n Container (Python support)

The n8n container uses a custom image (`pi_n8n_stack/Dockerfile`) that adds Python 3
and all pipeline dependencies. Rebuild whenever `pi_n8n_stack/requirements.txt` changes.

```bash
cd /home/adam/pi_setup/pi_n8n_stack
docker compose down
docker compose build   # ~5 min first time (compiles psycopg2 on ARM)
docker compose up -d
```
