#!/usr/bin/env python3
"""Add all Uptime Kuma monitors via socket.io API."""
import socketio, time, sys, json

KUMA_URL = "http://192.168.0.11:3001"
USERNAME = sys.argv[1] if len(sys.argv) > 1 else input("Uptime Kuma username: ")
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else input("Uptime Kuma password: ")

MONITORS = [
    # HTTP monitors
    {"type": "http", "name": "n8n",         "url": "http://192.168.0.11:5678/healthz",          "interval": 60},
    {"type": "http", "name": "Mattermost",  "url": "http://192.168.0.11:8065/api/v4/system/ping","interval": 60},
    {"type": "http", "name": "Pi-hole",     "url": "http://192.168.0.11:8080/admin",            "interval": 60},
    {"type": "http", "name": "Homepage",    "url": "http://192.168.0.11:3010",                  "interval": 60},
    # TCP monitors (databases)
    {"type": "port", "name": "PostgreSQL - TikTok",    "hostname": "192.168.0.11", "port": 5434, "interval": 120},
    {"type": "port", "name": "PostgreSQL - Instagram",  "hostname": "192.168.0.11", "port": 5435, "interval": 120},
    {"type": "port", "name": "PostgreSQL - X",          "hostname": "192.168.0.11", "port": 5436, "interval": 120},
    {"type": "port", "name": "PostgreSQL - YouTube",    "hostname": "192.168.0.11", "port": 5433, "interval": 120},
    {"type": "port", "name": "Redis - TikTok",          "hostname": "192.168.0.11", "port": 6380, "interval": 120},
    {"type": "port", "name": "Redis - Instagram",       "hostname": "192.168.0.11", "port": 6381, "interval": 120},
    {"type": "port", "name": "Redis - X",               "hostname": "192.168.0.11", "port": 6382, "interval": 120},
    {"type": "port", "name": "Redis - YouTube",          "hostname": "192.168.0.11", "port": 6379, "interval": 120},
]

sio = socketio.SimpleClient()
sio.connect(KUMA_URL)

# Login
res = sio.call("login", {"username": USERNAME, "password": PASSWORD, "token": ""}, timeout=10)
if not res.get("ok"):
    print(f"Login failed: {res}")
    sys.exit(1)
print("Logged in.")

created = []
for m in MONITORS:
    monitor = {
        "name": m["name"],
        "interval": m["interval"],
        "maxretries": 3,
        "retryInterval": 20,
        "notificationIDList": {},
        "accepted_statuscodes": ["200-299"],
    }
    if m["type"] == "http":
        monitor["type"] = "http"
        monitor["url"] = m["url"]
    else:
        monitor["type"] = "port"
        monitor["hostname"] = m["hostname"]
        monitor["port"] = m["port"]

    res = sio.call("add", monitor, timeout=10)
    if res.get("ok"):
        print(f"  ✅ {m['name']} (id={res.get('monitorID')})")
        created.append({"id": res["monitorID"], "name": m["name"]})
    else:
        print(f"  ❌ {m['name']}: {res.get('msg', res)}")

print(f"\nDone — {len(created)}/{len(MONITORS)} monitors created.")
sio.disconnect()
