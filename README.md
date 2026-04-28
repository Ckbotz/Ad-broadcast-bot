# 📡 Telegram Broadcast Bot

A feature-rich Pyrogram-based Telegram broadcast bot with multi-admin support, channel management, post creation with inline buttons, paginated channel selection, and post deletion from all channels.

---

## 🗂 File Structure

```
.
├── main.py           # Entrypoint: runs bot + webserver together
├── bot.py            # All bot logic and handlers
├── database.py       # Async SQLite DB layer (aiosqlite)
├── config.py         # Reads env vars
├── webserver.py      # Aiohttp health-check server (port 8080)
├── requirements.txt
├── Dockerfile
└── .env.example
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable      | Description                                      |
|---------------|--------------------------------------------------|
| `API_ID`      | Telegram API ID (from my.telegram.org)           |
| `API_HASH`    | Telegram API Hash                                |
| `BOT_TOKEN`   | Bot token from @BotFather                        |
| `ADMIN_IDS`   | Comma-separated admin Telegram user IDs          |
| `LOG_CHANNEL` | Channel ID for logs (e.g. `-1001234567890`)      |

---

## 🚀 Running Locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in your .env values
python main.py
```

---

## 🐳 Docker

```bash
docker build -t broadcast-bot .
docker run -d \
  -e API_ID=... \
  -e API_HASH=... \
  -e BOT_TOKEN=... \
  -e ADMIN_IDS=... \
  -e LOG_CHANNEL=... \
  -p 8080:8080 \
  broadcast-bot
```

---

## ☁️ Koyeb Deployment

1. Push to GitHub
2. Create a new Koyeb service → **Docker** or **Git** deployment
3. Set environment variables in Koyeb dashboard
4. Health check path: `/health` on port `8080`
5. Deploy!

---

## 📖 Admin Commands

| Command          | Description                                      |
|------------------|--------------------------------------------------|
| `/post`          | Create and broadcast a post                      |
| `/add_channels`  | Add channels (forward a message from the channel)|
| `/list_channels` | View all connected channels                      |
| `/refresh_chnl`  | Re-fetch and update channel names from Telegram  |
| `/delete_post`   | Delete a post from all channels it was sent to   |
| `/stats`         | View bot statistics                              |
| `/cancel`        | Cancel current operation                         |

---

## 🔄 Workflow

### Creating a Post
1. `/post` → Send image/text/image+caption
2. Send buttons in `Name - https://url` format (or `/skip`)
3. Preview shown → Press **Send**
4. Paginated channel list appears — tap to select ✅
5. **Send Selected** or **Send to All**

### Adding Channels
1. `/add_channels`
2. Forward any message from the target channel
3. Bot verifies it's an admin, saves channel
4. **Add More** or **Done**

### Deleting Posts
1. `/delete_post`
2. Select post from list
3. Bot deletes the message from every channel it was sent to

---

## 🗄 Database Schema

| Table           | Columns                                          |
|-----------------|--------------------------------------------------|
| `users`         | user_id, username, first_name, joined_at         |
| `channels`      | channel_id, channel_name, added_at               |
| `posts`         | post_id, created_at                              |
| `post_messages` | id, post_id, channel_id, message_id              |
