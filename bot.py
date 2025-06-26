import os
import time
from pathlib import Path
from zipfile import ZipFile
from pyrogram import Client, filters
from pyrogram.types import Message
from utils import add_to_zip
from tqdm import tqdm
from dotenv import load_dotenv
from shutil import rmtree
import threading
from health_check import start_health_check

load_dotenv()

API_ID = os.getenv("API_ID", "27788368")
API_HASH = os.getenv("API_HASH", "9df7e9ef3d7e4145270045e5e43e1081")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8064879322:AAHvYtmZRsRamwHqhgUbXW-yZ5rjHhwdE4A")

app = Client("zipbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_tasks: dict[int, list[Message]] = {}
rename_map: dict[int, str] = {}
STORAGE = Path("downloads/")


def format_bytes(size):
    # 1024 -> 1 KB, 1024^2 -> 1 MB
    power = 2**10
    n = 0
    power_labels = ["B", "KB", "MB", "GB", "TB"]
    while size >= power and n < len(power_labels) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"


def format_progress_bar(current, total, width=20):
    progress = current / total
    filled = int(width * progress)
    bar = "●" * filled + "○" * (width - filled)
    return f"[{bar}]"


def format_status(current, total, speed, eta):
    percent = (current / total) * 100
    return (
        f"◌Progress😉:〘 {percent:.2f}% 〙\n"
        f"Done: 〘{format_bytes(current)} of {format_bytes(total)}〙\n"
        f"◌Speed🚀:〘 {format_bytes(speed)}/s 〙\n"
        f"◌Time Left⏳:〘 {int(eta)}s 〙"
    )


async def download_with_progress(msg: Message, user_dir: Path, reply: Message):
    start = time.time()
    total_size = msg.document.file_size if msg.document else None
    file_path = None

    async def progress(current, total):
        elapsed = time.time() - start
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0

        progress_bar = format_progress_bar(current, total)
        status = format_status(current, total, speed, eta)

        try:
            await reply.edit_text(
                f"📥 Downloading `{msg.document.file_name}` to my server\n\n"
                f"{progress_bar}\n{status}"
            )
        except Exception:
            pass  # Ignore rapid edit errors

    file_path = await msg.download(
        file_name=user_dir / msg.document.file_name,
        progress=progress,
        progress_args=()
    )
    return file_path


@app.on_message(filters.command("add"))
async def add_handler(client, message: Message):
    user_tasks[message.from_user.id] = []
    await message.reply("✅ Now send me the files you want to zip.")


@app.on_message(filters.media & filters.private)
async def media_handler(client, message: Message):
    if message.from_user.id not in user_tasks:
        return await message.reply("❗ Use /add first.")
    user_tasks[message.from_user.id].append(message)
    await message.reply("📥 File added. Use /zip <name> [password] to finish.")


@app.on_message(filters.reply & filters.regex(r'^name:\s*(.+)'))
async def rename_handler(client, message: Message):
    if message.reply_to_message and message.reply_to_message.media:
        new_name = message.text.split(":", 1)[1].strip()
        rename_map[message.reply_to_message.id] = new_name
        await message.reply(f"✏️ File will be renamed to: `{new_name}`", quote=True)


@app.on_message(filters.command(["zip", "done"]))
async def zip_handler(client, message: Message):
    args = message.text.split(maxsplit=2)
    uid = message.from_user.id

    if uid not in user_tasks or not user_tasks[uid]:
        return await message.reply("❗ No files found. Use /add and send files first.")

    zip_name = args[1] if len(args) > 1 else "archive"
    zip_name = zip_name.replace(".zip", "")
    password = args[2] if len(args) > 2 else None

    user_dir = STORAGE / str(uid)
    user_dir.mkdir(parents=True, exist_ok=True)
    zip_path = user_dir / f"{zip_name}.zip"

    if zip_path.exists():
        zip_path.unlink()

    await message.reply("📦 Downloading and zipping...")

    progress = tqdm(total=len(user_tasks[uid]), desc="Zipping", unit="file")

    for msg in user_tasks[uid]:
        media_name = rename_map.get(msg.id)
        default_name = msg.document.file_name if msg.document else f"{msg.id}"
        reply = await message.reply(f"📤 Downloading `{default_name}`")
        file_path = await download_with_progress(msg, user_dir, reply)

        if file_path:
            add_to_zip(zip_path, Path(file_path), password=password)
            progress.update(1)

    progress.close()
    await message.reply_document(zip_path, caption="✅ Your zip is ready!")

    rmtree(user_dir, ignore_errors=True)
    user_tasks.pop(uid, None)
    rename_map.clear()


@app.on_message(filters.command("preview"))
async def preview_handler(client, message: Message):
    uid = message.from_user.id
    if uid not in user_tasks or not user_tasks[uid]:
        return await message.reply("📂 No files added.")

    text = "📝 **Preview of Files to be Zipped:**\n\n"
    for i, msg in enumerate(user_tasks[uid], 1):
        name = rename_map.get(msg.id, msg.document.file_name if msg.document else "Unnamed")
        text += f"{i}. `{name}`\n"

    await message.reply(text)


@app.on_message(filters.command("list"))
async def list_handler(client, message: Message):
    uid = message.from_user.id
    if uid not in user_tasks or not user_tasks[uid]:
        return await message.reply("📂 No files added.")
    text = "📄 Files added:\n"
    for i, msg in enumerate(user_tasks[uid], 1):
        name = rename_map.get(msg.id, msg.document.file_name if msg.document else "Unnamed")
        text += f"{i}. {name}\n"
    await message.reply(text)


@app.on_message(filters.command("cancel"))
async def cancel_handler(client, message: Message):
    uid = message.from_user.id
    user_tasks.pop(uid, None)
    rename_map.clear()
    await message.reply("❌ Task cancelled. Use /add to start over.")


# ✅ Run the bot
if __name__ == "__main__":
    threading.Thread(target=start_health_check, daemon=True).start()
    app.run()
