#!/usr/bin/env python3
"""Convert a spine atlas PNG (RGBA8888) to the raw texture format used by
raster2d on the STM32H743 target.

Supported output formats:
    --fmt 1555   (default) ARGB1555 - 1 bit alpha, fastest path (~6.8 Mpx/s)
    --fmt 4444             ARGB4444 - 4 bit alpha, smooth edges (~3.5 Mpx/s)

File layout (little endian):
    char     magic[4] = "R2DT"
    uint16   width
    uint16   height
    uint16   format   (1 = ARGB1555, 2 = ARGB4444)
    uint16   reserved
    uint32   dataBytes
    uint16   pixels[] row-major

--pma un-premultiplies the RGB channels first (spine atlases are usually
premultiplied; the rasterizer blends with straight alpha).

Usage:
    python DSH/middleware/png_to_raw.py <in.png> <out.raw> [--fmt 1555|4444] [--pma] [--threshold N]
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


def rgba_at(i, colortype, channels, palette, pixels):
    if colortype == 6:
        return pixels[4 * i], pixels[4 * i + 1], pixels[4 * i + 2], pixels[4 * i + 3]
    if colortype == 2:
        return pixels[3 * i], pixels[3 * i + 1], pixels[3 * i + 2], 255
    if colortype == 0:
        v = pixels[i]
        return v, v, v, 255
    if colortype == 3:
        idx = pixels[i]
        return palette[3 * idx], palette[3 * idx + 1], palette[3 * idx + 2], 255
    raise SystemExit("unsupported colour type")


def to_1555(width, height, colortype, channels, palette, pixels, threshold, pma):
    out = bytearray(width * height * 2)
    opaque = 0

    for i in range(width * height):
        r, g, b, a = rgba_at(i, colortype, channels, palette, pixels)

        if a >= threshold:
            opaque += 1

            if pma and (a < 255):
                r = min(255, (r * 255 + a // 2) // a)
                g = min(255, (g * 255 + a // 2) // a)
                b = min(255, (b * 255 + a // 2) // a)

            v = 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
        else:
            v = 0

        out[2 * i] = v & 0xFF
        out[2 * i + 1] = (v >> 8) & 0xFF

    return out, opaque


def to_4444(width, height, colortype, channels, palette, pixels, pma):
    out = bytearray(width * height * 2)
    opaque = 0

    for i in range(width * height):
        r, g, b, a = rgba_at(i, colortype, channels, palette, pixels)

        a4 = (a * 15 + 127) // 255

        if a4 > 0:
            opaque += 1

            if pma and (a < 255):
                r = min(255, (r * 255 + a // 2) // a)
                g = min(255, (g * 255 + a // 2) // a)
                b = min(255, (b * 255 + a // 2) // a)

            v = (a4 << 12) | (((r * 15 + 127) // 255) << 8) | (((g * 15 + 127) // 255) << 4) | ((b * 15 + 127) // 255)
        else:
            v = 0

        out[2 * i] = v & 0xFF
        out[2 * i + 1] = (v >> 8) & 0xFF

    return out, opaque


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)

    src, dst = sys.argv[1], sys.argv[2]
    fmt = "1555"
    threshold = 128
    pma = "--pma" in sys.argv

    if "--fmt" in sys.argv:
        fmt = sys.argv[sys.argv.index("--fmt") + 1]

    if "--threshold" in sys.argv:
        threshold = int(sys.argv[sys.argv.index("--threshold") + 1])

    width, height, colortype, channels, palette, pixels = read_png(src)

    if fmt == "4444":
        body, opaque = to_4444(width, height, colortype, channels, palette, pixels, pma)
        fmt_id = 2
    elif fmt == "1555":
        body, opaque = to_1555(width, height, colortype, channels, palette, pixels, threshold, pma)
        fmt_id = 1
    else:
        raise SystemExit("unknown --fmt %s" % fmt)

    header = b"R2DT" + struct.pack("<HHHHI", width, height, fmt_id, 0, len(body))
    open(dst, "wb").write(header + body)

    print("%s -> %s  %dx%d  fmt=%s  %d bytes  opaque=%.1f%%"
          % (src, dst, width, height, fmt, len(header) + len(body),
             100.0 * opaque / (width * height)))


if __name__ == "__main__":
    main()
