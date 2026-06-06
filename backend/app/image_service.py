"""Image processing for uploads.

Three jobs, all pure-Pillow (no external services):

1. **Validate by the real bytes** — we decode the upload with Pillow and read its
   actual format, so a renamed `.exe` or a spoofed `Content-Type` is rejected
   here (magic-byte sniffing, not a trusted header).
2. **Downsize + recompress** the stored "full" image, capping the long edge so
   the envelope/hero load fast and the NAS disk doesn't fill with 12 MP phone
   photos.
3. **Generate a small thumbnail** served for host cards, the gallery grid, and
   the envelope letter.

Returns web-friendly bytes the caller writes to the uploads dir.
"""
import io

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

# Formats we accept, keyed by Pillow's own identifier (read from the bytes).
_ALLOWED = {"JPEG", "PNG", "WEBP", "GIF"}
_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}

MAX_DIM = 1600   # long edge of the stored full image
THUMB_DIM = 480  # long edge of the thumbnail

# Decompression-bomb guard: refuse absurdly large images before allocating them.
Image.MAX_IMAGE_PIXELS = 64_000_000  # ~64 MP


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def sniff_format(data: bytes) -> str:
    """The real image format from the bytes, or HTTP 400 if it isn't a supported
    image. This is the magic-byte validation that replaces trusting Content-Type."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="That file isn't a valid image")
    if fmt not in _ALLOWED:
        raise HTTPException(
            status_code=400, detail="Unsupported image type (use JPEG, PNG, WebP, or GIF)"
        )
    return fmt


def _encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=85, optimize=True, progressive=True)
    elif fmt == "PNG":
        img.save(buf, "PNG", optimize=True)
    elif fmt == "WEBP":
        img.save(buf, "WEBP", quality=82, method=4)
    else:
        img.save(buf, fmt)
    return buf.getvalue()


def process(data: bytes) -> tuple[bytes, str, bytes, str]:
    """Validate + normalise an upload.

    Returns ``(full_bytes, full_ext, thumb_bytes, thumb_ext)`` — the caller
    writes each to the uploads dir. Raises HTTP 400 if the bytes aren't a
    supported image.
    """
    fmt = sniff_format(data)

    # Animated GIFs are kept verbatim for the full image so the animation
    # survives; everything else is orientation-fixed, downsized, recompressed.
    if fmt == "GIF":
        full_bytes, full_ext = data, ".gif"
    else:
        with Image.open(io.BytesIO(data)) as src:
            img = ImageOps.exif_transpose(src)  # honour camera rotation, then drop EXIF
            if max(img.size) > MAX_DIM:
                img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
            full_bytes, full_ext = _encode(img, fmt), _EXT[fmt]

    # Thumbnail: a small still (JPEG, or PNG when the source is transparent).
    with Image.open(io.BytesIO(data)) as src:
        thumb = ImageOps.exif_transpose(src)
        thumb.thumbnail((THUMB_DIM, THUMB_DIM), Image.LANCZOS)
        if _has_alpha(thumb):
            thumb_bytes, thumb_ext = _encode(thumb, "PNG"), ".png"
        else:
            thumb_bytes, thumb_ext = _encode(thumb, "JPEG"), ".jpg"

    return full_bytes, full_ext, thumb_bytes, thumb_ext
