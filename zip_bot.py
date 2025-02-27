import os
import tempfile
import logging
import pymongo
from zipfile import ZipFile
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message

# Bot Credentials
BOT_TOKEN = "8064879322:AAH4Uv8ZJbHfDZRBnre_Uf4D-ew-Q8SCinc"
API_ID = "27788368"
API_HASH = "9df7e9ef3d7e4145270045e5e43e1081"
MONGO_URI = "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# Initialize Bot
bot = Client("zip_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Initialize Flask for health check (fixes TCP error in Koyeb)
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!", 200

# MongoDB Connection
mongo_client = pymongo.MongoClient(MONGO_URI)
db = mongo_client["zip_bot"]
files_collection = db["user_files"]

# Logger
logging.basicConfig(level=logging.INFO)

# User file storage (temporary before zipping)
user_files = {}

# Start Command
@bot.on_message(filters.command("start"))
async def start(bot, message: Message):
    await message.reply("Send files to be added to a ZIP. Use /zip to start.")

# Begin ZIP Process
@bot.on_message(filters.command("zip"))
async def start_zip(bot, message: Message):
    user_id = message.from_user.id
    user_files[user_id] = []  # Reset file list
    await message.reply("Upload files now. Use /done when finished.")

# Collect Files (Documents, Photos, Videos)
@bot.on_message(filters.document | filters.photo | filters.video)
async def collect_files(bot, message: Message):
    user_id = message.from_user.id
    file_id = None

    # Detect File Type
    if message.document:
        file_id = message.document.file_id
        file_type = "Document"
    elif message.photo:
        file_id = message.photo.file_id
        file_type = "Photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "Video"
    else:
        file_type = "Unknown"

    if file_id:
        # Store file in memory
        user_files.setdefault(user_id, []).append(file_id)

        # Store in MongoDB
        files_collection.insert_one({"user_id": user_id, "file_id": file_id, "file_type": file_type})
        total_files = len(user_files[user_id])
        await message.reply(f"{file_type} saved! You have uploaded {total_files} files.")
    else:
        await message.reply("⚠️ Could not detect a valid file. Please try sending it again.")

# Finish ZIP Process
@bot.on_message(filters.command("done"))
async def create_zip(bot, message: Message):
    user_id = message.from_user.id
    files = user_files.get(user_id, [])

    if not files:
        await message.reply("⚠️ You haven't uploaded any files. Send some first!")
        return

    msg = await message.reply("⏳ Downloading files...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_filename = os.path.join(tmp_dir, "files.zip")

        with ZipFile(zip_filename, 'w') as zipObj:
            for index, file_id in enumerate(files):
                file_path = await bot.download_media(file_id, file_name=f"{index}")
                zipObj.write(file_path, os.path.basename(file_path))

        await msg.edit("✅ Files zipped! Uploading...")
        await message.reply_document(zip_filename, caption="Here is your ZIP file 📁")

    user_files[user_id] = []  # Reset files list

# Run Bot & Flask Server
if __name__ == "__main__":
    import threading
    from waitress import serve  # Production WSGI server

    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=8000), daemon=True).start()
    bot.run()
