#!/usr/bin/env python3
"""Generate invitio's PWA icons with zero dependencies (stdlib zlib only).

Draws a diagonal violet→pink gradient (the brand `.dot` gradient) with a white
four-point "✦" sparkle, supersampled for smooth edges, and writes RGBA PNGs to
frontend/icons/. Run once after changing the look; the PNGs are committed and the
runtime never imports this. Usage: python scripts/generate_icons.py
"""
import math
import os
import struct
import zlib

C0 = (124, 58, 237)   # #7c3aed  (accent / violet)
C1 = (219, 39, 119)   # #db2777  (pink)
WHITE = (255, 255, 255)
STAR_P = 0.55          # |x|^p + |y|^p <= 1 → concave 4-point star (smaller = spikier)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "icons")


def _lerp(a, b, t):
    return int(round(a + (b - a) * t))


def render(size, *, rounded, star_frac, ss=3):
    """Return PNG-ready scanline bytes (filter 0 + RGBA) for an icon."""
    m = size * ss
    cx = cy = (m - 1) / 2.0
    star_r = m * star_frac
    corner = m * 0.22 if rounded else 0.0

    # Supersampled pixel buffer.
    buf = [None] * (m * m)
    for y in range(m):
        for x in range(m):
            alpha = 255
            if corner > 0:                       # rounded-rect corner cutout
                dx = corner - x if x < corner else (x - (m - 1 - corner) if x > m - 1 - corner else 0)
                dy = corner - y if y < corner else (y - (m - 1 - corner) if y > m - 1 - corner else 0)
                if dx > 0 and dy > 0 and dx * dx + dy * dy > corner * corner:
                    alpha = 0
            t = (x + y) / (2 * (m - 1))          # diagonal gradient
            r, g, b = _lerp(C0[0], C1[0], t), _lerp(C0[1], C1[1], t), _lerp(C0[2], C1[2], t)
            nx, ny = abs((x - cx) / star_r), abs((y - cy) / star_r)
            if nx ** STAR_P + ny ** STAR_P <= 1.0:
                r, g, b = WHITE
            buf[y * m + x] = (r, g, b, alpha)

    # Downsample ss×ss (box filter) → final RGBA scanlines.
    n = ss * ss
    raw = bytearray()
    for y in range(size):
        raw.append(0)                            # PNG filter type: none
        for x in range(size):
            rr = gg = bb = aa = 0
            for j in range(ss):
                row = (y * ss + j) * m
                for i in range(ss):
                    px = buf[row + x * ss + i]
                    rr += px[0]; gg += px[1]; bb += px[2]; aa += px[3]
            raw += bytes((rr // n, gg // n, bb // n, aa // n))
    return bytes(raw)


def write_png(path, size, raw):
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    specs = [
        ("icon-192.png", 192, dict(rounded=True, star_frac=0.36)),
        ("icon-512.png", 512, dict(rounded=True, star_frac=0.36)),
        ("icon-maskable-512.png", 512, dict(rounded=False, star_frac=0.30)),  # full-bleed, star in safe zone
        ("apple-touch-icon.png", 180, dict(rounded=False, star_frac=0.34)),   # iOS masks corners itself
    ]
    for name, size, opts in specs:
        write_png(os.path.join(OUT_DIR, name), size, render(size, **opts))
        print(f"  wrote {name} ({size}x{size})")
    print(f"Done → {os.path.normpath(OUT_DIR)}")


if __name__ == "__main__":
    main()
