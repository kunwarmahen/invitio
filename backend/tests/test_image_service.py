"""Unit tests for image_service (no HTTP/DB)."""
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app import image_service


def _encode(mode, size, fmt, color=(10, 20, 30)):
    buf = io.BytesIO()
    img = Image.new(mode, size, color if mode != "RGBA" else (10, 20, 30, 128))
    img.save(buf, fmt)
    return buf.getvalue()


def test_downsizes_large_image():
    data = _encode("RGB", (3000, 2000), "JPEG")
    full_bytes, full_ext, thumb_bytes, thumb_ext = image_service.process(data)
    full = Image.open(io.BytesIO(full_bytes))
    thumb = Image.open(io.BytesIO(thumb_bytes))
    assert max(full.size) == image_service.MAX_DIM
    assert max(thumb.size) == image_service.THUMB_DIM
    assert full_ext == ".jpg" and thumb_ext == ".jpg"
    assert len(full_bytes) < len(data)  # recompressed smaller


def test_small_image_not_upscaled():
    data = _encode("RGB", (300, 200), "PNG")
    full_bytes, full_ext, _, _ = image_service.process(data)
    full = Image.open(io.BytesIO(full_bytes))
    assert full.size == (300, 200)
    assert full_ext == ".png"


def test_transparent_thumb_is_png():
    data = _encode("RGBA", (600, 600), "PNG")
    _, _, _, thumb_ext = image_service.process(data)
    assert thumb_ext == ".png"


def test_rejects_non_image():
    with pytest.raises(HTTPException) as exc:
        image_service.process(b"definitely not an image")
    assert exc.value.status_code == 400


def test_rejects_unsupported_format():
    # A valid image, but in a format we don't accept (BMP).
    data = _encode("RGB", (100, 100), "BMP")
    with pytest.raises(HTTPException) as exc:
        image_service.process(data)
    assert exc.value.status_code == 400
