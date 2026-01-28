import os
import re
import tempfile
import subprocess
import threading
from datetime import datetime

from pyrogram import Client, filters
from flask import Flask

# ================= CONFIG =================

API_ID = 37371391
API_HASH = "37895f967d284f6781f99e9beef21ebf"
BOT_TOKEN = "8229073869:AAELqqd2a4GhqqvelSpla0XNmLBz-c4QN3U"

ENABLE_DUMP = True
DUMP_CHANNEL_ID = int(os.getenv("DUMP_CHANNEL_ID", "-1003758304454"))

# ========================================

bot = Client("zip_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
sessions = {}

# ================= UTILS =================

def safe(name):
    if not name:
        return "file.bin"
    return re.sub(r"[^\w\-.]", "_", str(name))


async def progress_bar(current, total, msg, start, title):
    if total == 0:
        return
    percent = current * 100 / total
    filled = int(percent / 5)
    bar = "█" * filled + "░" * (20 - filled)
    speed = current / max((datetime.now() - start).total_seconds(), 1)

    try:
        await msg.edit(
            f"📦 **{title}**\n"
            f"`[{bar}]` {percent:.1f}%\n"
            f"{current//1024//1024}MB / {total//1024//1024}MB\n"
            f"⚡ {speed/1024/1024:.2f} MB/s"
        )
    except:
        pass


async def upload_file(bot, message, path):
    await message.reply_document(path)
    if ENABLE_DUMP and DUMP_CHANNEL_ID:
        await bot.send_document(DUMP_CHANNEL_ID, path)


async def upload_folder(bot, message, folder):
    for root, _, files in os.walk(folder):
        for f in files:
            await upload_file(bot, message, os.path.join(root, f))

# ================= COMMANDS =================

@bot.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(
        "📦 **ZIP BOT READY**\n\n"
        "/zip – Zip files\n"
        "/unzip – Extract ZIP/RAR\n"
        "/rejoin – Rejoin split ZIPs\n"
        "/rename – Rename ZIP\n"
        "/cancel – Cancel task"
    )


@bot.on_message(filters.command("cancel"))
async def cancel(_, m):
    sessions.pop(m.from_user.id, None)
    await m.reply("❌ Cancelled")


@bot.on_message(filters.command("zip"))
async def zip_start(_, m):
    sessions[m.from_user.id] = {"mode": "zip", "files": [], "step": "collect"}
    await m.reply("📤 Send files → /done")


@bot.on_message(filters.command("unzip"))
async def unzip_start(_, m):
    sessions[m.from_user.id] = {"mode": "unzip", "files": []}
    await m.reply("📂 Send ZIP/RAR → /done")


@bot.on_message(filters.command("rejoin"))
async def rejoin_start(_, m):
    sessions[m.from_user.id] = {"mode": "rejoin", "files": []}
    await m.reply("🔗 Send all parts (.001, .002…) → /done")


@bot.on_message(filters.command("rename"))
async def rename_start(_, m):
    sessions[m.from_user.id] = {"mode": "rename", "files": [], "step": "collect"}
    await m.reply("✏️ Send ZIP → /done")

# ================= FILE COLLECT =================

@bot.on_message(filters.private & (filters.document | filters.video | filters.photo))
async def collect(_, m):
    s = sessions.get(m.from_user.id)
    if not s:
        return

    media = m.document or m.video or m.photo

    name = (
        media.file_name
        if getattr(media, "file_name", None)
        else f"{media.file_id}.bin"
    )

    s["files"].append({
        "id": media.file_id,
        "name": safe(name)
    })

    await m.reply(f"✅ `{safe(name)}` added")

# ================= DONE =================

@bot.on_message(filters.command("done"))
async def done(_, m):
    s = sessions.get(m.from_user.id)
    if not s or not s["files"]:
        return await m.reply("⚠️ No files")

    if s["mode"] == "zip":
        s["step"] = "name"
        return await m.reply("✏️ ZIP name?")

    if s["mode"] == "rename":
        s["step"] = "rename"
        return await m.reply("✏️ New name?")

    if s["mode"] == "unzip":
        return await unzip(bot, m, s)

    if s["mode"] == "rejoin":
        return await rejoin(bot, m, s)

# ================= TEXT FLOW (FIXED) =================

@bot.on_message(filters.private & filters.text & ~filters.command)
async def text_flow(_, m):
    s = sessions.get(m.from_user.id)
    if not s:
        return

    if s.get("step") == "name":
        s["zip_name"] = safe(m.text) + ".zip"
        s["step"] = "pass"
        return await m.reply("🔐 Password? (yes/no)")

    if s.get("step") == "pass":
        if m.text.lower() == "yes":
            s["step"] = "pwd"
            return await m.reply("🔑 Send password")
        s["pwd"] = None
        return await make_zip(bot, m, s)

    if s.get("step") == "pwd":
        s["pwd"] = m.text
        return await make_zip(bot, m, s)

    if s.get("step") == "rename":
        return await rename(bot, m, s)

# ================= ZIP =================

async def make_zip(bot, m, s):
    msg = await m.reply("⏳ Downloading...")
    with tempfile.TemporaryDirectory() as tmp:
        files_dir = os.path.join(tmp, "files")
        os.mkdir(files_dir)

        for f in s["files"]:
            await bot.download_media(
                f["id"],
                os.path.join(files_dir, f["name"]),
                progress=progress_bar,
                progress_args=(msg, datetime.now(), "Downloading")
            )

        zip_path = os.path.join(tmp, s["zip_name"])
        cmd = ["7z", "a", zip_path, files_dir]
        if s.get("pwd"):
            cmd.insert(2, f"-p{s['pwd']}")

        subprocess.run(cmd, check=True)
        await upload_file(bot, m, zip_path)

    sessions.pop(m.from_user.id, None)

# ================= UNZIP =================

async def unzip(bot, m, s):
    msg = await m.reply("⏳ Extracting...")
    with tempfile.TemporaryDirectory() as tmp:
        f = s["files"][0]
        path = await bot.download_media(f["id"], tmp)

        out = os.path.join(tmp, "out")
        os.mkdir(out)

        subprocess.run(["7z", "x", path, f"-o{out}", "-y"], check=True)
        await upload_folder(bot, m, out)

    sessions.pop(m.from_user.id, None)

# ================= REJOIN =================

async def rejoin(bot, m, s):
    msg = await m.reply("⏳ Rejoining...")
    with tempfile.TemporaryDirectory() as tmp:
        for f in s["files"]:
            await bot.download_media(f["id"], os.path.join(tmp, f["name"]))

        parts = sorted(os.listdir(tmp))
        first = os.path.join(tmp, parts[0])

        out = os.path.join(tmp, "out")
        os.mkdir(out)

        subprocess.run(["7z", "x", first, f"-o{out}", "-y"], check=True)
        await upload_folder(bot, m, out)

    sessions.pop(m.from_user.id, None)

# ================= RENAME =================

async def rename(bot, m, s):
    msg = await m.reply("⏳ Renaming...")
    with tempfile.TemporaryDirectory() as tmp:
        f = s["files"][0]
        old = await bot.download_media(f["id"], tmp)
        new = os.path.join(tmp, safe(m.text) + ".zip")
        os.rename(old, new)
        await upload_file(bot, m, new)

    sessions.pop(m.from_user.id, None)

# ================= HEALTH =================

def health():
    app = Flask("health")

    @app.route("/")
    def ok():
        return "OK"

    app.run("0.0.0.0", 8000)

# ================= START =================

if __name__ == "__main__":
    threading.Thread(target=health, daemon=True).start()
    bot.run()
