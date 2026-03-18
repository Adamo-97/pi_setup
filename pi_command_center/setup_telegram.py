#!/usr/bin/env python3
"""Add Telegram notification to Uptime Kuma and apply to all monitors."""
import socketio, sys, json, os

KUMA_URL = "http://192.168.0.11:3001"
USERNAME = sys.argv[1]
PASSWORD = sys.argv[2]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

sio = socketio.SimpleClient()
sio.connect(KUMA_URL)

res = sio.call("login", {"username": USERNAME, "password": PASSWORD, "token": ""}, timeout=10)
if not res.get("ok"):
    print(f"Login failed: {res}")
    sys.exit(1)
print("Logged in.")

# Add Telegram notification
notif = {
    "name": "Telegram - Pi Alerts",
    "type": "telegram",
    "isDefault": True,
    "applyExisting": True,
    "telegramBotToken": BOT_TOKEN,
    "telegramChatID": CHAT_ID,
}
res = sio.call("addNotification", (notif, None), timeout=10)
if res.get("ok"):
    nid = res.get("id")
    print(f"✅ Telegram notification created (id={nid})")
else:
    print(f"❌ Failed: {res.get('msg', res)}")
    sio.disconnect()
    sys.exit(1)

# Test it
print("Sending test message...")
res = sio.call("testNotification", notif, timeout=15)
if res.get("ok"):
    print("✅ Test alert sent — check Telegram!")
else:
    print(f"⚠️  Test result: {res.get('msg', res)}")

sio.disconnect()
print("Done.")
