# 🔄 pi_n8n_stack — Shared Workflow Engine

Single [n8n](https://n8n.io) instance that orchestrates **all content pipelines** running on this Raspberry Pi 5.

## Why shared?

| Approach | n8n instances | RAM usage |
|----------|--------------|-----------|
| Per-stack n8n (old) | 4 × 512 MB | **~2 GB** |
| Shared n8n (this) | 1 × 768 MB | **~768 MB** |

One n8n connects to every pipeline's Postgres + Redis via Docker external networks.

## Architecture

```
pi_n8n_stack/
├── docker-compose.yml    # Shared n8n container
├── .env.example          # Auth & config template
├── setup.sh              # One-time setup
└── README.md

Mounts (read-only code, read-write output):
  /home/node/instagram_stack  →  ../pi_instagram_stack/
  /home/node/tiktok_stack     →  ../pi_tiktok_stack/
  /home/node/x_stack          →  ../pi_x_stack/
  /home/node/youtube_stack    →  ../pi_youtube_stack/
```

## Quick Start

```bash
# 1. Setup
chmod +x setup.sh && ./setup.sh

# 2. Edit credentials
nano .env

# 3. Start a pipeline stack first (creates the Docker network)
cd ../pi_instagram_stack && docker compose up -d

# 4. Start n8n
cd ../pi_n8n_stack && docker compose up -d

# 5. Open UI & import workflows
# http://<pi-ip>:5678
# Import each stack's n8n_workflow.json
```

## Networks

n8n joins each pipeline stack's Docker network as **external**:

| Network | Accessible services |
|---------|-------------------|
| `instagram_stack_net` | `postgres_instagram`, `redis_instagram` |
| `tiktok_stack_net` | `postgres_tiktok`, `redis_tiktok` |
| `x_stack_net` | `postgres_x`, `redis_x` |
| `youtube_stack_net` | `postgres_youtube`, `redis_youtube` |

> **Important:** The pipeline stack must be running (network created) _before_ starting n8n. If you only want to run one pipeline for now, comment out the other external networks in `docker-compose.yml`.

## Workflow Import

Each pipeline has an `n8n_workflow.json` at its root. After starting n8n:

1. Open `http://<pi-ip>:5678`
2. Go to **Workflows → Import from File**
3. Select the workflow JSON from the pipeline you want to activate
4. Configure credentials (API keys) in n8n's credential manager
5. Activate the workflow

## Ports

| Service | Port |
|---------|------|
| n8n Web UI | `5678` |
| n8n Webhooks | `5678` |
