"""
Telegram Broadcast Bot - Pyrogram
Features: Multi-admin, DB, Log channel, Create Post, Channel Management, Broadcasting
"""

import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.errors import (
    ChatAdminRequired, ChannelPrivate, PeerIdInvalid, FloodWait
)

import database as db
from config import (
    API_ID, API_HASH, BOT_TOKEN, ADMIN_IDS, LOG_CHANNEL
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Client("broadcast_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ─────────────────────────────────────────────
# In-memory session state per user
# ─────────────────────────────────────────────
user_states = {}
# Structure:
# {
#   user_id: {
#     "step": str,
#     "post_media": FileID or None,
#     "post_media_type": "photo" | None,
#     "post_text": str,
#     "post_entities": list,
#     "post_buttons": list[{"name": str, "url": str}],
#     "selected_channels": set of channel_ids,
#     "channel_page": int,
#     "preview_msg_id": int or None,
#   }
# }

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_only(func):
    async def wrapper(client, update, *args, **kwargs):
        uid = update.from_user.id if hasattr(update, "from_user") else None
        if uid and is_admin(uid):
            return await func(client, update, *args, **kwargs)
        else:
            if isinstance(update, Message):
                await update.reply("⛔ You are not authorized to use this bot.")
            elif isinstance(update, CallbackQuery):
                await update.answer("⛔ Not authorized.", show_alert=True)
    return wrapper


def parse_buttons(text: str):
    """Parse button text into list of {name, url} dicts."""
    buttons = []
    for line in text.strip().splitlines():
        if " - " in line:
            parts = line.split(" - ", 1)
            name = parts[0].strip()
            url = parts[1].strip()
            if name and url.startswith("http"):
                buttons.append({"name": name, "url": url})
    return buttons


def build_inline_keyboard(buttons: list) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows = [[InlineKeyboardButton(b["name"], url=b["url"])] for b in buttons]
    return InlineKeyboardMarkup(rows)


def build_channel_keyboard(channels: list, page: int, selected: set, extra_buttons=True):
    """Build paginated channel selection keyboard."""
    per_page = 10
    total = len(channels)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = page * per_page
    end = start + per_page
    page_channels = channels[start:end]

    rows = []
    for ch in page_channels:
        ch_id = ch["channel_id"]
        name = ch["channel_name"]
        tick = "✅ " if ch_id in selected else ""
        rows.append([InlineKeyboardButton(
            f"{tick}{name}",
            callback_data=f"sel_ch:{ch_id}:{page}"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"ch_page:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"ch_page:{page+1}"))
    if nav:
        rows.append(nav)

    if extra_buttons:
        rows.append([
            InlineKeyboardButton("📤 Send Selected", callback_data="broadcast:selected"),
            InlineKeyboardButton("📢 Send to All", callback_data="broadcast:all"),
        ])
        rows.append([InlineKeyboardButton("❌ Cancel", callback_data="broadcast:cancel")])

    return InlineKeyboardMarkup(rows)


async def log(client: Client, text: str):
    if LOG_CHANNEL:
        try:
            await client.send_message(LOG_CHANNEL, text, disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"Log failed: {e}")


async def send_post_to_chat(client: Client, chat_id, state: dict):
    """Send the composed post to a single chat_id. Returns message ID."""
    text = state.get("post_text") or ""
    media = state.get("post_media")
    media_type = state.get("post_media_type")
    buttons = state.get("post_buttons", [])
    reply_markup = build_inline_keyboard(buttons)

    if media and media_type == "photo":
        msg = await client.send_photo(
            chat_id, media, caption=text or None,
            parse_mode="html", reply_markup=reply_markup
        )
    else:
        msg = await client.send_message(
            chat_id, text, parse_mode="html",
            reply_markup=reply_markup, disable_web_page_preview=False
        )
    return msg.id


# ─────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    await db.add_user(user.id, user.username or "", user.first_name or "")
    await message.reply(
        f"👋 Hello <b>{user.first_name}</b>!\n\n"
        "I am a <b>Broadcast Bot</b>.\n\n"
        + ("🔑 You are an <b>admin</b>. Use /help to see commands." if is_admin(user.id)
           else "You can start the bot but only admins can use commands."),
        parse_mode="html"
    )


# ─────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────

@app.on_message(filters.command("help") & filters.private)
@admin_only
async def help_handler(client: Client, message: Message):
    await message.reply(
        "<b>📖 Admin Commands</b>\n\n"
        "/post — Create and broadcast a post\n"
        "/add_channels — Add channels to the bot\n"
        "/list_channels — View connected channels\n"
        "/refresh_chnl — Refresh channel names from Telegram\n"
        "/delete_post — Delete a broadcast post from all channels\n"
        "/stats — Bot statistics\n"
        "/cancel — Cancel current operation",
        parse_mode="html"
    )


# ─────────────────────────────────────────────
# /stats
# ─────────────────────────────────────────────

@app.on_message(filters.command("stats") & filters.private)
@admin_only
async def stats_handler(client: Client, message: Message):
    users = await db.count_users()
    channels = await db.count_channels()
    posts = await db.count_posts()
    await message.reply(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👤 Users: <b>{users}</b>\n"
        f"📡 Channels: <b>{channels}</b>\n"
        f"📝 Posts: <b>{posts}</b>",
        parse_mode="html"
    )


# ─────────────────────────────────────────────
# /cancel
# ─────────────────────────────────────────────

@app.on_message(filters.command("cancel") & filters.private)
@admin_only
async def cancel_handler(client: Client, message: Message):
    user_states.pop(message.from_user.id, None)
    await message.reply("✅ Operation cancelled.")


# ─────────────────────────────────────────────
# ═══════════ CHANNEL MANAGEMENT ═══════════
# ─────────────────────────────────────────────

@app.on_message(filters.command("add_channels") & filters.private)
@admin_only
async def add_channels_start(client: Client, message: Message):
    user_states[message.from_user.id] = {"step": "add_channel_await_forward"}
    await message.reply(
        "📡 <b>Add Channels</b>\n\n"
        "Please <b>forward any message</b> from the channel you want to add.\n\n"
        "<i>Make sure the bot is an admin in that channel first!</i>",
        parse_mode="html"
    )


@app.on_message(filters.command("list_channels") & filters.private)
@admin_only
async def list_channels_handler(client: Client, message: Message):
    channels = await db.get_all_channels()
    if not channels:
        return await message.reply("No channels added yet. Use /add_channels to add some.")
    lines = [f"<b>{i+1}.</b> {ch['channel_name']} — <code>{ch['channel_id']}</code>"
             for i, ch in enumerate(channels)]
    await message.reply("📡 <b>Connected Channels:</b>\n\n" + "\n".join(lines), parse_mode="html")


@app.on_message(filters.command("refresh_chnl") & filters.private)
@admin_only
async def refresh_channels_handler(client: Client, message: Message):
    channels = await db.get_all_channels()
    if not channels:
        return await message.reply("No channels to refresh.")
    msg = await message.reply("🔄 Refreshing channel names...")
    updated = 0
    for ch in channels:
        try:
            chat = await client.get_chat(ch["channel_id"])
            new_name = chat.title
            if new_name != ch["channel_name"]:
                await db.update_channel_name(ch["channel_id"], new_name)
                updated += 1
        except Exception as e:
            logger.warning(f"Refresh failed for {ch['channel_id']}: {e}")
    await msg.edit(f"✅ Refreshed. <b>{updated}</b> channel name(s) updated.", parse_mode="html")


# ─────────────────────────────────────────────
# ═══════════ CREATE POST ═══════════
# ─────────────────────────────────────────────

@app.on_message(filters.command("post") & filters.private)
@admin_only
async def post_start(client: Client, message: Message):
    user_states[message.from_user.id] = {
        "step": "post_await_content",
        "post_media": None,
        "post_media_type": None,
        "post_text": "",
        "post_entities": [],
        "post_buttons": [],
        "selected_channels": set(),
        "channel_page": 0,
        "preview_msg_id": None,
    }
    await message.reply(
        "✍️ <b>Create Post</b>\n\n"
        "Send me the post content:\n"
        "• Text message (HTML supported)\n"
        "• Photo\n"
        "• Photo with caption (HTML supported)\n\n"
        "<i>Use /cancel to abort.</i>",
        parse_mode="html"
    )


# ─────────────────────────────────────────────
# ═══════════ DELETE POST ═══════════
# ─────────────────────────────────────────────

@app.on_message(filters.command("delete_post") & filters.private)
@admin_only
async def delete_post_start(client: Client, message: Message):
    posts = await db.get_all_posts()
    if not posts:
        return await message.reply("No posts found in database.")

    rows = []
    for p in posts[-20:]:  # Show last 20
        ts = p.get("created_at", "")[:10]
        rows.append([InlineKeyboardButton(
            f"🗑 Post #{p['post_id']} ({ts})",
            callback_data=f"del_post:{p['post_id']}"
        )])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")])
    await message.reply(
        "🗑 <b>Delete Post</b>\n\nSelect a post to delete from all channels:",
        parse_mode="html",
        reply_markup=InlineKeyboardMarkup(rows)
    )


# ─────────────────────────────────────────────
# ═══════════ MESSAGE HANDLER (state machine) ═══════════
# ─────────────────────────────────────────────

@app.on_message(filters.private & ~filters.command(["start","help","post","add_channels",
    "list_channels","refresh_chnl","delete_post","stats","cancel"]))
@admin_only
async def message_state_handler(client: Client, message: Message):
    uid = message.from_user.id
    state = user_states.get(uid)
    if not state:
        return

    step = state.get("step")

    # ── Add channel: await forward ──
    if step == "add_channel_await_forward":
        if not message.forward_from_chat:
            return await message.reply("⚠️ Please forward a message from a channel, not from a user or group.")
        
        chat = message.forward_from_chat
        if chat.type not in ("channel",):
            return await message.reply("⚠️ That doesn't seem to be a channel. Please forward from a channel.")
        
        ch_id = chat.id
        ch_name = chat.title
        
        # Check if already added
        existing = await db.get_channel(ch_id)
        if existing:
            await message.reply(
                f"⚠️ <b>{ch_name}</b> is already added.",
                parse_mode="html",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("➕ Add More", callback_data="add_more_channel"),
                    InlineKeyboardButton("✅ Done", callback_data="add_channel_done")
                ]])
            )
            return

        # Verify bot is admin
        try:
            member = await client.get_chat_member(ch_id, "me")
            if member.status not in ("administrator", "creator"):
                return await message.reply("⚠️ I'm not an admin in that channel. Please add me as admin first.")
        except Exception as e:
            return await message.reply(f"⚠️ Could not verify bot membership: {e}")

        await db.add_channel(ch_id, ch_name)
        await log(client, f"📡 Channel added: <b>{ch_name}</b> (<code>{ch_id}</code>)")
        await message.reply(
            f"✅ <b>{ch_name}</b> added successfully!",
            parse_mode="html",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Add More", callback_data="add_more_channel"),
                InlineKeyboardButton("✅ Done", callback_data="add_channel_done")
            ]])
        )

    # ── Post: await content ──
    elif step == "post_await_content":
        if message.photo:
            state["post_media"] = message.photo.file_id
            state["post_media_type"] = "photo"
            state["post_text"] = message.caption or ""
        elif message.text:
            state["post_text"] = message.text.html
        else:
            return await message.reply("⚠️ Please send text or a photo (with optional caption).")

        state["step"] = "post_await_buttons"
        await message.reply(
            "🔘 <b>Add Buttons</b>\n\n"
            "Send button links in this format (one per line):\n"
            "<code>Button Name - https://link.com</code>\n\n"
            "Example:\n"
            "<code>Visit Website - https://example.com\n"
            "Join Channel - https://t.me/channel</code>\n\n"
            "Send /skip to skip buttons.",
            parse_mode="html"
        )

    # ── Post: await buttons ──
    elif step == "post_await_buttons":
        if message.text and message.text != "/skip":
            buttons = parse_buttons(message.text)
            if not buttons:
                return await message.reply(
                    "⚠️ Could not parse buttons. Use format:\n"
                    "<code>Button Name - https://link.com</code>",
                    parse_mode="html"
                )
            state["post_buttons"] = buttons

        state["step"] = "post_preview"
        await show_post_preview(client, message.chat.id, uid, state)


async def show_post_preview(client: Client, chat_id: int, uid: int, state: dict):
    text = state.get("post_text") or ""
    media = state.get("post_media")
    media_type = state.get("post_media_type")
    buttons = state.get("post_buttons", [])
    post_markup = build_inline_keyboard(buttons)

    await client.send_message(chat_id, "👁 <b>Post Preview:</b>", parse_mode="html")

    if media and media_type == "photo":
        preview = await client.send_photo(
            chat_id, media, caption=text or None,
            parse_mode="html", reply_markup=post_markup
        )
    else:
        preview = await client.send_message(
            chat_id, text, parse_mode="html",
            reply_markup=post_markup, disable_web_page_preview=False
        )

    state["preview_msg_id"] = preview.id

    await client.send_message(
        chat_id,
        "Ready to send? Press <b>Send</b> to select channels.",
        parse_mode="html",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📤 Send", callback_data="post_send"),
            InlineKeyboardButton("❌ Cancel", callback_data="post_cancel")
        ]])
    )
    user_states[uid] = state


# ─────────────────────────────────────────────
# ═══════════ CALLBACK QUERY HANDLER ═══════════
# ─────────────────────────────────────────────

@app.on_callback_query(filters.private)
@admin_only
async def callback_handler(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    data = query.data
    state = user_states.get(uid, {})

    # ── Add channel buttons ──
    if data == "add_more_channel":
        user_states[uid] = {"step": "add_channel_await_forward"}
        await query.message.edit_text(
            "📡 Forward another message from the next channel you want to add:"
        )
        await query.answer()

    elif data == "add_channel_done":
        user_states.pop(uid, None)
        channels = await db.get_all_channels()
        await query.message.edit_text(
            f"✅ Done! <b>{len(channels)}</b> channel(s) connected.",
            parse_mode="html"
        )
        await query.answer()

    # ── Post flow ──
    elif data == "post_cancel":
        user_states.pop(uid, None)
        await query.message.edit_text("❌ Post creation cancelled.")
        await query.answer()

    elif data == "post_send":
        channels = await db.get_all_channels()
        if not channels:
            await query.answer("No channels added! Use /add_channels first.", show_alert=True)
            return
        state["selected_channels"] = set()
        state["channel_page"] = 0
        state["step"] = "selecting_channels"
        user_states[uid] = state
        kb = build_channel_keyboard(channels, 0, set())
        await query.message.edit_text(
            "📡 <b>Select Channels</b>\n\nTap channels to select/deselect:",
            parse_mode="html",
            reply_markup=kb
        )
        await query.answer()

    # ── Channel selection pagination ──
    elif data.startswith("ch_page:"):
        page = int(data.split(":")[1])
        state["channel_page"] = page
        user_states[uid] = state
        channels = await db.get_all_channels()
        kb = build_channel_keyboard(channels, page, state.get("selected_channels", set()))
        await query.message.edit_reply_markup(kb)
        await query.answer()

    elif data.startswith("sel_ch:"):
        parts = data.split(":")
        ch_id = int(parts[1])
        page = int(parts[2])
        selected = state.get("selected_channels", set())
        if ch_id in selected:
            selected.discard(ch_id)
        else:
            selected.add(ch_id)
        state["selected_channels"] = selected
        user_states[uid] = state
        channels = await db.get_all_channels()
        kb = build_channel_keyboard(channels, page, selected)
        await query.message.edit_reply_markup(kb)
        await query.answer(f"{'✅ Selected' if ch_id in selected else '❌ Deselected'}")

    # ── Broadcast ──
    elif data.startswith("broadcast:"):
        action = data.split(":")[1]
        channels = await db.get_all_channels()

        if action == "cancel":
            user_states.pop(uid, None)
            await query.message.edit_text("❌ Broadcast cancelled.")
            await query.answer()
            return

        if action == "selected":
            targets = [ch for ch in channels if ch["channel_id"] in state.get("selected_channels", set())]
        else:  # all
            targets = channels

        if not targets:
            await query.answer("No channels selected!", show_alert=True)
            return

        await query.message.edit_text(f"📤 Sending to <b>{len(targets)}</b> channel(s)...", parse_mode="html")
        
        post_id = await db.create_post()
        success, failed = 0, 0
        
        for ch in targets:
            try:
                msg_id = await send_post_to_chat(client, ch["channel_id"], state)
                await db.save_post_message(post_id, ch["channel_id"], msg_id)
                success += 1
                await asyncio.sleep(0.5)  # Flood protection
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    msg_id = await send_post_to_chat(client, ch["channel_id"], state)
                    await db.save_post_message(post_id, ch["channel_id"], msg_id)
                    success += 1
                except Exception as ex:
                    logger.error(f"Failed after flood wait: {ex}")
                    failed += 1
            except Exception as e:
                logger.error(f"Broadcast to {ch['channel_id']} failed: {e}")
                failed += 1

        user_states.pop(uid, None)
        await query.message.edit_text(
            f"✅ <b>Broadcast Complete!</b>\n\n"
            f"📤 Sent: <b>{success}</b>\n"
            f"❌ Failed: <b>{failed}</b>\n"
            f"🆔 Post ID: <code>{post_id}</code>\n\n"
            f"<i>Use /delete_post to remove this post from all channels.</i>",
            parse_mode="html"
        )
        await log(client,
            f"📢 Broadcast done | Post #{post_id} | ✅ {success} | ❌ {failed}"
        )
        await query.answer("Done!")

    # ── Delete post ──
    elif data.startswith("del_post:"):
        post_id = int(data.split(":")[1])
        records = await db.get_post_messages(post_id)
        if not records:
            await query.answer("No message records found for this post.", show_alert=True)
            return
        await query.message.edit_text(f"🗑 Deleting Post #{post_id} from {len(records)} channel(s)...")
        deleted, failed = 0, 0
        for rec in records:
            try:
                await client.delete_messages(rec["channel_id"], rec["message_id"])
                deleted += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"Delete failed: {rec['channel_id']} / {rec['message_id']}: {e}")
                failed += 1
        await db.delete_post(post_id)
        await query.message.edit_text(
            f"✅ Deleted <b>{deleted}</b> message(s). Failed: <b>{failed}</b>.",
            parse_mode="html"
        )
        await log(client, f"🗑 Post #{post_id} deleted | ✅{deleted} ❌{failed}")
        await query.answer()

    elif data == "del_cancel":
        await query.message.edit_text("❌ Deletion cancelled.")
        await query.answer()

    else:
        await query.answer()


# ─────────────────────────────────────────────
# Startup / Shutdown
# ─────────────────────────────────────────────

async def on_startup():
    await db.init_db()
    logger.info("Database initialized.")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    if LOG_CHANNEL:
        try:
            await app.send_message(LOG_CHANNEL, f"🚀 Bot started at <b>{now}</b>", parse_mode="html")
        except Exception as e:
            logger.warning(f"Could not send startup log: {e}")


async def on_shutdown():
    logger.info("Bot stopping.")
    if LOG_CHANNEL:
        try:
            await app.send_message(LOG_CHANNEL, "🔴 Bot stopped.")
        except Exception:
            pass


if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    async def main():
        async with app:
            await on_startup()
            logger.info("Bot is running...")
            await asyncio.Event().wait()  # Keep running

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        loop.run_until_complete(on_shutdown())
