"""
Configuration - reads from environment variables
"""
import os

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", 0)) if os.environ.get("LOG_CHANNEL") else None

# Comma-separated list of admin Telegram user IDs
_raw_admins = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = set(int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit())

# MongoDB
MONGO_URI    = os.environ.get("MONGO_URI", "")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "broadcast_bot")

