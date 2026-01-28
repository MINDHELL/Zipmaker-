import os
import re
import asyncio
import tempfile
import subprocess
import threading
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask

# ================== CONFIG ==================
API_ID = "37371391"
API_HASH = "37895f967d284f6781f99e9beef21ebf"
BOT_TOKEN = "8229073869:AAELqqd2a4GhqqvelSpla0XNmLBz-c4QN3U"
ENABLE_DUMP = True
DUMP_CHANNEL_ID = int(os.getenv("DUMP_CHANNEL_ID", "-1003758304454"))  # -100xxxx
# ============================================

bot = Client("zip_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_sessions = {}

# ================== UTILS ==================
def safe_filename(name):
    return re.sub(r"[^\w\-.]", "_", name)

async def progress_bar(current, total, message, start, prefix="Progress"):
    if total == 0:
        return
    elapsed = (datetime.now() - start).total_seconds()
    speed = current / elapsed if elapsed else 0
    percent = current * 100 / total
    bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
    text = (
        f"📦 **{prefix}**\n"
        f"`[{bar}]` {percent:.2f}%\n"
        f"{current//1024//1024}MB / {total//1024//1024}MB\n"
        f"⚡ {speed/1024/1024:.2f} MB/s"
    )
    try:
        await message.edit(text)
    except:
        pass

async def upload(bot, message, path):
    progress_msg = await message.reply("⏳ Uploading...")
    await message.reply_document(
        path,
        progress=progress_bar,
        progress_args=(progress_msg, datetime.now(), "Uploading")
    )
    if ENABLE_DUMP and DUMP_CHANNEL_ID:
        await bot.send_document(
            DUMP_CHANNEL_ID,
            path,
            caption=f"📦 From user {message.from_user.id}"
        )

# ================== COMMANDS ==================
@bot.on_message(filters.command("start"))
async def start(bot, message):
    await message.reply(
        "📦 **ZIP BOT READY**\n\n"
        "/zip – Zip files\n"
        "/rejoin – Rejoin split ZIPs\n"
        "/unzip – Extract ZIP / RAR\n"
        "/rename – Rename ZIP\n"
        "/cancel – Cancel task"
    )

@bot.on_message(filters.command("cancel"))
async def cancel(bot, message):
    user_sessions.pop(message.from_user.id, None)
    await message.reply("❌ Task cancelled.")

@bot.on_message(filters.command("zip"))
async def zip_start(bot, message):
    user_sessions[message.from_user.id] = {"mode": "zip", "status": "collecting", "files": []}
    await message.reply("📦 Send file(s) to zip.\nSend /done when finished.")

@bot.on_message(filters.command("rejoin"))
async def rejoin_start(bot, message):
    user_sessions[message.from_user.id] = {"mode": "rejoin", "status": "collecting", "files": []}
    await message.reply("🔗 Send ALL split ZIP parts (.001, .002...).\nSend /done.")

@bot.on_message(filters.command("unzip"))
async def unzip_start(bot, message):
    user_sessions[message.from_user.id] = {"mode": "unzip", "status": "waiting", "files": []}
    await message.reply("📂 Send ZIP or RAR file.")

@bot.on_message(filters.command("rename"))
async def rename_start(bot, message):
    user_sessions[message.from_user.id] = {"mode": "rename", "status": "waiting", "files": []}
    await message.reply("✏️ Send the ZIP file to rename.")

# ================== FILE COLLECT ==================
@bot.on_message(filters.document | filters.video | filters.photo)
async def collect(bot, message):
    session = user_sessions.get(message.from_user.id)
    if not session:
        return
    file = message.document or message.video or message.photo
    name = getattr(file, "file_name", f"{file.file_id}.bin")
    session["files"].append({"file_id": file.file_id, "file_name": safe_filename(name)})
    await message.reply(f"✅ Added `{name}`")

# ================== DONE ROUTER ==================
@bot.on_message(filters.command("done"))
async def done(bot, message):
    session = user_sessions.get(message.from_user.id)
    if not session or not session["files"]:
        return await message.reply("⚠️ No files received.")

    mode = session["mode"]
    if mode == "zip":
        session["status"] = "ask_name"
        await message.reply("✏️ Send ZIP name")
    elif mode == "unzip":
        await handle_unzip(bot, message, session)
    elif mode == "rejoin":
        await handle_rejoin(bot, message, session)
    elif mode == "rename":
        session["status"] = "waiting_new_name"
        await message.reply("✏️ Send new name for the ZIP")

# ================== TEXT FLOW ==================
bot.on_message(filters.command(["zip","rejoin","unzip","rename"]))
async def text_flow(bot, message):
    session = user_sessions.get(message.from_user.id)
    if not session:
        return
    status = session.get("status")

    # ZIP name
    if status == "ask_name":
        session["zip_name"] = safe_filename(message.text) + ".zip"
        session["status"] = "ask_password"
        await message.reply("🔐 Password protect? (yes / no)")

    # Password
    elif status == "ask_password":
        if message.text.lower() == "yes":
            session["status"] = "waiting_password"
            await message.reply("🔑 Send password")
        else:
            session["password"] = None
            await create_zip(bot, message, session)

    elif status == "waiting_password":
        session["password"] = message.text
        await create_zip(bot, message, session)

    # Rename ZIP
    elif status == "waiting_new_name":
        zip_file = session["files"][0]
        progress_msg = await message.reply("⏳ Downloading ZIP for rename...")
        path = await bot.download_media(
            zip_file["file_id"],
            progress=progress_bar,
            progress_args=(progress_msg, datetime.now(), "Downloading")
        )
        new_name = safe_filename(message.text) + ".zip"
        new_path = os.path.join(os.path.dirname(path), new_name)
        os.rename(path, new_path)
        await upload(bot, message, new_path)
        user_sessions.pop(message.from_user.id, None)

# ================== ZIP CREATE ==================
async def create_zip(bot, message, session):
    progress_msg = await message.reply("⏳ Zipping...")
    with tempfile.TemporaryDirectory() as tmp:
        files_dir = os.path.join(tmp, "files")
        os.mkdir(files_dir)
        # Download files
        for f in session["files"]:
            start = datetime.now()
            await bot.download_media(
                f["file_id"],
                os.path.join(files_dir, f["file_name"]),
                progress=progress_bar,
                progress_args=(progress_msg, start, "Downloading")
            )
        # Create ZIP
        zip_path = os.path.join(tmp, session["zip_name"])
        cmd = ["7z", "a", zip_path, files_dir, "-y"]
        if session.get("password"):
            cmd.insert(2, f"-p{session['password']}")
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await upload(bot, message, zip_path)
    user_sessions.pop(message.from_user.id, None)

# ================== REJOIN ==================
async def handle_rejoin(bot, message, session):
    progress_msg = await message.reply("⏳ Rejoining ZIP parts...")
    with tempfile.TemporaryDirectory() as tmp:
        # Download all parts
        parts = []
        for f in session["files"]:
            path = os.path.join(tmp, f["file_name"])
            start = datetime.now()
            await bot.download_media(
                f["file_id"],
                path,
                progress=progress_bar,
                progress_args=(progress_msg, start, "Downloading")
            )
            parts.append(path)
        parts.sort()
        extract_dir = os.path.join(tmp, "ext")
        os.mkdir(extract_dir)
        cmd = ["7z", "x"] + parts + [f"-o{extract_dir}", "-y"]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Upload
        await message.reply("✅ Rejoin complete. Uploading files...")
        for f in os.listdir(extract_dir):
            await upload(bot, message, os.path.join(extract_dir, f))
    user_sessions.pop(message.from_user.id, None)

# ================== UNZIP ==================
async def handle_unzip(bot, message, session):
    progress_msg = await message.reply("⏳ Downloading archive...")
    with tempfile.TemporaryDirectory() as tmp:
        zip_file = session["files"][0]
        path = await bot.download_media(
            zip_file["file_id"],
            tmp,
            progress=progress_bar,
            progress_args=(progress_msg, datetime.now(), "Downloading")
        )
        out_dir = os.path.join(tmp, "out")
        os.mkdir(out_dir)
        await message.reply("⏳ Extracting...")
        subprocess.run(["7z", "x", path, f"-o{out_dir}", "-y"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for f in os.listdir(out_dir):
            await upload(bot, message, os.path.join(out_dir, f))
    user_sessions.pop(message.from_user.id, None)

# ================== HEALTH SERVER ==================
def run_health():
    app = Flask("health")
    @app.route("/")
    def ok():
        return "OK", 200
    app.run(host="0.0.0.0", port=8000)

# ================== START ==================
if __name__ == "__main__":
    threading.Thread(target=run_health, daemon=True).start()
    bot.run()
