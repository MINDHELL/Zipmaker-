import os
import asyncio
import tempfile
import threading
from zipfile import ZipFile
from datetime import datetime
from pyrogram import Client, filters
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
zip_name_collection = db["zip_names"]

# Initialize Bot
bot = Client("zip_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Dictionary to store user file data temporarily
user_files = {}

# Progress Bar Function
async def progress_bar(current, total, message, start_time):
    if total == 0:
        return

    percent = (current / total) * 100
    elapsed_time = (datetime.now() - start_time).total_seconds()
    speed = current / elapsed_time if elapsed_time > 0 else 0
    remaining_time = (total - current) / speed if speed > 0 else 0

    progress = f"[{'█' * int(percent // 5)}{' ' * (20 - int(percent // 5))}]"
    text = (
        f"⏳ Downloading... {percent:.2f}%\n"
        f"{progress}\n"
        f"📥 Downloaded: {current / (1024 * 1024):.2f} MB / {total / (1024 * 1024):.2f} MB\n"
        f"🚀 Speed: {speed / (1024 * 1024):.2f} MB/s\n"
        f"⌛ Estimated Time: {remaining_time:.2f} sec"
    )

    await message.edit(text)

# /start command
@bot.on_message(filters.command("start"))
async def start(bot, message):
    await message.reply(
        "👋 Send me videos, photos, or documents to zip!\n\n"
        "Use `/done` when you're ready.\n"
        "🔄 To rename a file: `/rename oldname newname`\n"
        "🔄 To set ZIP name: `/setzip MyArchive.zip`"
    )

# File collection handler
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
    user_files.setdefault(user_id, []).append(file_info)

    await message.reply(f"📂 File **{file_name}** saved!\nSend more or use `/done` to zip.")

# Rename file command
@bot.on_message(filters.command("rename"))
async def rename_file(bot, message):
    user_id = message.from_user.id
    args = message.text.split(" ", 2)

    if len(args) < 3:
        await message.reply("⚠️ Incorrect format!\nUse: `/rename oldname newname`")
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

# Set ZIP name
@bot.on_message(filters.command("setzip"))
async def set_zip_name(bot, message):
    user_id = message.from_user.id
    args = message.text.split(" ", 1)

    if len(args) < 2:
        await message.reply("⚠️ Incorrect format!\nUse: `/setzip MyCustomName.zip`")
        return

    zip_name = args[1]

    zip_name_collection.update_one(
        {"user_id": user_id},
        {"$set": {"zip_name": zip_name}},
        upsert=True
    )

    await message.reply(f"✅ ZIP name set to `{zip_name}`")

# Done command to create zip
@bot.on_message(filters.command("done"))
async def create_zip(bot, message):
    user_id = message.from_user.id
    files = list(files_collection.find({"user_id": user_id}))

    if not files:
        await message.reply("⚠️ You haven't uploaded any files.")
        return

    zip_data = zip_name_collection.find_one({"user_id": user_id})
    zip_filename = zip_data["zip_name"] if zip_data else f"user_{user_id}.zip"
    processing_message = await message.reply("⏳ Downloading files...")

    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, zip_filename)

        with ZipFile(zip_path, "w") as zipf:
            for file in files:
                start_time = datetime.now()

                while True:
                    try:
                        file_path = await bot.download_media(
                            file["file_id"],
                            file_name=os.path.join(temp_dir, file["file_name"]),
                            progress=progress_bar,
                            progress_args=(processing_message, start_time)
                        )
                        break
                    except Exception as e:
                        print(f"Retrying download due to error: {e}")
                        await asyncio.sleep(1)

                zipf.write(file_path, os.path.basename(file_path))

        await message.reply_document(zip_path, caption=f"✅ Here is your ZIP file: `{zip_filename}`")

    files_collection.delete_many({"user_id": user_id})
    zip_name_collection.delete_one({"user_id": user_id})
    user_files.pop(user_id, None)

# === Health Check Server ===
def run_dummy_server():
    app = Flask("health")

    @app.route("/")
    def health():
        return "OK", 200

    app.run(host="0.0.0.0", port=8080)

# === Entry Point ===
if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    bot.run()
