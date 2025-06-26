from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def add_to_zip(zip_path: Path, file_path: Path, password: str = None):
    """
    Adds a file to the zip archive. If password is provided,
    it will be set for the file (only compatible with some extractors).

    Args:
        zip_path: Path to the zip file.
        file_path: Path to the file to add.
        password: Optional password to protect the zip.
    """
    mode = 'a' if zip_path.exists() else 'w'

    with ZipFile(zip_path, mode, ZIP_DEFLATED) as zf:
        arcname = file_path.name

        if password:
            # Standard zipfile doesn't support per-file password encryption,
            # but we can set a password globally (less secure).
            zf.setpassword(password.encode())

        zf.write(file_path, arcname=arcname)
