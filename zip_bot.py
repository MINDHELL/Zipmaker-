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

async def progress_bar(current, total, message, start, prefix):
    if total == 0:
        return
    elapsed = (datetime.now() - start).total_seconds()
    speed = current / elapsed if elapsed else 0
    percent = current * 100 / total
    bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
    try:
        await message.edit(
            f"📦 **{prefix}**\n"
            f"`[{bar}]` {percent:.2f}%\n"
            f"{current//1024//1024}MB / {total//1024//1024}MB\n"
            f"⚡ {speed/1024/1024:.2f} MB/s"
        )
    except:
        pass

async def upload(bot, message, path):
    if os.path.isfile(path):
        await message.reply_document(path)
        if ENABLE_DUMP and DUMP_CHANNEL_ID:
            await bot.send_document(
                DUMP_CHANNEL_ID,
                path,
                caption=f"📦 From user {message.from_user.id}"
            )

async def upload_all_files(bot, message, folder_path):
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            full_path = os.path.join(root, f)
            await upload(bot, message, full_path)

# ================== COMMANDS ==================
@bot.on_message(filters.command("start"))
async def start(bot, message):
    await message.reply(
        "📦 **ZIP BOT READY**\n\n"
        "/zip – Zip files\n"
        "/rejoin – Rejoin split ZIPs\n"
        "/unzip – Extract ZIP / RAR\n"
        "/rename – Rename ZIP before sending\n"
        "/cancel – Cancel task"
    )

@bot.on_message(filters.command("cancel"))
async def cancel(bot, message):
    user_sessions.pop(message.from_user.id, None)
    await message.reply("❌ Task cancelled.")

# ================== SESSION START ==================
@bot.on_message(filters.command(["zip","rejoin","unzip","rename"]))
async def start_session(bot, message):
    cmd = message.text[1:].split()[0].lower()
    mode = cmd
    user_sessions[message.from_user.id] = {
        "mode": mode,
        "status": "collecting" if mode in ["zip","rejoin"] else "waiting",
        "files": []
    }
    if mode == "zip":
        await message.reply("📦 Send files to zip. /done when finished.")
    elif mode == "rejoin":
        await message.reply("🔗 Send all split parts (.001/.002...). /done when finished.")
    elif mode == "unzip":
        await message.reply("📂 Send ZIP or RAR file to extract.")
    elif mode == "rename":
        await message.reply("✏️ Send ZIP file to rename.")

# ================== FILE COLLECT ==================
@bot.on_message(filters.document | filters.video | filters.photo)
async def collect(bot, message):
    session = user_sessions.get(message.from_user.id)
    if not session:
        return

    file = message.document or message.video or message.photo
    name = getattr(file, "file_name", f"{file.file_id}.bin")
    session["files"].append({
        "file_id": file.file_id,
        "file_name": safe_filename(name)
    })
    await message.reply(f"✅ Added `{name}`")

# ================== DONE HANDLER ==================
@bot.on_message(filters.command("done"))
async def done(bot, message):
    session = user_sessions.get(message.from_user.id)
    if not session or not session["files"]:
        return await message.reply("⚠️ No files received.")

    if session["mode"] == "zip":
        session["status"] = "ask_name"
        await message.reply("✏️ Send ZIP name")
    elif session["mode"] == "rename":
        session["status"] = "ask_name"
        await message.reply("✏️ Send new ZIP name")
    elif session["mode"] == "rejoin":
        await handle_rejoin(bot, message, session)
    elif session["mode"] == "unzip":
        await handle_unzip(bot, message, session)

# ================== TEXT FLOW ==================
bot.on_message(filters.command(["zip","rejoin","unzip","rename"]))
async def text_flow(bot, message):
    session = user_sessions.get(message.from_user.id)
    if not session:
        return

    if session["status"] == "ask_name":
        zip_name = safe_filename(message.text)
        if not zip_name.endswith(".zip"):
            zip_name += ".zip"
        session["zip_name"] = zip_name
        if session["mode"] == "zip":
            session["status"] = "ask_password"
            await message.reply("🔐 Password protect? (yes / no)")
        elif session["mode"] == "rename":
            # Only rename
            await rename_zip(bot, message, session)

    elif session["status"] == "ask_password":
        if message.text.lower() == "yes":
            session["status"] = "waiting_password"
            await message.reply("🔑 Send password")
        else:
            session["password"] = None
            await create_zip(bot, message, session)

    elif session["status"] == "waiting_password":
        session["password"] = message.text
        await create_zip(bot, message, session)

# ================== ZIP CREATE ==================
async def create_zip(bot, message, session):
    progress = await message.reply("⏳ Zipping...")
    with tempfile.TemporaryDirectory() as tmp:
        files_dir = os.path.join(tmp, "files")
        os.mkdir(files_dir)
        for f in session["files"]:
            start = datetime.now()
            await bot.download_media(
                f["file_id"],
                os.path.join(files_dir, f["file_name"]),
                progress=progress_bar,
                progress_args=(progress, start, "Downloading")
            )

        zip_path = os.path.join(tmp, session["zip_name"])
        cmd = ["7z", "a"]
        if session.get("password"):
            cmd.append(f"-p{session['password']}")
        cmd += [zip_path, files_dir]
        subprocess.run(cmd)
        await upload(bot, message, zip_path)

    user_sessions.pop(message.from_user.id, None)

# ================== RENAME ==================
async def rename_zip(bot, message, session):
    f = session["files"][0]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f["file_name"])
        await bot.download_media(f["file_id"], path)
        new_path = os.path.join(tmp, session["zip_name"])
        os.rename(path, new_path)
        await upload(bot, message, new_path)
    user_sessions.pop(message.from_user.id, None)

# ================== UNZIP ==================
async def handle_unzip(bot, message, session):
    progress = await message.reply("⏳ Extracting...")
    with tempfile.TemporaryDirectory() as tmp:
        f = session["files"][0]
        path = os.path.join(tmp, f["file_name"])
        await bot.download_media(f["file_id"], path, progress=progress_bar, progress_args=(progress, datetime.now(), "Downloading"))

        out_dir = os.path.join(tmp, "out")
        os.mkdir(out_dir)
        subprocess.run(["7z", "x", path, f"-o{out_dir}", "-y"])
        await upload_all_files(bot, message, out_dir)

    user_sessions.pop(message.from_user.id, None)

# ================== REJOIN ==================
async def handle_rejoin(bot, message, session):
    progress = await message.reply("⏳ Rejoining parts...")
    with tempfile.TemporaryDirectory() as tmp:
        files = sorted(session["files"], key=lambda x: x["file_name"])
        for f in files:
            await bot.download_media(f["file_id"], os.path.join(tmp, f["file_name"]), progress=progress_bar, progress_args=(progress, datetime.now(), "Downloading"))

        extract_dir = os.path.join(tmp, "extract")
        os.mkdir(extract_dir)
        first_part = os.path.join(tmp, files[0]["file_name"])
        subprocess.run(["7z", "x", first_part, f"-o{extract_dir}", "-y"])
        await upload_all_files(bot, message, extract_dir)

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
