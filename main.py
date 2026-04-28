"""
main.py — Entrypoint: runs bot + webserver concurrently.
"""

import asyncio
import logging
from datetime import datetime

from pyrogram import Client
from pyrogram.errors import FloodWait

import database as db
from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL
from webserver import run_webserver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import bot to register all handlers
import bot  # noqa: F401


async def main():
    # Init DB
    await db.init_db()
    logger.info("Database initialized.")

    # Start webserver
    runner = await run_webserver()

    # Start bot
    async with bot.app:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        if LOG_CHANNEL:
            try:
                await bot.app.send_message(
                    LOG_CHANNEL,
                    f"🚀 <b>Bot started</b> at {now}",
                    parse_mode="html"
                )
            except Exception as e:
                logger.warning(f"Startup log failed: {e}")

        logger.info("Bot is running...")
        await asyncio.Event().wait()  # Run forever

    # Cleanup
    await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
