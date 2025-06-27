import os
import asyncio
import tempfile
import threading
from zipfile import ZipFile
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
from flask import Flask

# === Telegram Bot API Details ===
API_ID = "27788368"
API_HASH = "9df7e9ef3d7e4145270045e5e43e1081"
BOT_TOKEN = "8064879322:AAHvYtmZRsRamwHqhgUbXW-yZ5rjHhwdE4A"
MONGO_URL = "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# === MongoDB Setup ===
mongo_client = MongoClient(MONGO_URL)
db = mongo_client["zip_bot"]
files_collection = db["files"]
zip_name_collection = db["zip_names"]

# === Initialize Bot ===
bot = Client("zip_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# === In-memory file tracker ===
user_files = {}

# === Progress Bar Function ===
async def progress_bar(current, total, message: Message, start_time):
    if total == 0:
        return
    elapsed = (datetime.now() - start_time).total_seconds()
    speed = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0
    percent = current * 100 / total

    progress_str = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
    text = (
        f"📦 **Progress**\n"
        f"`[{progress_str}]` {percent:.2f}%\n"
        f"📥 {current / 1024**2:.2f}MB / {total / 1024**2:.2f}MB\n"
        f"⚡ Speed: {speed / 1024**2:.2f} MB/s\n"
        f"⏳ ETA: {eta:.1f}s"
    )
    try:
        await message.edit(text)
    except:
        pass

# === /start command ===
@bot.on_message(filters.command("start"))
async def start_command(bot, message):
    await message.reply(
        "👋 Send me videos, photos, or documents to zip!\n\n"
        "✅ When you're ready, use `/done`\n"
        "✏️ Rename: `/rename oldname newname`\n"
        "📦 Set ZIP name: `/setzip MyArchive.zip`"
    )

# === Collect uploaded files ===
@bot.on_message(filters.document | filters.video)
async def collect_files(bot, message):
    user_id = message.from_user.id
    file_type = "document" if message.document else "video"
    file_id = message.document.file_id if message.document else message.video.file_id
    file_name = message.document.file_name if message.document else f"video_{datetime.now().timestamp()}.mp4"

    file_info = {
        "user_id": user_id,
        "file_id": file_id,
        "file_name": file_name,
        "file_type": file_type,
    }
    files_collection.insert_one(file_info)

    if user_id not in user_files:
        user_files[user_id] = []
    user_files[user_id].append(file_info)

    await message.reply(f"📂 File **{file_name}** saved!\nSend more or use `/done` to zip.")

# === Rename uploaded file ===
@bot.on_message(filters.command("rename"))
async def rename_file(bot, message):
    user_id = message.from_user.id
    args = message.text.split(" ", 2)

    if len(args) < 3:
        await message.reply("⚠️ Format: `/rename oldname newname`")
        return

    old_name, new_name = args[1], args[2]

    result = files_collection.update_one(
        {"user_id": user_id, "file_name": old_name},
        {"$set": {"file_name": new_name}}
    )

    if result.modified_count == 0:
        await message.reply("⚠️ File not found!")
    else:
        await message.reply(f"✅ Renamed `{old_name}` to `{new_name}`!")

# === Set ZIP filename ===
@bot.on_message(filters.command("setzip"))
async def set_zip_name(bot, message):
    user_id = message.from_user.id
    args = message.text.split(" ", 1)

    if len(args) < 2:
        await message.reply("⚠️ Format: `/setzip MyCustomName.zip`")
        return

    zip_name = args[1].strip()

    zip_name_collection.update_one(
        {"user_id": user_id},
        {"$set": {"zip_name": zip_name}},
        upsert=True
    )

    await message.reply(f"✅ ZIP name set to `{zip_name}`")

# === Create and send ZIP ===
@bot.on_message(filters.command("done"))
async def create_zip(bot, message):
    user_id = message.from_user.id
    files = list(files_collection.find({"user_id": user_id}))

    if not files:
        await message.reply("⚠️ You haven't uploaded any files yet!")
        return

    zip_data = zip_name_collection.find_one({"user_id": user_id})
    zip_filename = zip_data["zip_name"] if zip_data else f"user_{user_id}.zip"

    progress_msg = await message.reply("⏳ Preparing to download files...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, zip_filename)

            with ZipFile(zip_path, "w") as zipf:
                for file in files:
                    start_time = datetime.now()
                    file_name = file["file_name"]
                    file_id = file["file_id"]

                    file_path = await bot.download_media(
                        file_id,
                        file_name=os.path.join(temp_dir, file_name),
                        progress=progress_bar,
                        progress_args=(progress_msg, start_time),
                        fast_download=True
                    )

                    zipf.write(file_path, os.path.basename(file_path))

            await progress_msg.edit("✅ Uploading ZIP...")
            await message.reply_document(zip_path, caption=f"📦 Zipped: `{zip_filename}`")

    except Exception as e:
        await progress_msg.edit(f"❌ Error: {str(e)}")
        return

    # Cleanup
    files_collection.delete_many({"user_id": user_id})
    zip_name_collection.delete_one({"user_id": user_id})
    user_files.pop(user_id, None)

# === Flask Health Server (for UptimeRobot etc.) ===
def run_dummy_server():
    app = Flask("health_check")

    @app.route("/")
    def health():
        return "OK", 200

    app.run(host="0.0.0.0", port=8000)

# === Background Health Logger ===
def start_health_check():
    import time
    while True:
        print("[HEALTH CHECK] Bot is alive.")
        time.sleep(60)

# === Run Bot ===
if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    threading.Thread(target=start_health_check, daemon=True).start()
    bot.run()
