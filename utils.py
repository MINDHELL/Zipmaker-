from typing import AsyncGenerator
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import mimetypes
from tqdm.asyncio import tqdm

from pyrogram.types import Message


async def download_files(
    msgs: list[Message],
    root: Path,
) -> AsyncGenerator[Path, None]:
    """
    Downloads media from a list of messages.

    Args:
        msgs: List of Pyrogram messages.
        root: Directory to save downloaded files.

    Yields:
        Path of each downloaded file.
    """
    root.mkdir(parents=True, exist_ok=True)

    async for msg in tqdm(msgs, desc="Downloading", unit="file"):
        media_name = msg.document.file_name if msg.document else None

        if not media_name:
            # Guess file extension from MIME type
            mime_type = msg.document.mime_type if msg.document else None
            ext = mimetypes.guess_extension(mime_type) or ''
            media_name = f"file_{msg.id}{ext}"

        file_path = await msg.download(file_name=root / media_name)

        if file_path:
            yield Path(file_path)


def add_to_zip(zip_path: Path, file_path: Path, password: str | None = None):
    """
    Adds a file to a ZIP archive.

    Args:
        zip_path: Target ZIP file path.
        file_path: File to add.
        password: Optional password for encryption.
    """
    mode = 'a' if zip_path.exists() else 'w'

    with ZipFile(zip_path, mode, compression=ZIP_DEFLATED) as zipf:
        if password:
            zipf.setpassword(password.encode())
        zipf.write(file_path, arcname=file_path.name)
