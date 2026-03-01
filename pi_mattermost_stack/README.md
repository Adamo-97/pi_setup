# pi_mattermost_stack

Central human-in-the-loop approval dashboard for the 4 gaming news content pipelines on Raspberry Pi 5. Deploys **Mattermost Team Edition** (messaging + bot integrations) and **PostgreSQL 16** (database) via Docker Compose. All data stored on the NVMe SSD. Securely accessible over **Tailscale** — no public ports, no port forwarding.

Each n8n pipeline posts pending content to its dedicated channel. Admin reviews on desktop or mobile, approves/rejects, and the pipeline acts on the decision. Mobile push notifications are enabled via the free **TPNS** (Test Push Notification Service).

## Architecture

### C4 Context Diagram

```mermaid
C4Context
    title System Context — pi_mattermost_stack

    Person(admin, "Admin", "Reviews & approves AI-generated gaming news content via Mattermost web/mobile")

    System(mm_stack, "pi_mattermost_stack", "Mattermost Team Edition on Raspberry Pi 5. Human-in-the-loop approval dashboard.")

    System_Ext(yt, "pi_youtube_stack", "n8n pipeline → posts pending content to #pipeline-youtube")
    System_Ext(tt, "pi_tiktok_stack", "n8n pipeline → posts pending content to #pipeline-tiktok")
    System_Ext(ig, "pi_instagram_stack", "n8n pipeline → posts pending content to #pipeline-instagram")
    System_Ext(x, "pi_x_stack", "n8n pipeline → posts pending content to #pipeline-x")
    System_Ext(tailscale, "Tailscale Network", "Encrypted VPN — access from anywhere")
    System_Ext(tpns, "Mattermost TPNS", "Free push notification relay for iOS/Android")

    Rel(yt, mm_stack, "POST /api/v4/posts (Bot Token)")
    Rel(tt, mm_stack, "POST /api/v4/posts (Bot Token)")
    Rel(ig, mm_stack, "POST /api/v4/posts (Bot Token)")
    Rel(x, mm_stack, "POST /api/v4/posts (Bot Token)")
    Rel(admin, tailscale, "WireGuard tunnel")
    Rel(tailscale, mm_stack, "http://100.x.x.x:8065")
    Rel(mm_stack, tpns, "Push notification relay")
    Rel(tpns, admin, "iOS/Android push alert")

    UpdateRelStyle(mm_stack, tpns, $lineColor="orange", $textColor="orange")
    UpdateRelStyle(tpns, admin, $lineColor="orange", $textColor="orange")
```

### C4 Container Diagram

```mermaid
C4Container
    title Container Diagram — pi_mattermost_stack

    Person(admin, "Admin")
    System_Ext(n8n_pipes, "4 n8n Pipelines", "YouTube / TikTok / Instagram / X")
    System_Ext(tailscale, "Tailscale", "VPN access")
    System_Ext(tpns, "TPNS", "push-test.mattermost.com")

    System_Boundary(pi, "Raspberry Pi 5 (Docker)") {
        Container(mattermost, "Mattermost", "mattermost-team-edition:latest", "Messaging server, REST API, WebSocket. Port: 8065")
        ContainerDb(postgres, "PostgreSQL 16", "postgres:16-alpine", "Users, channels, messages, tokens. Port: 5438")
    }

    System_Boundary(nvme, "NVMe SSD (/mnt/nvme/mattermost)") {
        ContainerDb(mm_data, "Mattermost Data", "Filesystem", "/mnt/nvme/mattermost/data — file uploads")
        ContainerDb(mm_config, "Mattermost Config", "Filesystem", "/mnt/nvme/mattermost/config")
        ContainerDb(mm_logs, "Mattermost Logs", "Filesystem", "/mnt/nvme/mattermost/logs")
        ContainerDb(db_data, "PostgreSQL Data", "Filesystem", "/mnt/nvme/mattermost/db")
    }

    Rel(admin, tailscale, "WireGuard")
    Rel(tailscale, mattermost, "HTTP :8065")
    Rel(n8n_pipes, mattermost, "REST API /api/v4/posts")
    Rel(mattermost, postgres, "SQL queries")
    Rel(mattermost, mm_data, "Read/write files")
    Rel(mattermost, mm_config, "Server config")
    Rel(mattermost, mm_logs, "Application logs")
    Rel(postgres, db_data, "Persistent storage")
    Rel(mattermost, tpns, "Push relay (outbound)")
```

### Approval Flow

```mermaid
flowchart LR
    subgraph pipelines["n8n Pipelines (weekday)"]
        YT["YouTube n8n\n:5678"]
        TT["TikTok n8n\n:5679"]
        IG["Instagram n8n\n:5680"]
        X["X n8n\n:5681"]
    end

    subgraph mm["Mattermost :8065"]
        CH_YT["#pipeline-youtube"]
        CH_TT["#pipeline-tiktok"]
        CH_IG["#pipeline-instagram"]
        CH_X["#pipeline-x"]
    end

    subgraph review["Admin Review"]
        WEB["Web UI\n(Tailscale)"]
        MOB["Mobile App\n(TPNS push)"]
    end

    YT -->|Bot Token 1| CH_YT
    TT -->|Bot Token 2| CH_TT
    IG -->|Bot Token 3| CH_IG
    X  -->|Bot Token 4| CH_X

    CH_YT --> WEB
    CH_TT --> WEB
    CH_IG --> WEB
    CH_X --> WEB

    CH_YT --> MOB
    CH_TT --> MOB
    CH_IG --> MOB
    CH_X --> MOB

    WEB -->|✅ Approve / ❌ Reject| pipelines
    MOB -->|✅ Approve / ❌ Reject| pipelines
```

### Traffic Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MATTERMOST APPROVAL PIPELINE                             │
│              Accessible via Tailscale — no public exposure                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  n8n PIPELINES → MATTERMOST                                                │
│  ────────────────────────────                                               │
│  ┌────────────┐  Bot Token   ┌─────────────┐                               │
│  │ YouTube    │─────────────▶│ #pipeline-  │                               │
│  │ n8n :5678  │  POST /api   │  youtube    │                               │
│  ├────────────┤              ├─────────────┤   ┌──────────┐                │
│  │ TikTok    │─────────────▶│ #pipeline-  │──▶│ Admin    │                │
│  │ n8n :5679  │              │  tiktok     │   │ Review   │                │
│  ├────────────┤              ├─────────────┤   │ (web +   │                │
│  │ Instagram │─────────────▶│ #pipeline-  │   │  mobile) │                │
│  │ n8n :5680  │              │  instagram  │   └──────────┘                │
│  ├────────────┤              ├─────────────┤        │                       │
│  │ X/Twitter │─────────────▶│ #pipeline-  │        ▼                       │
│  │ n8n :5681  │              │  x          │  ✅ Approve                    │
│  └────────────┘              └─────────────┘  ❌ Reject                     │
│                                                                             │
│  ADMIN ACCESS (Tailscale VPN)                                               │
│  ────────────────────────────                                               │
│  Work Laptop ──WireGuard──▶ Tailscale Net ──▶ Pi5:8065 (Mattermost)        │
│  Mobile App  ──WireGuard──▶ Tailscale Net ──▶ Pi5:8065 + TPNS push         │
│                                                                             │
│  MOBILE PUSH (TPNS — free)                                                  │
│  ─────────────────────────                                                  │
│  Mattermost ──HTTPS──▶ push-test.mattermost.com ──▶ APNs/FCM ──▶ Phone    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

| Requirement     | Version           | Notes                                     |
| --------------- | ----------------- | ----------------------------------------- |
| Raspberry Pi 5  | ARM64             | 4 GB+ RAM                                 |
| Raspberry Pi OS | Bookworm (64-bit) | Or any Debian-based ARM64 distro          |
| Docker          | 24.0+             | `curl -fsSL https://get.docker.com \| sh` |
| Docker Compose  | v2.20+            | `sudo apt install docker-compose-plugin`  |
| NVMe SSD        | 1 TB              | Mounted at `/mnt/nvme`                    |
| Tailscale       | Running           | Via `pi_remote_access_stack`              |

## Quick Start

```bash
# 1. Clone & enter
git clone https://github.com/Adamo-97/pi_setup.git
cd pi_setup/pi_mattermost_stack

# 2. Configure environment (set a strong DB password)
cp .env.example .env
nano .env

# 3. Run setup
chmod +x scripts/*.sh
./scripts/setup.sh

# 4. Open Mattermost
#    LAN:       http://<pi-ip>:8065
#    Tailscale: http://100.x.x.x:8065

# 5. Follow the Channel & Bot Setup Checklist below
```

## Folder Structure

```
pi_mattermost_stack/
├── docker-compose.yml              # Mattermost + PostgreSQL
├── .env.example                    # Environment variable template
├── .gitignore
├── scripts/
│   ├── setup.sh                    # One-time installer (9 steps)
│   └── mattermost-status.sh       # Diagnostics & management
└── README.md                       # This file

NVMe SSD Layout (/mnt/nvme/mattermost):
├── data/                           # File uploads, attachments
├── config/                         # Server configuration (auto-generated)
├── logs/                           # Application logs
├── plugins/                        # Server plugins
├── client-plugins/                 # Client-side plugins
└── db/                             # PostgreSQL data directory
```

## Configuration

### Environment Variables (`.env`)

| Variable            | Default                     | Description                          |
| ------------------- | --------------------------- | ------------------------------------ |
| `NVME_MOUNT`        | `/mnt/nvme`                 | NVMe SSD mount point                 |
| `TZ`                | `Asia/Riyadh`               | Timezone                             |
| `POSTGRES_DB`       | `mattermost`                | Database name                        |
| `POSTGRES_USER`     | `mm_user`                   | Database user                        |
| `POSTGRES_PASSWORD` | —                           | Database password (**change this!**) |
| `POSTGRES_PORT`     | `5438`                      | Host port for PostgreSQL             |
| `MATTERMOST_PORT`   | `8065`                      | Host port for Mattermost web UI      |
| `MM_SITEURL`        | `http://192.168.1.100:8065` | Site URL (update to Tailscale IP)    |
| `HOST_IP`           | `192.168.1.100`             | Raspberry Pi static IP               |

### Mobile Push Notifications (TPNS)

Push notifications are **pre-configured** in the Docker Compose file. The three environment variables that enable this are:

```yaml
MM_EMAILSETTINGS_SENDPUSHNOTIFICATIONS: "true"
MM_EMAILSETTINGS_PUSHNOTIFICATIONSERVER: "https://push-test.mattermost.com"
MM_EMAILSETTINGS_PUSHNOTIFICATIONCONTENTS: "id_loaded"
```

**What is TPNS?** The Test Push Notification Service is a free relay provided by Mattermost Inc. for Team Edition users. It forwards push notifications to Apple (APNs) and Google (FCM) so you receive alerts on the official Mattermost iOS/Android app.

**Limitations of TPNS:**

- 600 notifications per minute (plenty for a single-user approval workflow)
- No support for id-only push (use `id_loaded` or `generic`)
- Not recommended for >50 users (not a concern here)

**To verify it's working:**

1. Install the Mattermost app on iOS/Android
2. Log in with your server URL (Tailscale IP: `http://100.x.x.x:8065`)
3. Post a message in any channel — you should receive a push notification

### Tailscale Access

This stack runs behind Tailscale from `pi_remote_access_stack`. No public ports or Cloudflare tunnels are needed — this is an **internal approval tool**.

**After Tailscale is running:**

1. Get your Pi's Tailscale IP:

   ```bash
   docker exec tailscale tailscale ip -4
   # → 100.x.x.x
   ```

2. Update `.env`:

   ```
   MM_SITEURL=http://100.x.x.x:8065
   ```

3. Restart Mattermost:

   ```bash
   docker compose restart mattermost
   ```

4. Access from any device on your tailnet:
   - **Desktop:** `http://100.x.x.x:8065`
   - **Mobile app:** Use the same URL when logging in

---

## Channel & Bot Setup Checklist

After the setup script completes and Mattermost is running, follow this step-by-step checklist to configure the approval workflow.

### Step 1: Create the Admin Account

1. Open Mattermost in your browser: `http://<pi-ip>:8065`
2. The **first user to sign up becomes the System Admin**
3. Fill in:
   - **Email:** your email address
   - **Username:** your preferred admin username
   - **Password:** a strong password (16+ characters recommended)
4. Click **Create Account**
5. You'll be prompted to create or join a team → create a team (e.g., `Pi Lab`)

### Step 2: Create the 4 Pipeline Channels

From the Mattermost web UI:

1. Click the **+** button next to "Channels" in the left sidebar
2. Select **Create New Channel**
3. Create each channel with these exact settings:

| Channel Name         | Display Name         | Purpose                                                      |
| -------------------- | -------------------- | ------------------------------------------------------------ |
| `pipeline-youtube`   | Pipeline — YouTube   | Human-in-the-loop approval for YouTube gaming news content   |
| `pipeline-tiktok`    | Pipeline — TikTok    | Human-in-the-loop approval for TikTok gaming news content    |
| `pipeline-instagram` | Pipeline — Instagram | Human-in-the-loop approval for Instagram gaming news content |
| `pipeline-x`         | Pipeline — X/Twitter | Human-in-the-loop approval for X/Twitter gaming news content |

4. Set all channels as **Public** (so bot accounts can post to them)
5. Set the **Header** for each channel to describe the content format:
   - YouTube: `Video titles, descriptions, thumbnails for review`
   - TikTok: `Short-form video scripts and captions for review`
   - Instagram: `Reels, stories, and carousel posts for review`
   - X: `Tweet threads and individual posts for review`

### Step 3: Enable Personal Access Tokens

1. Go to **System Console** (click ☰ → System Console, or navigate to `/admin_console`)
2. Navigate to **Integrations → Integration Management**
3. Ensure these are set to **true** (they should be from the Docker env vars):
   - ✅ Enable Personal Access Tokens
   - ✅ Enable Bot Account Creation
   - ✅ Enable Incoming Webhooks
   - ✅ Enable Outgoing Webhooks
   - ✅ Enable integrations to override usernames
   - ✅ Enable integrations to override profile picture icons

### Step 4: Create 4 Bot Accounts

For clean separation, create a dedicated bot account per pipeline:

1. Go to **System Console → Integrations → Bot Accounts**
2. Click **Add Bot Account**
3. Create each bot:

| Bot Username    | Display Name       | Description                                  | Role   |
| --------------- | ------------------ | -------------------------------------------- | ------ |
| `bot-youtube`   | YouTube Pipeline   | Posts pending YouTube content for approval   | Member |
| `bot-tiktok`    | TikTok Pipeline    | Posts pending TikTok content for approval    | Member |
| `bot-instagram` | Instagram Pipeline | Posts pending Instagram content for approval | Member |
| `bot-x`         | X Pipeline         | Posts pending X/Twitter content for approval | Member |

4. After creating each bot, **copy the Access Token** immediately — it's shown only once!

### Step 5: Generate Personal Access Tokens (Alternative to Bot Accounts)

If you prefer Personal Access Tokens (PATs) over bot accounts, you can create them from your admin account:

1. Click your avatar (top-left) → **Profile**
2. Go to **Security → Personal Access Tokens**
3. Click **Create Token**
4. Create 4 tokens:

| Token Description   | Used By                        |
| ------------------- | ------------------------------ |
| `n8n-youtube-bot`   | YouTube n8n pipeline (:5678)   |
| `n8n-tiktok-bot`    | TikTok n8n pipeline (:5679)    |
| `n8n-instagram-bot` | Instagram n8n pipeline (:5680) |
| `n8n-x-bot`         | X n8n pipeline (:5681)         |

5. **Save each token securely** — they are shown only once

### Step 6: Test the Integration

Test each bot token with a curl command from the Pi:

```bash
# Replace TOKEN and CHANNEL_ID with your values
# Get channel ID: Mattermost web UI → channel → ... menu → View Info → copy ID

# Test YouTube bot
curl -X POST http://localhost:8065/api/v4/posts \
  -H "Authorization: Bearer YOUR_YOUTUBE_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "YOUTUBE_CHANNEL_ID",
    "message": "🎮 **[TEST] YouTube Content Ready for Review**\n\nTitle: Top 10 Gaming News This Week\nDuration: 12:34\nStatus: ⏳ Pending Approval"
  }'

# Test TikTok bot
curl -X POST http://localhost:8065/api/v4/posts \
  -H "Authorization: Bearer YOUR_TIKTOK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "TIKTOK_CHANNEL_ID",
    "message": "📱 **[TEST] TikTok Content Ready for Review**\n\nCaption: Breaking gaming news!\nDuration: 0:45\nStatus: ⏳ Pending Approval"
  }'

# Test Instagram bot
curl -X POST http://localhost:8065/api/v4/posts \
  -H "Authorization: Bearer YOUR_INSTAGRAM_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "INSTAGRAM_CHANNEL_ID",
    "message": "📸 **[TEST] Instagram Content Ready for Review**\n\nType: Reel\nCaption: Gaming highlights!\nStatus: ⏳ Pending Approval"
  }'

# Test X bot
curl -X POST http://localhost:8065/api/v4/posts \
  -H "Authorization: Bearer YOUR_X_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "X_CHANNEL_ID",
    "message": "🐦 **[TEST] X Post Ready for Review**\n\nThread: 3 tweets\nTopic: Weekly gaming roundup\nStatus: ⏳ Pending Approval"
  }'
```

### Step 7: Configure n8n HTTP Nodes

In each n8n pipeline, add an **HTTP Request** node to post to Mattermost:

| n8n Instance      | Mattermost Endpoint                      | Bot Token       | Channel               |
| ----------------- | ---------------------------------------- | --------------- | --------------------- |
| YouTube (:5678)   | `http://192.168.1.100:8065/api/v4/posts` | YouTube token   | `#pipeline-youtube`   |
| TikTok (:5679)    | `http://192.168.1.100:8065/api/v4/posts` | TikTok token    | `#pipeline-tiktok`    |
| Instagram (:5680) | `http://192.168.1.100:8065/api/v4/posts` | Instagram token | `#pipeline-instagram` |
| X (:5681)         | `http://192.168.1.100:8065/api/v4/posts` | X token         | `#pipeline-x`         |

**n8n HTTP Request Node Settings:**

- **Method:** POST
- **URL:** `http://192.168.1.100:8065/api/v4/posts`
- **Authentication:** Header Auth
  - Name: `Authorization`
  - Value: `Bearer YOUR_BOT_TOKEN`
- **Body (JSON):**
  ```json
  {
    "channel_id": "CHANNEL_ID_HERE",
    "message": "🎮 **Content Ready for Review**\n\nTitle: {{ $json.title }}\nPlatform: YouTube\nStatus: ⏳ Pending"
  }
  ```

### Step 8: Install Mobile App

1. Download **Mattermost** from the App Store (iOS) or Google Play (Android)
2. Open the app → **Enter Server URL**
3. Enter your Tailscale URL: `http://100.x.x.x:8065`
   - Make sure Tailscale VPN is active on your phone
4. Log in with your admin credentials
5. You should see the 4 pipeline channels
6. **Push notifications** will arrive automatically (TPNS is pre-configured)

---

## Diagnostics

```bash
# Full status report
./scripts/mattermost-status.sh

# Quick health check
./scripts/mattermost-status.sh health

# List pipeline channels (requires MM_ADMIN_TOKEN)
export MM_ADMIN_TOKEN=your_token_here
./scripts/mattermost-status.sh channels

# Tail logs
./scripts/mattermost-status.sh logs
```

## Maintenance

### Useful Commands

```bash
# View live logs
docker compose logs -f

# Restart both services
docker compose restart

# Stop everything
docker compose down

# Update images
docker compose pull && docker compose up -d

# Container status
docker compose ps

# Mattermost CLI (inside container)
docker exec -it mattermost mmctl --local system version
docker exec -it mattermost mmctl --local channel list pi-lab
docker exec -it mattermost mmctl --local user list

# Database shell
docker exec -it postgres_mattermost psql -U mm_user -d mattermost
```

### Backup

```bash
# Database dump
docker exec postgres_mattermost pg_dump -U mm_user mattermost > backup_mm_$(date +%Y%m%d).sql

# Full data backup (NVMe)
sudo tar czf mattermost_backup_$(date +%Y%m%d).tar.gz /mnt/nvme/mattermost/

# Restore database
cat backup_mm_YYYYMMDD.sql | docker exec -i postgres_mattermost psql -U mm_user -d mattermost
```

### Update Mattermost

```bash
# Pull latest image
docker compose pull mattermost

# Recreate container (data is persisted on NVMe)
docker compose up -d mattermost

# Verify
./scripts/mattermost-status.sh health
```

## Ports

| Service    | Port | Protocol | Description                      |
| ---------- | ---- | -------- | -------------------------------- |
| Mattermost | 8065 | HTTP     | Web UI, REST API, WebSocket      |
| PostgreSQL | 5438 | TCP      | Database (host-mapped from 5432) |

## Coexistence with Other Stacks

| Stack                   | Ports               | Network             | Purpose                                         |
| ----------------------- | ------------------- | ------------------- | ----------------------------------------------- |
| pi_youtube_stack        | 5433, 5678          | youtube_stack_net   | Content pipeline → posts to #pipeline-youtube   |
| pi_tiktok_stack         | 5434, 5679          | tiktok_stack_net    | Content pipeline → posts to #pipeline-tiktok    |
| pi_instagram_stack      | 5435, 5680          | instagram_stack_net | Content pipeline → posts to #pipeline-instagram |
| pi_x_stack              | 5436, 5681          | x_stack_net         | Content pipeline → posts to #pipeline-x         |
| pi_hole_stack           | 53, 8080            | pihole_net          | DNS ad blocking                                 |
| pi_command_center       | 3001, 3010          | command_center_net  | Homepage + Uptime Kuma monitoring               |
| pi_nextcloud_stack      | 80, 443, 5437, 8443 | nextcloud_net       | Personal cloud + file sync                      |
| pi_remote_access_stack  | none                | remote_access_net   | Tailscale VPN + Cloudflare Tunnels              |
| **pi_mattermost_stack** | **5438, 8065**      | **mattermost_net**  | **Approval dashboard (this stack)**             |

## Security Considerations

- **No public exposure:** Mattermost is accessed only via Tailscale VPN — never exposed to the internet
- **Bot tokens are secrets:** Store them securely in n8n credentials, never commit to Git
- **Database password:** Change from the default immediately; never commit `.env`
- **TPNS limitations:** The free push service is unencrypted between Mattermost and the relay — acceptable for approval notifications, not for sensitive data
- **Single admin:** Only one user (you) — no need for complex RBAC, but enable MFA for extra safety

## Troubleshooting

### Mattermost won't start

```bash
# Check container logs
docker compose logs mattermost

# Common issues:
# 1. Database not ready → postgres_mattermost must be healthy first (depends_on handles this)
# 2. Permission denied → run: sudo chown -R 2000:2000 /mnt/nvme/mattermost/{data,config,logs,plugins}
# 3. Port 8065 in use → check: sudo lsof -i :8065
```

### Can't connect from mobile app

```bash
# 1. Ensure Tailscale is active on your phone
# 2. Verify Tailscale IP:
docker exec tailscale tailscale ip -4

# 3. Test from the phone's browser first:
#    http://100.x.x.x:8065

# 4. Ensure MM_SITEURL matches the Tailscale IP
grep MM_SITEURL .env
```

### Push notifications not arriving

```bash
# 1. Verify TPNS is configured:
docker exec mattermost env | grep PUSH

# Expected output:
# MM_EMAILSETTINGS_SENDPUSHNOTIFICATIONS=true
# MM_EMAILSETTINGS_PUSHNOTIFICATIONSERVER=https://push-test.mattermost.com

# 2. Check System Console → Environment → Push Notification Server
#    Should show: https://push-test.mattermost.com

# 3. Test: send a DM to yourself while the app is in background
#    → notification should appear within 5 seconds

# 4. If still not working, check if the TPNS endpoint is reachable:
docker exec mattermost curl -sf https://push-test.mattermost.com
```

### Bot token "invalid or expired"

```bash
# 1. Verify the token exists:
#    System Console → Integrations → Bot Accounts → check token is active

# 2. Test the token:
curl -sf -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8065/api/v4/users/me | python3 -m json.tool

# 3. If the bot was deactivated, reactivate it in System Console
```

### Database connection issues

```bash
# Check PostgreSQL health
docker inspect --format='{{.State.Health.Status}}' postgres_mattermost

# Check PostgreSQL logs
docker compose logs postgres_mattermost

# Test connection manually
docker exec -it postgres_mattermost psql -U mm_user -d mattermost -c "SELECT 1;"
```

## License

Private — Adamo-97
