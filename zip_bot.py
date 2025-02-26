import os
import zipfile
import logging
import asyncio
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN
from flask import Flask

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the bot
bot = Client("ZipBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Flask app for health check (Fixes TCP error on Koyeb)
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!", 200

def run_flask():
    app.run(host="0.0.0.0", port=8000)

# Directory for temporary files (Use "/app/tmp" on Koyeb)
TEMP_DIR = "/app/tmp" if os.getenv("KOYEB_REGION") else "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Store user file paths
user_files = {}
user_collecting = set()  # Track users who started /zip

# Start command
@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text("👋 Welcome! Send `/zip` to start selecting files.")

# Command to start collecting files
@bot.on_message(filters.command("zip"))
async def start_collection(client, message: Message):
    user_id = message.from_user.id
    user_collecting.add(user_id)  # Mark user as collecting files
    user_files[user_id] = []  # Initialize empty list
    await message.reply_text("📂 Now send the files you want to zip. When done, send `/done`.")

# Handle file uploads
@bot.on_message(filters.document | filters.video | filters.photo)
async def receive_files(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_collecting:
        return  # Ignore files if user didn't start /zip

    if user_id not in user_files:
        user_files[user_id] = []

    # Download the file
    file_name = message.document.file_name if message.document else f"{message.message_id}.jpg"
    file_path = os.path.join(TEMP_DIR, file_name)
    await message.download(file_path)

    # Store the file
    user_files[user_id].append(file_path)
    await message.reply_text(f"✅ Added: `{file_name}`\nSend more files or `/done` when finished.")

# Command to remove a file
@bot.on_message(filters.command("remove"))
async def remove_file(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_files or not user_files[user_id]:
        await message.reply_text("⚠️ No files to remove.")
        return

    buttons = [
        [InlineKeyboardButton(f"🗑 {os.path.basename(f)}", callback_data=f"remove_{i}")]
        for i, f in enumerate(user_files[user_id])
    ]
    buttons.append([InlineKeyboardButton("✅ Done", callback_data="done")])

    await message.reply_text("🗑 Select a file to remove:", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query()
async def handle_callback(client, callback_query):
    user_id = callback_query.from_user.id

    if callback_query.data.startswith("remove_"):
        index = int(callback_query.data.split("_")[1])
        removed_file = user_files[user_id].pop(index)
        os.remove(removed_file)

        await callback_query.answer("✅ File removed!")
        await remove_file(client, callback_query.message)

    elif callback_query.data == "done":
        await callback_query.message.delete()

# Command to finalize ZIP creation
@bot.on_message(filters.command("done"))
async def create_zip(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_files or not user_files[user_id]:
        await message.reply_text("⚠️ No files to zip. Send `/zip` to start.")
        return

    zip_name = os.path.join(TEMP_DIR, f"{user_id}.zip")
    with zipfile.ZipFile(zip_name, "w") as zipf:
        for file_path in user_files[user_id]:
            zipf.write(file_path, os.path.basename(file_path))

    # Send ZIP file
    await message.reply_document(zip_name, caption="📦 Here is your ZIP file!")

    # Cleanup
    for file in user_files[user_id]:
        os.remove(file)
    os.remove(zip_name)
    del user_files[user_id]
    user_collecting.discard(user_id)

if __name__ == "__main__":
    import threading
    threading.Thread(target=run_flask).start()
    bot.run()
