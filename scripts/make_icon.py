"""Generate the pixel-art broom icon (assets/icon.ico + package window PNG).

Pure stdlib. The broom is drawn once on a 16x16 grid and nearest-neighbor
scaled, keeping the pixel-art look at every size.

Run:  python scripts/make_icon.py
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PALETTE = {
    "H": (201, 168, 92, 255),   # handle wood (gold)
    "D": (138, 109, 59, 255),   # handle shadow
    "S": (199, 204, 214, 255),  # ferrule band (silver)
    "R": (176, 58, 48, 255),    # stitching (red)
    "B": (216, 163, 67, 255),   # straw (amber)
    "b": (166, 124, 46, 255),   # straw shadow
    ".": (0, 0, 0, 0),          # transparent
}

GRID = [
    ".......HD.......",
    ".......HD.......",
    ".......HD.......",
    ".......HD.......",
    ".......HD.......",
    ".......HD.......",
    "......SSSS......",
    "......BBBB......",
    ".....BBBBBb.....",
    "....BBBBBBBb....",
    "....RRRRRRRR....",
    "...BBBBBBBBBb...",
    "...RRRRRRRRRR...",
    "..BBbBBBBbBBBb..",
    ".BBbBBbBBbBBbBb.",
    ".b.b.b.b.b.b.b..",
]


def pixels(scale: int) -> list[list[tuple[int, int, int, int]]]:
    rows = []
    for line in GRID:
        row = [PALETTE[ch] for ch in line for _ in range(scale)]
        rows.extend([row] * scale)
    return rows


def png_bytes(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    height, width = len(rows), len(rows[0])

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body)))

    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def bmp_entry(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    height, width = len(rows), len(rows[0])
    header = struct.pack("<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0,
                         width * height * 4, 0, 0, 0, 0)
    xor = b"".join(
        bytes(v for r, g, b, a in row for v in (b, g, r, a))
        for row in reversed(rows)
    )
    mask_row = b"\x00" * (((width + 31) // 32) * 4)
    return header + xor + mask_row * height


def write_ico(path: Path) -> None:
    images = []
    for size, scale in ((16, 1), (32, 2), (48, 3)):
        images.append((size, bmp_entry(pixels(scale))))
    images.append((256, png_bytes(pixels(16))))
    header = struct.pack("<HHH", 0, 1, len(images))
    entries, bodies = b"", b""
    offset = len(header) + 16 * len(images)
    for size, body in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32,
                               len(body), offset)
        bodies += body
        offset += len(body)
    path.write_bytes(header + entries + bodies)


def main() -> None:
    ico = ROOT / "assets" / "icon.ico"
    ico.parent.mkdir(exist_ok=True)
    write_ico(ico)
    window_png = ROOT / "src" / "llm_export_cleaner" / "assets" / "icon-64.png"
    window_png.parent.mkdir(exist_ok=True)
    window_png.write_bytes(png_bytes(pixels(4)))
    preview = ROOT / "assets" / "icon-256.png"
    preview.write_bytes(png_bytes(pixels(16)))
    print(f"wrote {ico}, {window_png}, {preview}")


if __name__ == "__main__":
    sys.exit(main())
