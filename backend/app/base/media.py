"""Provider-neutral media encoding primitives."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Union


def encode_bytes_to_base64(data: bytes) -> str:
    """Encode in-memory binary media as base64 text for JSON transports."""
    return base64.standard_b64encode(data).decode("utf-8")


def get_media_type(file_path: Union[str, Path]) -> str:
    """Infer the MIME type used by runtime media parts from a file extension."""
    extension_to_mime = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    ext = Path(file_path).suffix.lower()
    return extension_to_mime.get(ext, "application/octet-stream")
