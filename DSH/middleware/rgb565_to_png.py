#!/usr/bin/env python3
"""Convert a raw RGB565 framebuffer dump (little-endian) into a PNG.

Usage: rgb565_to_png.py <in.raw> <out.png> <width> <height>
Only the Python standard library is used (zlib + struct).
"""
import struct
import sys
import zlib


def write_png(path, width, height, rgb_rows):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rgb_rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    src, dst, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    data = open(src, "rb").read()
    if len(data) < w * h * 2:
        raise SystemExit(f"dump too small: {len(data)} < {w * h * 2}")

    rows = []
    for y in range(h):
        row = bytearray(w * 3)
        base = y * w * 2
        for x in range(w):
            px = data[base + x * 2] | (data[base + x * 2 + 1] << 8)
            r = ((px >> 11) & 0x1F) * 255 // 31
            g = ((px >> 5) & 0x3F) * 255 // 63
            b = (px & 0x1F) * 255 // 31
            o = x * 3
            row[o] = r
            row[o + 1] = g
            row[o + 2] = b
        rows.append(bytes(row))

    write_png(dst, w, h, rows)
    print(f"wrote {dst} ({w}x{h}) from {len(data)} bytes")


if __name__ == "__main__":
    main()
