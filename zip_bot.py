import os
import re
import asyncio
import tempfile
import threading
from datetime import datetime
from pyzipper import AESZipFile
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
from flask import Flask

# Telegram Bot API Details
API_ID = "27788368"
API_HASH = "9df7e9ef3d7e4145270045e5e43e1081"
BOT_TOKEN = "8064879322:AAHvYtmZRsRamwHqhgUbXW-yZ5rjHhwdE4A"
MONGO_URL = "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# MongoDB Setup
mongo_client = MongoClient(MONGO_URL)
db = mongo_client["zip_bot"]
files_collection = db["files"]

# Initialize Bot
bot = Client("zip_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Track user sessions
user_sessions = {}

# Safely clean filenames
def safe_filename(name):
    return re.sub(r"[^\w\-.]", "_", name)

# Progress bar function
async def progress_bar(current, total, message: Message, start_time, prefix="Progress"):
    if total == 0:
        return
    elapsed = (datetime.now() - start_time).total_seconds()
    speed = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0
    percent = current * 100 / total
    bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
    text = (
        f"📦 **{prefix}**\n"
        f"`[{bar}]` {percent:.2f}%\n"
        f"📥 {current / 1024**2:.2f}MB / {total / 1024**2:.2f}MB\n"
        f"⚡ {speed / 1024**2:.2f} MB/s\n"
        f"⏳ ETA: {eta:.1f}s"
    )
    try:
        await message.edit(text)
    except:
        pass

@bot.on_message(filters.command("start"))
async def start_command(bot, message):
    await message.reply("👋 Welcome! Use /zip to begin selecting files for zipping.")

@bot.on_message(filters.command("zip"))
async def start_zip(bot, message):
    user_id = message.from_user.id
    user_sessions[user_id] = {
        "files": [],
        "status": "collecting",
        "zip_name": None,
        "password": None
    }
    await message.reply("📥 Please send the files (video, photo, or document) you want to include. Use /done when finished.")

@bot.on_message(filters.command("done"))
async def done_collecting(bot, message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session or not session["files"]:
        await message.reply("⚠️ You haven't added any files. Start with /zip")
        return
    user_sessions[user_id]["status"] = "awaiting_name"
    await message.reply("📦 Please send the name you want for your ZIP file (e.g., `myfiles.zip`).")

@bot.on_message(filters.text & ~filters.command(["start", "zip", "done"]))
async def handle_text(bot, message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        return

    if session["status"] == "awaiting_name":
        zip_name = message.text.strip()
        if not zip_name.endswith(".zip"):
            zip_name += ".zip"
        session["zip_name"] = safe_filename(zip_name)
        session["status"] = "awaiting_password"
        await message.reply("🔐 (Optional) Send a password to protect your ZIP, or type `no` to skip.")

    elif session["status"] == "awaiting_password":
        password = message.text.strip()
        if password.lower() != "no":
            session["password"] = password
        await create_and_send_zip(bot, message, session)
        user_sessions.pop(user_id, None)

@bot.on_message(filters.document | filters.video | filters.photo)
async def collect_files(bot, message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session or session.get("status") != "collecting":
        return

    file_id = None
    file_name = None

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.video:
        file_id = message.video.file_id
        file_name = f"video_{datetime.now().timestamp()}.mp4"
    elif message.photo:
        file_id = message.photo.file_id
        file_name = f"photo_{datetime.now().timestamp()}.jpg"

    file_name = safe_filename(file_name)
    session["files"].append({
        "file_id": file_id,
        "file_name": file_name
    })
    await message.reply(f"✅ File `{file_name}` added. Send more or /done when ready.")

async def create_and_send_zip(bot, message, session):
    zip_name = session["zip_name"]
    password = session["password"]
    files = session["files"]
    valid_count = 0

    progress_msg = await message.reply("⏳ Starting download and zip process...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, zip_name)
            with AESZipFile(zip_path, 'w', compression=8, encryption=2) as zipf:
                if password:
                    zipf.setpassword(password.encode())

                for file in files:
                    start_time = datetime.now()
                    filename = safe_filename(file["file_name"])
                    filepath = os.path.join(temp_dir, filename)

                    try:
                        file_path = await bot.download_media(
                            file["file_id"],
                            file_name=filepath,
                            progress=progress_bar,
                            progress_args=(progress_msg, start_time, f"Downloading `{filename}`")
                        )
                    except Exception as e:
                        await progress_msg.edit(f"❌ Failed to download `{filename}`:\n`{e}`")
                        continue

                    if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        try:
                            zipf.write(file_path, arcname=os.path.basename(file_path))
                            valid_count += 1
                        except Exception as e:
                            await progress_msg.edit(f"❌ Failed to zip `{filename}`:\n`{e}`")
                    else:
                        await progress_msg.edit(f"⚠️ Skipped `{filename}` (empty or missing).")

            if valid_count == 0:
                await progress_msg.edit("❌ Failed to create ZIP. No valid files were added.")
                return

            await progress_msg.edit("📤 Uploading ZIP...")
            start_time = datetime.now()

            await message.reply_document(
                zip_path,
                caption=f"✅ Here is your ZIP: `{zip_name}`",
                progress=progress_bar,
                progress_args=(progress_msg, start_time, "Uploading ZIP")
            )

    except Exception as e:
        await progress_msg.edit(f"❌ Critical error:\n`{e}`")

# Flask Health Server
def run_dummy_server():
    app = Flask("health_check")

    @app.route("/")
    def health():
        return "OK", 200

    app.run(host="0.0.0.0", port=8000)

# Optional: Background health check log
def start_health_check():
    import time
    while True:
        print("[HEALTH CHECK] Bot is alive.")
        time.sleep(60)

# Main Entry
if __name__ == "__main__":
    print("✅ Booting ZIP bot...")

    threading.Thread(target=run_dummy_server, daemon=True).start()
    threading.Thread(target=start_health_check, daemon=True).start()

    try:
        bot.run()
    except Exception as e:
        print("❌ Bot failed to start:", e)
