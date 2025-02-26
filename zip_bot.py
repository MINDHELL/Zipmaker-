import os
import zipfile
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the bot
bot = Client("ZipBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Store user file paths and zip status
user_files = {}
user_collecting = {}

# Directory for temporary files
TEMP_DIR = "/app/tmp" if os.getenv("KOYEB_REGION") else "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Start command
@bot.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text("👋 Welcome! Type `/zip` to start selecting files.")

# Start ZIP process
@bot.on_message(filters.command("zip"))
async def start_zipping(client, message: Message):
    user_id = message.from_user.id
    user_files[user_id] = []
    user_collecting[user_id] = True  # Start collecting files

    await message.reply_text(
        "📂 Now send the files you want to include in the ZIP.\nWhen you're done, type `/done`.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel")]])
    )

# Receive files
@bot.on_message(filters.document | filters.video | filters.photo)
async def receive_files(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_collecting or not user_collecting[user_id]:
        await message.reply_text("⚠️ You haven't started a ZIP session yet.\nType `/zip` first.")
        return

    # Ensure user has a list
    if user_id not in user_files:
        user_files[user_id] = []

    # Download file
    file_path = await message.download(file_name=os.path.join(TEMP_DIR, message.document.file_name))
    user_files[user_id].append(file_path)

    # Show updated file list
    await message.reply_text(
        f"✅ File added: `{message.document.file_name}`\nTotal files: {len(user_files[user_id])}\nSend more or type `/done` when finished.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Remove a File", callback_data="remove_file")]])
    )

# Remove a file
@bot.on_callback_query(filters.regex("remove_file"))
async def remove_file(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id not in user_files or not user_files[user_id]:
        await callback_query.answer("No files to remove!", show_alert=True)
        return

    # Create buttons for file selection
    buttons = [
        [InlineKeyboardButton(os.path.basename(file), callback_data=f"delete_{index}")]
        for index, file in enumerate(user_files[user_id])
    ]
    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel")])

    await callback_query.message.reply_text("Select a file to remove:", reply_markup=InlineKeyboardMarkup(buttons))

# Delete a selected file
@bot.on_callback_query(filters.regex(r"delete_(\d+)"))
async def delete_selected_file(client, callback_query):
    user_id = callback_query.from_user.id
    index = int(callback_query.data.split("_")[1])

    if user_id in user_files and 0 <= index < len(user_files[user_id]):
        removed_file = user_files[user_id].pop(index)
        os.remove(removed_file)  # Delete from storage
        await callback_query.message.edit_text(f"❌ Removed `{os.path.basename(removed_file)}`.\nTotal files left: {len(user_files[user_id])}")

# Cancel file selection
@bot.on_callback_query(filters.regex("cancel"))
async def cancel_selection(client, callback_query):
    user_id = callback_query.from_user.id
    user_collecting[user_id] = False
    user_files[user_id] = []
    await callback_query.message.edit_text("❌ ZIP process cancelled.")

# Finalize ZIP process
@bot.on_message(filters.command("done"))
async def finalize_zip(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_files or not user_files[user_id]:
        await message.reply_text("⚠️ No files selected for zipping.\nType `/zip` to start.")
        return

    zip_name = os.path.join(TEMP_DIR, f"{user_id}.zip")

    # Create ZIP
    with zipfile.ZipFile(zip_name, "w") as zipf:
        for file in user_files[user_id]:
            zipf.write(file, os.path.basename(file))

    # Send ZIP
    await client.send_document(message.chat.id, zip_name)

    # Cleanup
    os.remove(zip_name)
    for file in user_files[user_id]:
        os.remove(file)
    user_files[user_id] = []
    user_collecting[user_id] = False

    await message.reply_text("✅ ZIP file created and sent!")

# Start bot
bot.run()
