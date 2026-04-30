"""Neutral runtime media builders for source extraction."""

from __future__ import annotations

from app.agents.runtime import MediaPart
from app.base.media import encode_bytes_to_base64


def pdf_page_part(*, filename: str, page_number: int, data: bytes) -> MediaPart:
    """Return one labeled PDF page/document part for model extraction."""
    return MediaPart(
        kind="document",
        media_type="application/pdf",
        data=encode_bytes_to_base64(data),
        title=f"{filename} - Page {page_number}",
    )


def pptx_slide_part(*, filename: str, slide_number: int, data: bytes) -> MediaPart:
    """Return one labeled slide document part for model extraction."""
    return MediaPart(
        kind="document",
        media_type="application/pdf",
        data=encode_bytes_to_base64(data),
        title=f"{filename} - Slide {slide_number}",
    )


def image_part(*, filename: str, media_type: str, data: bytes) -> MediaPart:
    """Return one labeled image part for model extraction."""
    return MediaPart(
        kind="image",
        media_type=media_type,
        data=encode_bytes_to_base64(data),
        title=filename,
        filename=filename,
    )
