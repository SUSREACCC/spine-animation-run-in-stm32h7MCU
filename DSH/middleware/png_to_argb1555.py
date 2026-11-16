#!/usr/bin/env python3
"""Convert a spine atlas PNG (RGBA8888) to the raw ARGB1555 format used by
raster2d on the STM32H743 target.

Output format (little endian):
    char     magic[4] = "R2DT"
    uint16   width
    uint16   height
    uint16   format   = 1 (ARGB1555)
    uint16   reserved
    uint32   dataBytes
    uint16   pixels[] row-major

Alpha is reduced to 1 bit: pixel is opaque when a >= threshold (default 8),
which is what ARGB1555 gives us and what the renderer blends with. Because the
spine atlases we use are PMA (premultiplied), a 1-bit alpha conversion loses
nothing: for a fully opaque texel premultiplied == straight.

Usage:
    python DSH/middleware/png_to_argb1555.py <in.png> <out.raw> [--threshold N] [--pma]
"""
import struct
import sys
import zlib


def read_png(path):
    data = open(path, "rb").read()

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("not a PNG file")

    pos = 8
    width = height = bitdepth = colortype = None
    idat = []
    palette = None

    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length

        if ctype == b"IHDR":
            width, height, bitdepth, colortype, comp, filt, interlace = struct.unpack(">IIBBBBB", chunk)
            if (bitdepth != 8) or (interlace != 0):
                raise SystemExit("only 8-bit non-interlaced PNGs are supported")
        elif ctype == b"PLTE":
            palette = chunk
        elif ctype == b"IDAT":
            idat.append(chunk)
        elif ctype == b"IEND":
            break

    raw = zlib.decompress(b"".join(idat))

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colortype]
    stride = width * channels
    out = bytearray(width * height * channels)
    prev = bytearray(stride)

    p = 0
    for y in range(height):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride

        if f == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif f != 0:
            raise SystemExit("bad filter type %d" % f)

        out[y * stride:(y + 1) * stride] = line
        prev = line

    return width, height, colortype, channels, palette, out


def to_argb1555(width, height, colortype, channels, palette, pixels, threshold, unpremultiply):
    out = bytearray(width * height * 2)

    for i in range(width * height):
        if colortype == 6:
            r, g, b, a = pixels[4 * i:4 * i + 4]
        elif colortype == 2:
            r, g, b = pixels[3 * i:3 * i + 3]
            a = 255
        elif colortype == 0:
            r = g = b = pixels[i]
            a = 255
        elif colortype == 3:
            idx = pixels[i]
            r, g, b = palette[3 * idx:3 * idx + 3]
            a = 255
        else:
            raise SystemExit("unsupported colour type")

        bit = 1 if a >= threshold else 0

        if bit and unpremultiply and (a < 255):
            # 图集是预乘 alpha：先还原成直通色，否则半透明处会偏暗
            r = min(255, (r * 255 + a // 2) // a)
            g = min(255, (g * 255 + a // 2) // a)
            b = min(255, (b * 255 + a // 2) // a)

        v = (bit << 15) | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
        out[2 * i] = v & 0xFF
        out[2 * i + 1] = (v >> 8) & 0xFF

    return out


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)

    src, dst = sys.argv[1], sys.argv[2]
    threshold = 128
    unpremultiply = "--pma" in sys.argv

    if "--threshold" in sys.argv:
        threshold = int(sys.argv[sys.argv.index("--threshold") + 1])

    width, height, colortype, channels, palette, pixels = read_png(src)
    body = to_argb1555(width, height, colortype, channels, palette, pixels, threshold, unpremultiply)

    header = b"R2DT" + struct.pack("<HHHHI", width, height, 1, 0, len(body))
    open(dst, "wb").write(header + body)

    opaque = sum(1 for i in range(0, len(body), 2) if (body[i + 1] & 0x80))
    print("%s -> %s  %dx%d  %d bytes  opaque=%.1f%%"
          % (src, dst, width, height, len(header) + len(body), 100.0 * opaque / (width * height)))


if __name__ == "__main__":
    main()
