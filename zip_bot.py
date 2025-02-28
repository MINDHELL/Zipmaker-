import os
import asyncio
import tempfile
import threading
from zipfile import ZipFile
from datetime import datetime
from pyrogram import Client, filters
from pymongo import MongoClient

# Telegram Bot API Details
API_ID = "27788368"  # Replace with your API ID
API_HASH = "9df7e9ef3d7e4145270045e5e43e1081"  # Replace with your API Hash
BOT_TOKEN = "8064879322:AAH4Uv8ZJbHfDZRBnre_Uf4D-ew-Q8SCinc"  # Replace with your bot token
MONGO_URL = "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"  # Replace with your MongoDB URL

# MongoDB Setup
mongo_client = MongoClient(MONGO_URL)
db = mongo_client["zip_bot"]
files_collection = db["files"]

# Initialize Bot
bot = Client("zip_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Dictionary to store user file data temporarily
user_files = {}

# Function to show a progress bar
async def progress_bar(current, total, message):
    percent = (current / total) * 100 if total > 0 else 0
    progress = f"[{'█' * int(percent // 5)}{' ' * (20 - int(percent // 5))}]"
    text = f"⏳ Downloading... {percent:.2f}%\n{progress}"
    await message.edit(text)

# Command to start the bot
@bot.on_message(filters.command("start"))
async def start(bot, message):
    await message.reply("👋 Send me videos, photos, or documents to zip!\n\nUse `/done` when you're ready.")

# Function to collect files
@bot.on_message(filters.document | filters.video)
async def collect_files(bot, message):
    user_id = message.from_user.id

    file_type = "document" if message.document else "video"
    file_id = message.document.file_id if message.document else message.video.file_id
    file_name = message.document.file_name if message.document else f"video_{datetime.now().timestamp()}.mp4"

    # Store user files in MongoDB
    file_info = {
        "user_id": user_id,
        "file_id": file_id,
        "file_name": file_name,
        "file_type": file_type,
    }
    files_collection.insert_one(file_info)

    # Store file in local dictionary
    if user_id not in user_files:
        user_files[user_id] = []
    user_files[user_id].append(file_info)

    await message.reply(f"📂 File **{file_name}** saved!\nSend more or use `/done` to zip.")

# Command to finish and create ZIP
@bot.on_message(filters.command("done"))
async def create_zip(bot, message):
    user_id = message.from_user.id

    # Get user's files from MongoDB
    files = list(files_collection.find({"user_id": user_id}))

    if not files:
        await message.reply("⚠️ You haven't uploaded any files. Send some files first!")
        return

    await message.reply("⏳ Downloading files...")

    # Create ZIP
    zip_filename = f"user_{user_id}.zip"
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, zip_filename)
        with ZipFile(zip_path, "w") as zipf:
            for file in files:
                file_path = await bot.download_media(file["file_id"], progress=progress_bar)
                zipf.write(file_path, file["file_name"])

        await message.reply_document(zip_path, caption="✅ Here is your ZIP file!")
    
    # Clear stored files
    files_collection.delete_many({"user_id": user_id})
    user_files.pop(user_id, None)

# Run Bot
bot.run()
