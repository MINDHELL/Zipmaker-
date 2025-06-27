import os
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

# MongoDB Setup (still available if needed)
mongo_client = MongoClient(MONGO_URL)
db = mongo_client["zip_bot"]
files_collection = db["files"]

# Initialize Bot
bot = Client("zip_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# In-memory sessions: {user_id: {files, status, zip_name, password}}
user_sessions = {}

# Progress Bar Function
async def progress_bar(current, total, message: Message, start_time, label="Progress"):
    if total == 0:
        return
    elapsed = (datetime.now() - start_time).total_seconds()
    speed = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0
    percent = current * 100 / total
    bar = "█" * int(percent // 5) + "░" * (20 - int(percent // 5))
    text = (
        f"**{label}**\n"
        f"`[{bar}]` {percent:.2f}%\n"
        f"📥 {current / 1024**2:.2f}MB / {total / 1024**2:.2f}MB\n"
        f"⚡ Speed: {speed / 1024**2:.2f} MB/s\n"
        f"⏳ ETA: {eta:.1f}s"
    )
    try:
        await message.edit(text)
    except:
        pass

# /start command
@bot.on_message(filters.command("start"))
async def start(bot, message):
    await message.reply("👋 Send /zip to begin collecting files to ZIP.\nUse /done when ready.")

# /zip command: Begin collecting files
@bot.on_message(filters.command("zip"))
async def zip_command(bot, message):
    user_id = message.from_user.id
    user_sessions[user_id] = {
        "files": [],
        "status": "collecting",
        "zip_name": None,
        "password": None
    }
    await message.reply("📤 Send me videos, documents or photos.\nSend /done when finished.")

# Handle files (video/photo/document)
@bot.on_message(filters.document | filters.video | filters.photo)
async def collect_files(bot, message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session or session.get("status") != "collecting":
        return

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
    elif message.video:
        file_id = message.video.file_id
        file_name = f"video_{datetime.now().timestamp()}.mp4"
    elif message.photo:
        file_id = message.photo.file_id
        file_name = f"photo_{datetime.now().timestamp()}.jpg"
    else:
        return

    session["files"].append({"file_id": file_id, "file_name": file_name})
    await message.reply(f"✅ File `{file_name}` saved. Send more or /done to zip.")

# /done command: Ask for zip name
@bot.on_message(filters.command("done"))
async def done_command(bot, message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session or not session["files"]:
        await message.reply("⚠️ You haven't uploaded any files. Start with /zip.")
        return

    session["status"] = "awaiting_zipname"
    await message.reply("📦 Please send the name you want for your ZIP file (e.g., `myfiles.zip`).")

# Handle ZIP name and password
@bot.on_message(filters.text & ~filters.command(["start", "zip", "done"]))
async def handle_text(bot, message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        return

    text = message.text.strip()

    if session["status"] == "awaiting_zipname":
        if not text.endswith(".zip"):
            text += ".zip"
        session["zip_name"] = text
        session["status"] = "awaiting_password"
        await message.reply("🔐 (Optional) Send a password to protect your ZIP, or type `no` to skip.")

    elif session["status"] == "awaiting_password":
        session["password"] = None if text.lower() == "no" else text
        await create_and_send_zip(bot, message, session)
        user_sessions.pop(user_id, None)

# Create ZIP and send
async def create_and_send_zip(bot, message, session):
    zip_name = session["zip_name"]
    password = session["password"]
    files = session["files"]
    valid_file_count = 0

    progress_msg = await message.reply("⏳ Downloading and creating ZIP...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, zip_name)

            with AESZipFile(zip_path, 'w', compression=8, encryption=2) as zipf:
                if password:
                    zipf.setpassword(password.encode())

                for f in files:
                    file_name = f["file_name"]
                    temp_file_path = os.path.join(temp_dir, file_name)
                    start_time = datetime.now()

                    try:
                        downloaded_path = await bot.download_media(
                            f["file_id"],
                            file_name=temp_file_path,
                            progress=progress_bar,
                            progress_args=(progress_msg, start_time, f"Downloading `{file_name}`")
                        )

                        # ✅ Confirm the file exists and is not empty
                        if downloaded_path and os.path.exists(downloaded_path) and os.path.getsize(downloaded_path) > 0:
                            zipf.write(downloaded_path, arcname=os.path.basename(downloaded_path))
                            valid_file_count += 1
                        else:
                            await progress_msg.edit(f"⚠️ Skipped `{file_name}` (downloaded_path invalid or empty).")

                    except Exception as e:
                        await progress_msg.edit(f"❌ Error downloading `{file_name}`:\n`{e}`")
                        continue

            # ✅ Final check if ZIP is valid
            if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 100 or valid_file_count == 0:
                await progress_msg.edit("❌ Failed to create ZIP. No valid files were added.")
                return

            await progress_msg.edit("📤 Uploading ZIP...")
            start_time = datetime.now()

            await message.reply_document(
                zip_path,
                caption=f"✅ Your ZIP file: `{zip_name}`",
                progress=progress_bar,
                progress_args=(progress_msg, start_time, "Uploading ZIP")
            )

    except Exception as e:
        await progress_msg.edit(f"❌ Critical ZIP error:\n`{e}`")


# Flask health check server
def run_dummy_server():
    app = Flask("health_check")
    @app.route("/")
    def health():
        return "OK", 200
    app.run(host="0.0.0.0", port=8000)

# Periodic health log
def start_health_check():
    import time
    while True:
        print("[HEALTH CHECK] Bot is alive.")
        time.sleep(60)

# Start bot
if __name__ == "__main__":
    print("🚀 Starting bot...")
    threading.Thread(target=run_dummy_server, daemon=True).start()
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run()
