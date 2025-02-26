import os
import zipfile
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask
from threading import Thread

# Bot Configuration
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Initialize Bot
bot = Client(
    "zip_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Flask Web Server (for Koyeb health checks)
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web_server():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Dictionary to store user files
user_files = {}

# Command to start bot
@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text("Send me files, and I'll zip them for you!")

# Handling file uploads
@bot.on_message(filters.document | filters.video | filters.photo)
async def receive_files(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_files:
        user_files[user_id] = []

    file_path = await message.download()
    user_files[user_id].append(file_path)

    await message.reply_text(f"File **{message.document.file_name}** added! Send more files or type `/zip filename` to create a ZIP.")

# Command to create ZIP file
@bot.on_message(filters.command("zip"))
async def zip_files(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_files or not user_files[user_id]:
        await message.reply_text("You haven't sent any files to zip.")
        return

    args = message.text.split(maxsplit=1)
    zip_filename = args[1] if len(args) > 1 else "compressed_files"
    zip_path = f"{zip_filename}.zip"

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in user_files[user_id]:
            zipf.write(file, os.path.basename(file))

    await client.send_document(message.chat.id, zip_path, caption="Here is your zipped file!")

    os.remove(zip_path)
    for file in user_files[user_id]:
        os.remove(file)
    user_files[user_id] = []

# Run Flask server in a separate thread
Thread(target=run_web_server).start()

# Start the bot
bot.run()
