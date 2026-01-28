import os
import re
import asyncio
import tempfile
import threading
import subprocess
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from flask import Flask

# ================= CONFIG =================
API_ID = "37371391"
API_HASH = "37895f967d284f6781f99e9beef21ebf"
BOT_TOKEN = "8064879322:AAHvYtmZRsRamwHqhgUbXW-yZ5rjHhwdE4A"

# OPTIONAL: dump channel (set to None to disable)
DUMP_CHANNEL = -1003758304454  # example: -1001234567890

# =========================================

bot = Client("zip_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_sessions = {}

# ================= HELPERS =================
def safe_filename(name):
    return re.sub(r"[^\w\-.]", "_", name)

async def progress_bar(current, total, message, start, prefix):
    if total == 0:
        return
    elapsed = (datetime.now() - start).total_seconds()
    speed = current / elapsed if elapsed else 0
    percent = current * 100 / total
    bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
    text = (
        f"📦 **{prefix}**\n"
        f"`[{bar}]` {percent:.2f}%\n"
        f"⚡ {speed / 1024**2:.2f} MB/s"
    )
    try:
        await message.edit(text)
    except:
        pass

# ================= COMMANDS =================
@bot.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(
        "👋 **ZIP BOT**\n\n"
        "/zip – Create ZIP\n"
        "/rejoin – Rejoin split ZIPs\n"
        "/unzip – Extract ZIP/RAR\n"
        "/cancel – Cancel session"
    )

@bot.on_message(filters.command("cancel"))
async def cancel(_, m):
    user_sessions.pop(m.from_user.id, None)
    await m.reply("❌ Session cancelled.")

# ================= ZIP =================
@bot.on_message(filters.command("zip"))
async def zip_start(_, m):
    user_sessions[m.from_user.id] = {
        "mode": "zip",
        "files": [],
        "status": "collect"
    }
    await m.reply("📥 Send files. Use /done when finished.")

# ================= REJOIN =================
@bot.on_message(filters.command("rejoin"))
async def rejoin_start(_, m):
    user_sessions[m.from_user.id] = {
        "mode": "rejoin",
        "files": [],
        "status": "collect"
    }
    await m.reply("🔗 Send all split parts (.001, .002…). Use /done")

# ================= UNZIP =================
@bot.on_message(filters.command("unzip"))
async def unzip_start(_, m):
    user_sessions[m.from_user.id] = {
        "mode": "unzip",
        "files": [],
        "status": "collect"
    }
    await m.reply("📂 Send ZIP or RAR file")

# ================= DONE =================
@bot.on_message(filters.command("done"))
async def done(_, m):
    s = user_sessions.get(m.from_user.id)
    if not s or not s["files"]:
        return await m.reply("⚠️ No files received")

    if s["mode"] == "zip":
        s["status"] = "ask_name"
        return await m.reply("✏️ Send ZIP name")

    if s["mode"] == "rejoin":
        return await rejoin_process(m, s)

    if s["mode"] == "unzip":
        return await unzip_process(m, s)

# ================= TEXT HANDLER =================
@bot.on_message(filters.text & ~filters.command)
async def text_handler(_, m):
    s = user_sessions.get(m.from_user.id)
    if not s:
        return

    if s["status"] == "ask_name":
        s["zip_name"] = safe_filename(m.text)
        if not s["zip_name"].endswith(".zip"):
            s["zip_name"] += ".zip"
        s["status"] = "ask_password"
        return await m.reply("🔐 Password? (yes / no)")

    if s["status"] == "ask_password":
        if m.text.lower() == "yes":
            s["status"] = "get_password"
            return await m.reply("🔑 Send password")
        s["password"] = None
        return await zip_process(m, s)

    if s["status"] == "get_password":
        s["password"] = m.text
        return await zip_process(m, s)

# ================= FILE COLLECT =================
@bot.on_message(filters.document | filters.video | filters.photo)
async def collect(_, m):
    s = user_sessions.get(m.from_user.id)
    if not s:
        return

    file = m.document or m.video or m.photo
    name = file.file_name if hasattr(file, "file_name") and file.file_name else f"{file.file_id}"
    s["files"].append({
        "id": file.file_id,
        "name": safe_filename(name)
    })
    await m.reply(f"✅ `{name}` added")

# ================= ZIP PROCESS =================
async def zip_process(m, s):
    msg = await m.reply("⏳ Zipping...")
    with tempfile.TemporaryDirectory() as tmp:
        for f in s["files"]:
            await bot.download_media(f["id"], os.path.join(tmp, f["name"]))

        zip_path = os.path.join(tmp, s["zip_name"])

        cmd = ["7z", "a", zip_path, tmp + "/*"]
        if s["password"]:
            cmd += [f"-p{s['password']}", "-mhe=on"]

        subprocess.run(cmd)

        upload_to = DUMP_CHANNEL if DUMP_CHANNEL else m.chat.id
        sent = await bot.send_document(upload_to, zip_path)
        if DUMP_CHANNEL:
            await m.reply_document(sent.document.file_id)

    user_sessions.pop(m.from_user.id, None)

# ================= REJOIN PROCESS =================
async def rejoin_process(m, s):
    msg = await m.reply("🔗 Rejoining parts...")
    with tempfile.TemporaryDirectory() as tmp:
        for f in s["files"]:
            await bot.download_media(f["id"], os.path.join(tmp, f["name"]))

        first = sorted(os.listdir(tmp))[0]
        out = os.path.join(tmp, "out")
        os.mkdir(out)

        subprocess.run(["7z", "x", first, f"-o{out}", "-y"], cwd=tmp)

        zip_out = os.path.join(tmp, "final.zip")
        subprocess.run(["7z", "a", zip_out, out + "/*", "-v2000m"])

        for part in sorted(os.listdir(tmp)):
            if part.startswith("final.zip"):
                await m.reply_document(os.path.join(tmp, part))

    user_sessions.pop(m.from_user.id, None)

# ================= UNZIP PROCESS =================
async def unzip_process(m, s):
    msg = await m.reply("📂 Extracting...")
    with tempfile.TemporaryDirectory() as tmp:
        f = s["files"][0]
        path = await bot.download_media(f["id"], tmp)
        out = os.path.join(tmp, "out")
        os.mkdir(out)

        subprocess.run(["7z", "x", path, f"-o{out}", "-y"])

        for file in os.listdir(out):
            await m.reply_document(os.path.join(out, file))

    user_sessions.pop(m.from_user.id, None)

# ================= HEALTH SERVER =================
def run_server():
    app = Flask("health")

    @app.route("/")
    def health():
        return "OK", 200

    app.run(host="0.0.0.0", port=8000)

# ================= MAIN =================
if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    bot.run()
