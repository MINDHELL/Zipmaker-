import os
import zipfile
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

# Bot Configurations (Replace with your credentials)
API_ID = "your_api_id"
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot
bot = Client("ZipBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Storage for user files
user_files = {}
user_collecting = {}

# Temporary file directory
TEMP_DIR = "/app/tmp" if os.getenv("KOYEB_REGION") else "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Start command
@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text("👋 Welcome! Use `/zip` to start collecting files for zipping.")

# Start ZIP process
@bot.on_message(filters.command("zip"))
async def start_zip(client, message: Message):
    user_id = message.from_user.id
    user_collecting[user_id] = True
    user_files[user_id] = []
    
    await message.reply_text("📂 Send me the files you want to ZIP.\n\n✅ Send `/done` when finished.")

# Receive files
@bot.on_message(filters.document | filters.video | filters.photo)
async def receive_files(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_collecting:
        return  # Ignore files if user didn't start /zip

    if user_id not in user_files:
        user_files[user_id] = []

    # Fix: Use message.id instead of message.message_id
    file_name = message.document.file_name if message.document else f"{message.id}.jpg"
    file_path = os.path.join(TEMP_DIR, file_name)
    await message.download(file_path)

    # Store the file
    user_files[user_id].append(file_path)
    await message.reply_text(f"✅ Added: `{file_name}`\nSend more files or `/done` when finished.")

# Remove a file
@bot.on_message(filters.command("remove"))
async def remove_file(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_files or not user_files[user_id]:
        await message.reply_text("❌ No files to remove.")
        return

    files_list = "\n".join([f"`{os.path.basename(f)}`" for f in user_files[user_id]])
    await message.reply_text(f"📂 Your files:\n{files_list}\n\nSend the filename to remove.")

    @bot.on_message(filters.text)
    async def delete_selected_file(client, msg: Message):
        file_to_remove = msg.text.strip()
        file_paths = [f for f in user_files[user_id] if os.path.basename(f) == file_to_remove]

        if not file_paths:
            await msg.reply_text("❌ File not found.")
            return
        
        os.remove(file_paths[0])
        user_files[user_id].remove(file_paths[0])
        await msg.reply_text(f"🗑 Removed `{file_to_remove}`")

# Finalize ZIP creation
@bot.on_message(filters.command("done"))
async def create_zip(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_files or not user_files[user_id]:
        await message.reply_text("❌ No files selected for zipping.")
        return

    zip_filename = os.path.join(TEMP_DIR, f"user_{user_id}.zip")

    with zipfile.ZipFile(zip_filename, "w") as zipf:
        for file in user_files[user_id]:
            zipf.write(file, os.path.basename(file))

    await message.reply_document(zip_filename, caption="📦 Here is your ZIP file.")
    
    # Cleanup
    os.remove(zip_filename)
    for file in user_files[user_id]:
        os.remove(file)
    
    del user_files[user_id]
    del user_collecting[user_id]

# Run the bot
bot.run()
