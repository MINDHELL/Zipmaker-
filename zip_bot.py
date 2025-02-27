import os
import tempfile
from zipfile import ZipFile
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient

# BOT CONFIGURATION (Update these)
API_ID = "27788368"  # Replace with your API ID
API_HASH = "9df7e9ef3d7e4145270045e5e43e1081"  # Replace with your API Hash
BOT_TOKEN = "8064879322:AAH4Uv8ZJbHfDZRBnre_Uf4D-ew-Q8SCinc"  # Replace with your Bot Token
MONGO_URI = "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"  # Replace with your MongoDB connection URI

# MongoDB Setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["zip_bot"]
files_collection = db["uploaded_files"]

# Initialize Bot
bot = Client("ZipBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Track user states
user_states = {}

# ✅ Command: /start
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    user_id = message.from_user.id
    user_states[user_id] = "uploading"

    # Clear old files from MongoDB
    files_collection.delete_many({"user_id": user_id})

    await message.reply("Send me files, and I'll zip them for you!\nUse /done when you're finished.")

# ✅ Command: /done
@bot.on_message(filters.command("done") & filters.private)
async def done_cmd(client, message: Message):
    user_id = message.from_user.id
    file_count = files_collection.count_documents({"user_id": user_id})

    if file_count == 0:
        await message.reply("⚠️ You haven't uploaded any files. Send some files first!")
        return

    user_states[user_id] = "naming"
    await message.reply("Send a name for the ZIP file (without extension).")

# ✅ Handle file uploads
@bot.on_message(filters.private & filters.document)
async def file_handler(client, message: Message):
    user_id = message.from_user.id

    if user_states.get(user_id) != "uploading":
        await message.reply("Please use /start before sending files.")
        return

    file_id = message.document.file_id

    # Store file in MongoDB
    files_collection.insert_one({"user_id": user_id, "file_id": file_id})
    file_count = files_collection.count_documents({"user_id": user_id})

    print(f"📂 Stored file for user {user_id}: {file_id}")  # Debugging

    await message.reply(f"✅ File saved! Total: {file_count}. Send more or use /done.")

# ✅ Handle ZIP file naming
@bot.on_message(filters.private & filters.text)
async def name_handler(client, message: Message):
    user_id = message.from_user.id

    if user_states.get(user_id) != "naming":
        return

    zip_name = message.text.strip()
    if not zip_name:
        await message.reply("⚠️ Invalid name. Please send a valid ZIP file name.")
        return

    await message.reply("📥 Downloading and zipping your files...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, f"{zip_name}.zip")

        with ZipFile(zip_path, "w") as zip_file:
            files = list(files_collection.find({"user_id": user_id}))  # Convert cursor to list
            if not files:
                await message.reply("⚠️ No files found in database. Try again.")
                return
            
            for file in files:
                file_id = file["file_id"]
                print(f"⬇️ Downloading file: {file_id}")  # Debugging

                file_path = await client.download_media(file_id, file_name=tmp_dir)
                zip_file.write(file_path, os.path.basename(file_path))

        await message.reply_document(zip_path, caption="📦 Here is your ZIP file!")

    # Clear old files from MongoDB
    files_collection.delete_many({"user_id": user_id})
    
    user_states[user_id] = "uploading"
    await message.reply("Send more files or use /done to create another ZIP.")

# Run the bot
bot.run()
