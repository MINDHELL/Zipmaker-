import os
import zipfile
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the bot
bot = Client("ZipBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Store user file paths
user_files = {}

# Directory for temporary files (use /app/tmp for Koyeb)
TEMP_DIR = "/app/tmp" if os.getenv("KOYEB_REGION") else "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Start command
@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text("👋 Welcome! Send files and type `/zip filename` to create a ZIP.")

# Handle file uploads
@bot.on_message(filters.document | filters.video | filters.photo)
async def receive_files(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_files:
        user_files[user_id] = []

    file_path = await message.download(file_name=os.path.join(TEMP_DIR, message.document.file_name))
    user_files[user_id].append(file_path)

    logger.info(f"File saved: {file_path}")  # Debugging log
    await message.reply_text(f"✅ File **{message.document.file_name}** added! Send more or type `/zip filename`.")

# ZIP command
@bot.on_message(filters.command("zip"))
async def zip_files(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_files or not user_files[user_id]:
        await message.reply_text("⚠️ No files to zip. Send files first!")
        return

    args = message.text.split(maxsplit=1)
    zip_filename = args[1] if len(args) > 1 else "compressed_files"
    zip_path = os.path.join(TEMP_DIR, f"{zip_filename}.zip")

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in user_files[user_id]:
                zipf.write(file, os.path.basename(file))
                logger.info(f"Added to ZIP: {file}")

        await client.send_document(message.chat.id, zip_path, caption="📁 Your ZIP file is ready!")

        # Cleanup
        os.remove(zip_path)
        for file in user_files[user_id]:
            os.remove(file)
        user_files[user_id] = []

    except Exception as e:
        logger.error(f"ZIP Error: {e}")
        await message.reply_text("❌ Failed to create ZIP file.")

bot.run()
