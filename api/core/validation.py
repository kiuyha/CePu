"""Helper validasi payload umum untuk router detect dan reports."""
from typing import Optional

from fastapi import UploadFile

from .config import Settings
from .errors import (
    EmptyPayloadError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)


def ensure_not_empty(*fields: Optional[str], image: Optional[UploadFile] = None) -> None:
    has_text_field = any(f is not None and f.strip() != "" for f in fields)
    has_image = image is not None and image.filename not in (None, "")
    if not has_text_field and not has_image:
        raise EmptyPayloadError("Payload kosong: isi minimal satu field atau lampirkan gambar.")


async def validate_image(image: UploadFile, settings: Settings) -> bytes:
    if image.content_type not in settings.allowed_image_content_types:
        raise UnsupportedMediaTypeError(
            f"Tipe file '{image.content_type}' tidak didukung. "
            f"Gunakan salah satu dari: {', '.join(settings.allowed_image_content_types)}."
        )

    contents = await image.read()
    if len(contents) > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes / (1024 * 1024)
        raise PayloadTooLargeError(f"Ukuran file melebihi batas {max_mb:.0f} MB.")

    await image.seek(0)
    return contents
