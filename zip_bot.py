import os
import re
import tempfile
import threading
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask
from zipfile import ZipFile, ZIP_DEFLATED

# ================= CONFIG ================= #

# Telegram Bot API Details
API_ID = "27788368"
API_HASH = "9df7e9ef3d7e4145270045e5e43e1081"
BOT_TOKEN = "7411785952:AAHE7utWPpx73UHvIh7zgeA-a_KUGOCtXKQ"
MONGO_URL = "mongodb+srv://aarshhub:wcCgmKoCu2sTsEtv@cluster0.6shiu.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"



# ========================================== #

bot = Client(
    "zip_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=50
)

user_sessions = {}


# ================= UTILITIES ================= #

def safe_filename(name):
    return re.sub(r"[^\w\-.]", "_", name)


async def progress_bar(current, total, message: Message, start_time, prefix="Progress"):
    if total == 0:
        return

    diff = (datetime.now() - start_time).total_seconds()

    # Update every 3 seconds only (prevents FloodWait)
    if int(diff) % 3 != 0:
        return

    percent = current * 100 / total
    speed = current / diff if diff > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0

    bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))

    text = (
        f"📦 **{prefix}**\n"
        f"`[{bar}]` {percent:.1f}%\n"
        f"📥 {current / 1024**2:.2f}MB / {total / 1024**2:.2f}MB\n"
        f"⚡ {speed / 1024**2:.2f} MB/s\n"
        f"⏳ ETA: {eta:.0f}s"
    )

    try:
        await message.edit(text)
    except:
        pass


# ================= COMMANDS ================= #

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply(
        "👋 Welcome!\n\n"
        "Use /zip to start creating your ZIP file."
    )


@bot.on_message(filters.command("zip"))
async def start_zip(client, message):
    user_sessions[message.from_user.id] = {
        "files": [],
        "status": "collecting",
        "zip_name": None,
        "password": None
    }

    await message.reply(
        "📥 Send files (video/photo/document).\n"
        "When finished, send /done"
    )


@bot.on_message(filters.command("done"))
async def done_collecting(client, message):
    session = user_sessions.get(message.from_user.id)

    if not session or not session["files"]:
        await message.reply("⚠️ No files added. Use /zip first.")
        return

    session["status"] = "awaiting_name"
    await message.reply("📦 Send ZIP file name (example: myfiles.zip)")


@bot.on_message(filters.text & ~filters.command(["start", "zip", "done"]))
async def handle_text(client, message):
    session = user_sessions.get(message.from_user.id)
    if not session:
        return

    # Step 1: ZIP Name
    if session["status"] == "awaiting_name":
        zip_name = message.text.strip()

        if not zip_name.endswith(".zip"):
            zip_name += ".zip"

        session["zip_name"] = safe_filename(zip_name)
        session["status"] = "awaiting_password"

        await message.reply(
            "🔐 Send password for ZIP (or type `no` to skip)"
        )

    # Step 2: Password
    elif session["status"] == "awaiting_password":
        password = message.text.strip()

        if password.lower() != "no":
            session["password"] = password

        await create_and_send_zip(client, message, session)
        user_sessions.pop(message.from_user.id, None)


# ================= FILE COLLECTION ================= #

@bot.on_message(filters.document | filters.video | filters.photo)
async def collect_files(client, message):
    session = user_sessions.get(message.from_user.id)
    if not session or session["status"] != "collecting":
        return

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name

    elif message.video:
        file_id = message.video.file_id
        file_name = f"video_{int(datetime.now().timestamp())}.mp4"

    elif message.photo:
        file_id = message.photo.file_id
        file_name = f"photo_{int(datetime.now().timestamp())}.jpg"

    file_name = safe_filename(file_name)

    session["files"].append({
        "file_id": file_id,
        "file_name": file_name
    })

    await message.reply(f"✅ Added `{file_name}`")


# ================= ZIP ENGINE ================= #

async def create_and_send_zip(client, message, session):

    files = session["files"]
    zip_name = session["zip_name"]
    password = session["password"]
    valid_count = 0

    progress_msg = await message.reply("⏳ Preparing ZIP...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:

            zip_path = os.path.join(temp_dir, zip_name)

            # Password protected ZIP
            if password:
                import pyzipper
                zipf = pyzipper.AESZipFile(
                    zip_path,
                    'w',
                    compression=pyzipper.ZIP_DEFLATED,
                    encryption=pyzipper.WZ_AES
                )
                zipf.setpassword(password.encode())
            else:
                zipf = ZipFile(zip_path, 'w', compression=ZIP_DEFLATED)

            with zipf:

                for file in files:
                    filename = file["file_name"]
                    filepath = os.path.join(temp_dir, filename)

                    start_time = datetime.now()
                    file_path = None

                    # Retry 3 times
                    for attempt in range(3):
                        try:
                            file_path = await client.download_media(
                                file["file_id"],
                                file_name=filepath,
                                progress=progress_bar,
                                progress_args=(progress_msg, start_time, f"Downloading `{filename}`")
                            )
                            break
                        except Exception as e:
                            await progress_msg.edit(
                                f"⚠️ Retry {attempt+1} failed for `{filename}`"
                            )

                    if not file_path or not os.path.exists(file_path):
                        continue

                    if os.path.getsize(file_path) < 10:
                        continue

                    zipf.write(file_path, arcname=filename)
                    valid_count += 1

            if valid_count == 0:
                await progress_msg.edit("❌ No valid files to zip.")
                return

            await progress_msg.edit("📤 Uploading ZIP...")

            start_time = datetime.now()

            await message.reply_document(
                zip_path,
                caption=f"✅ Here is your ZIP: `{zip_name}`",
                progress=progress_bar,
                progress_args=(progress_msg, start_time, "Uploading ZIP")
            )

            await progress_msg.delete()

    except Exception as e:
        await progress_msg.edit(f"❌ Error:\n`{e}`")


# ================= HEALTH SERVER ================= #

def run_server():
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "Bot is running", 200

    app.run(host="0.0.0.0", port=8000)


# ================= MAIN ================= #

if __name__ == "__main__":
    print("🚀 ZIP Bot Started")
    threading.Thread(target=run_server, daemon=True).start()
    bot.run()
