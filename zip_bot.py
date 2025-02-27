import os
import tempfile
from os.path import basename
from zipfile import ZipFile
from pyrogram import Client, filters
from pymongo import MongoClient

# Bot credentials (replace with actual values)
API_ID = int(os.getenv("API_ID", "27788368"))
API_HASH = os.getenv("API_HASH", "9df7e9ef3d7e4145270045e5e43e1081")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8064879322:AAH4Uv8ZJbHfDZRBnre_Uf4D-ew-Q8SCinc")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://aarshhub:6L1PAPikOnAIHIRA@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

# Initialize MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["zip_bot"]
files_collection = db["uploaded_files"]

# Initialize bot
bot = Client("ZipBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Dictionary to store user file lists in memory
user_files = {}


@bot.on_message(filters.command("start"))
async def start(bot, message):
    await message.reply("Welcome! Send multiple files, then use /zip to create a ZIP file.")


@bot.on_message(filters.document | filters.photo | filters.video)
async def collect_files(bot, message):
    user_id = message.from_user.id

    # Save file info to MongoDB
    file_info = {"user_id": user_id, "file_id": message.document.file_id if message.document else message.photo.file_id}
    files_collection.insert_one(file_info)

    # Save file in memory for quick access
    if user_id not in user_files:
        user_files[user_id] = []
    user_files[user_id].append(file_info)

    await message.reply(f"File saved! You have uploaded {len(user_files[user_id])} files.")


@bot.on_message(filters.command("zip"))
async def zip_files(bot, message):
    user_id = message.from_user.id

    # Fetch user files from MongoDB
    user_files_db = list(files_collection.find({"user_id": user_id}))

    if not user_files_db:
        await message.reply("You haven't uploaded any files. Send some files first!")
        return

    zip_name = f"user_{user_id}.zip"
    with tempfile.TemporaryDirectory() as tmp_dirname:
        zip_path = os.path.join(tmp_dirname, zip_name)

        with ZipFile(zip_path, 'w') as zip_file:
            for file in user_files_db:
                file_id = file["file_id"]
                file_path = await bot.download_media(file_id, file_name=tmp_dirname)
                zip_file.write(file_path, basename(file_path))

        await message.reply_document(zip_path, caption="Here is your zipped file!")

    # Clear user's files after zipping
    files_collection.delete_many({"user_id": user_id})
    user_files.pop(user_id, None)


bot.run()
