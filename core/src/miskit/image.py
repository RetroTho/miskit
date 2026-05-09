import json
import mimetypes
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4


SUPPORTED_IMAGE_MIME_TYPES = {
    "image/bmp",
    "image/gif",
    "image/heic",
    "image/heif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}

MODEL_IMAGE_MIME_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


class ImageStore:
    def __init__(self, root):
        self.root = Path(root).expanduser()

    def setup(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, data, mime_type=None, filename=None):
        self.setup()
        media_id = self._media_id()
        mime_type = self._mime_type(mime_type=mime_type, filename=filename)
        suffix = self._suffix(filename=filename, mime_type=mime_type)
        path = self.root / f"{media_id}{suffix}"
        path.write_bytes(data)
        path, mime_type = self._normalize_for_model(path, mime_type)
        metadata = self._metadata(media_id, path, mime_type)
        self._write_metadata(metadata)
        return metadata

    def copy_file(self, path, mime_type=None):
        self.setup()
        source = Path(path).expanduser()
        media_id = self._media_id()
        mime_type = self._mime_type(mime_type=mime_type, filename=source.name)
        suffix = self._suffix(filename=source.name, mime_type=mime_type)
        destination = self.root / f"{media_id}{suffix}"
        shutil.copy2(source, destination)
        destination, mime_type = self._normalize_for_model(destination, mime_type)
        metadata = self._metadata(media_id, destination, mime_type)
        self._write_metadata(metadata)
        return metadata

    def is_supported_image(self, mime_type=None, filename=None):
        mime_type = self._mime_type(mime_type=mime_type, filename=filename)
        return mime_type in SUPPORTED_IMAGE_MIME_TYPES

    def _metadata(self, media_id, path, mime_type):
        return {
            "media_id": media_id,
            "path": str(path.resolve()),
            "mime_type": mime_type,
            "size": path.stat().st_size,
        }

    def _write_metadata(self, metadata):
        metadata_path = self.root / f"{metadata['media_id']}.json"
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    def _media_id(self):
        return uuid4().hex

    def _mime_type(self, mime_type=None, filename=None):
        if mime_type:
            return str(mime_type)
        guessed, _ = mimetypes.guess_type(str(filename or ""))
        return guessed or "application/octet-stream"

    def _suffix(self, filename=None, mime_type=None):
        suffix = Path(str(filename or "")).suffix
        if suffix:
            return suffix

        guessed = mimetypes.guess_extension(str(mime_type or ""))
        if guessed:
            return guessed
        return ".bin"

    def _normalize_for_model(self, path, mime_type):
        if mime_type in MODEL_IMAGE_MIME_TYPES:
            return path, mime_type
        if not str(mime_type).startswith("image/"):
            return path, mime_type

        converted = path.with_suffix(".jpg")
        if converted == path:
            converted = path.with_name(path.stem + "-converted.jpg")

        if self._convert_to_jpeg(path, converted):
            if path.exists():
                path.unlink()
            return converted, "image/jpeg"

        return path, mime_type

    def _convert_to_jpeg(self, source, destination):
        if shutil.which("sips") is None:
            return False

        process = subprocess.run(
            ["sips", "-s", "format", "jpeg", str(source), "--out", str(destination)],
            capture_output=True,
            text=True,
            check=False,
        )
        return process.returncode == 0 and destination.exists()
