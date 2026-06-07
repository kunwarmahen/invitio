#!/usr/bin/env python3
"""Generate invitio's PWA icons with zero dependencies (stdlib zlib only).

Draws a diagonal violet→pink gradient (the brand `.dot` gradient) with a white
open envelope: an invitation card rising out of the pocket, carrying the brand
"✦" sparkle. Supersampled for smooth edges, written as RGBA PNGs to
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

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "icons")

# Artwork in normalised [0,1] space (centred on 0.5).
CARD = [(0.30, 0.14), (0.70, 0.14), (0.70, 0.52), (0.30, 0.52)]
FRONT = [(0.15, 0.46), (0.85, 0.46), (0.85, 0.82), (0.15, 0.82)]
SPARK_C = (0.50, 0.31)   # sparkle centre on the card
SPARK_R = 0.11
SPARK_P = 0.55           # |x|^p + |y|^p <= 1 → concave 4-point star
MOUTH_W = 0.02           # half-width of the open-envelope "V"


def _lerp(a, b, t):
    return int(round(a + (b - a) * t))


def _grad(t):
    return (_lerp(C0[0], C1[0], t), _lerp(C0[1], C1[1], t), _lerp(C0[2], C1[2], t))


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _in_poly(px, py, pts):
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]; xj, yj = pts[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _art(au, av, gt):
    """Override colour for art coords (au, av); gt = screen gradient param. None = bg."""
    on_card = _in_poly(au, av, CARD)
    on_front = _in_poly(au, av, FRONT)
    if on_card and not on_front:
        nx = abs((au - SPARK_C[0]) / SPARK_R)
        ny = abs((av - SPARK_C[1]) / SPARK_R)
        if nx ** SPARK_P + ny ** SPARK_P <= 1.0:
            return _grad(gt)
        return WHITE
    if on_front:
        if _seg_dist(au, av, 0.15, 0.46, 0.50, 0.60) < MOUTH_W: return _grad(gt)
        if _seg_dist(au, av, 0.85, 0.46, 0.50, 0.60) < MOUTH_W: return _grad(gt)
        return WHITE
    return None


def render(size, *, rounded, scale, ss=3):
    """Return PNG-ready scanline bytes (filter 0 + RGBA). `scale` shrinks the
    artwork toward centre (use <1 for maskable so it sits in the safe zone)."""
    m = size * ss
    corner = m * 0.22 if rounded else 0.0
    raw = bytearray()
    for y in range(size):
        rows = [[0, 0, 0, 0] for _ in range(size)]
        for sy in range(ss):
            yy = y * ss + sy
            for x in range(size):
                acc = rows[x]
                for sx in range(ss):
                    xx = x * ss + sx
                    alpha = 255
                    if corner > 0:                   # rounded-rect corner cutout
                        dx = corner - xx if xx < corner else (xx - (m - 1 - corner) if xx > m - 1 - corner else 0)
                        dy = corner - yy if yy < corner else (yy - (m - 1 - corner) if yy > m - 1 - corner else 0)
                        if dx > 0 and dy > 0 and dx * dx + dy * dy > corner * corner:
                            alpha = 0
                    u, v = xx / (m - 1), yy / (m - 1)
                    gt = (u + v) / 2.0               # diagonal gradient
                    r, g, b = _grad(gt)
                    au, av = 0.5 + (u - 0.5) / scale, 0.5 + (v - 0.5) / scale
                    ov = _art(au, av, gt)
                    if ov is not None:
                        r, g, b = ov
                    acc[0] += r; acc[1] += g; acc[2] += b; acc[3] += alpha
        raw.append(0)                                # PNG filter type: none
        n = ss * ss
        for x in range(size):
            c = rows[x]
            raw += bytes((c[0] // n, c[1] // n, c[2] // n, c[3] // n))
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
        ("icon-192.png", 192, dict(rounded=True, scale=1.0)),
        ("icon-512.png", 512, dict(rounded=True, scale=1.0)),
        ("icon-maskable-512.png", 512, dict(rounded=False, scale=0.78)),  # full-bleed, art in safe zone
        ("apple-touch-icon.png", 180, dict(rounded=False, scale=0.96)),   # iOS masks corners itself
    ]
    for name, size, opts in specs:
        write_png(os.path.join(OUT_DIR, name), size, render(size, **opts))
        print(f"  wrote {name} ({size}x{size})")
    print(f"Done → {os.path.normpath(OUT_DIR)}")


if __name__ == "__main__":
    main()
