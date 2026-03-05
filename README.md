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
