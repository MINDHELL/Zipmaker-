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

async def upload(bot, message, path, caption=None):
    await message.reply_document(path, caption=caption or f"📦 {os.path.basename(path)}")
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
    user_sessions[message.from_user.id] = {
        "mode": "zip",
        "status": "collecting",
        "files": []
    }
    await message.reply("📦 Send file(s) to zip.\nSend /done when finished.")

@bot.on_message(filters.command("rejoin"))
async def rejoin_start(bot, message):
    user_sessions[message.from_user.id] = {
        "mode": "rejoin",
        "status": "collecting",
        "files": []
    }
    await message.reply("🔗 Send ALL split ZIP parts (.001, .002...)\nSend /done.")

@bot.on_message(filters.command("unzip"))
async def unzip_start(bot, message):
    user_sessions[message.from_user.id] = {
        "mode": "unzip",
        "status": "waiting",
        "files": []
    }
    await message.reply("📂 Send ZIP or RAR file(s).")

@bot.on_message(filters.command("rename"))
async def rename_start(bot, message):
    user_sessions[message.from_user.id] = {
        "mode": "rename",
        "status": "waiting_file",
        "files": []
    }
    await message.reply("✏️ Send the ZIP file you want to rename.")

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
    elif mode == "rejoin":
        await handle_rejoin(bot, message, session)
    elif mode == "unzip":
        await handle_unzip(bot, message, session)
    elif mode == "rename":
        await handle_rename(bot, message, session)

# ================== TEXT FLOW ==================
@bot.on_message(filters.text & ~filters.command(["start", "zip", "rejoin", "unzip", "done", "cancel"]))
async def text_flow(bot, message):
    session = user_sessions.get(message.from_user.id)
    if not session:
        return

    status = session.get("status")
    if status == "ask_name":
        session["zip_name"] = safe_filename(message.text) + ".zip"
        session["status"] = "ask_password"
        await message.reply("🔐 Password protect? (yes / no)")
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
    elif status == "choose_output":
        if message.text.startswith("1"):
            for f in os.listdir(session["extract_dir"]):
                await upload(bot, message, os.path.join(session["extract_dir"], f))
        else:
            out_zip = os.path.join(session["extract_dir"], "final.zip")
            subprocess.run(["7z", "a", "-v2000m", out_zip, os.path.join(session["extract_dir"], "*")])
            for f in os.listdir(session["extract_dir"]):
                if f.endswith(".zip"):
                    await upload(bot, message, os.path.join(session["extract_dir"], f))
        user_sessions.pop(message.from_user.id, None)
    elif status == "waiting_new_name":
        new_name = safe_filename(message.text) + ".zip"
        old_path = session["files"][0]["local_path"]
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        os.rename(old_path, new_path)
        await upload(bot, message, new_path)
        user_sessions.pop(message.from_user.id, None)

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
        if session.get("password"):
            subprocess.run(["7z", "a", f"-p{session['password']}", zip_path, files_dir])
        else:
            subprocess.run(["7z", "a", zip_path, files_dir])

        await upload(bot, message, zip_path)

    user_sessions.pop(message.from_user.id, None)

# ================== REJOIN ==================
async def handle_rejoin(bot, message, session):
    with tempfile.TemporaryDirectory() as tmp:
        for f in session["files"]:
            await bot.download_media(f["file_id"], os.path.join(tmp, f["file_name"]))

        parts = sorted([os.path.join(tmp, f) for f in os.listdir(tmp)])
        extract_dir = os.path.join(tmp, "ext")
        os.mkdir(extract_dir)

        # Join all parts
        first_part = parts[0]
        subprocess.run(["7z", "x", first_part, f"-o{extract_dir}", "-y"], cwd=tmp)

        session["extract_dir"] = extract_dir
        session["status"] = "choose_output"

        await message.reply(
            "📤 Choose output:\n"
            "1️⃣ Upload extracted files\n"
            "2️⃣ Upload as ZIPs (2GB each)"
        )

# ================== UNZIP ==================
async def handle_unzip(bot, message, session):
    with tempfile.TemporaryDirectory() as tmp:
        for f in session["files"]:
            path = await bot.download_media(f["file_id"], tmp)
            out = os.path.join(tmp, "out")
            os.mkdir(out)
            subprocess.run(["7z", "x", path, f"-o{out}", "-y"])
            for file in os.listdir(out):
                await upload(bot, message, os.path.join(out, file))

    user_sessions.pop(message.from_user.id, None)

# ================== RENAME ==================
async def handle_rename(bot, message, session):
    f = session["files"][0]
    tmp = tempfile.gettempdir()
    local_path = os.path.join(tmp, f["file_name"])
    await bot.download_media(f["file_id"], local_path)
    session["files"][0]["local_path"] = local_path
    session["status"] = "waiting_new_name"
    await message.reply("✏️ Send the new ZIP name")

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
