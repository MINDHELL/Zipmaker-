import os
import asyncio
import tempfile
import threading
from pyzipper import AESZipFile
from datetime import datetime
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

# Dictionary to track zip sessions
user_sessions = {}

async def progress_bar(current, total, message: Message, start_time, prefix="Progress"):
    if total == 0:
        return
    elapsed = (datetime.now() - start_time).total_seconds()
    speed = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0
    percent = current * 100 / total

    progress_str = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
    text = (
        f"📦 **{prefix}**\n"
        f"`[{progress_str}]` {percent:.2f}%\n"
        f"📥 {current / 1024**2:.2f}MB / {total / 1024**2:.2f}MB\n"
        f"⚡ Speed: {speed / 1024**2:.2f} MB/s\n"
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
        session["zip_name"] = zip_name
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

    session["files"].append({
        "file_id": file_id,
        "file_name": file_name
    })
    await message.reply(f"✅ File `{file_name}` added. Send more or /done when ready.")

async def create_and_send_zip(bot, message, session):
    zip_name = session["zip_name"]
    password = session["password"]
    files = session["files"]
    valid_file_count = 0

    progress_msg = await message.reply("⏳ Starting download and zip process...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, zip_name)

            with AESZipFile(zip_path, 'w', compression=8, encryption=2) as zipf:
                if password:
                    zipf.setpassword(password.encode())

                for file in files:
                    start_time = datetime.now()
                    filename = file["file_name"]
                    filepath = os.path.join(temp_dir, filename)

                    try:
                        downloaded_path = await bot.download_media(
                            file["file_id"],
                            file_name=filepath,
                            progress=progress_bar,
                            progress_args=(progress_msg, start_time, f"Downloading `{filename}`")
                        )
                    except Exception as e:
                        await progress_msg.edit(f"❌ Failed to download `{filename}`:\n`{e}`")
                        continue

                    if not downloaded_path or not os.path.exists(downloaded_path):
                        await progress_msg.edit(f"⚠️ Skipping `{filename}` — not downloaded.")
                        continue

                    try:
                        zipf.write(downloaded_path, arcname=os.path.basename(downloaded_path))
                        valid_file_count += 1
                    except Exception as e:
                        await progress_msg.edit(f"❌ Failed to add `{filename}` to zip:\n`{e}`")
                        continue

            # Validate the final ZIP
            if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 100 or valid_file_count == 0:
                await progress_msg.edit("❌ Failed to create ZIP. No valid files were added.")
                return

            await progress_msg.edit("📤 Uploading ZIP...")
            start_time = datetime.now()

            await message.reply_document(
                zip_path,
                caption=f"✅ Here is your ZIP file: `{zip_name}`",
                progress=progress_bar,
                progress_args=(progress_msg, start_time, "Uploading ZIP")
            )

    except Exception as e:
        await progress_msg.edit(f"❌ Critical error:\n`{e}`")
# Flask health check
def run_dummy_server():
    app = Flask("health_check")

    @app.route("/")
    def health():
        return "OK", 200

    app.run(host="0.0.0.0", port=8000)

def start_health_check():
    import time
    while True:
        print("[HEALTH CHECK] Bot is alive.")
        time.sleep(60)

if __name__ == "__main__":
    print("✅ Booting ZIP bot...")

    # Start Flask dummy server for health check
    try:
        threading.Thread(target=run_dummy_server, daemon=True).start()
        print("✅ Flask server started on port 8000")
    except Exception as e:
        print("❌ Flask error:", e)

    try:
        threading.Thread(target=start_health_check, daemon=True).start()
        print("✅ Health check logger started")
    except Exception as e:
        print("❌ Health logger error:", e)

    try:
        print("✅ Starting Pyrogram bot...")
        bot.run()
    except Exception as e:
        print("❌ Bot failed:", e)
