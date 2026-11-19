#!/usr/bin/env python3
"""Generate a compact 5x7 bitmap font as C code, self-verified.

The board font (asc2_1608) read back transposed/garbled through our overlay
path, so the overlay now ships its own font: 5 columns x 7 rows, one byte per
column (bit0 = top row), digits/uppercase/symbols only.

Each glyph is authored as 7 text rows here, then packed.  The script prints a
sample render so the table can be eyeballed before being written into C.

Run:  python DSH/middleware/gen_font.py > User/spine_font.h
"""
import sys

# 7 rows x 5 cols, '#' = pixel
GLYPHS = {
    ' ': ["     ", "     ", "     ", "     ", "     ", "     ", "     "],
    '0': [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    '1': ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    '2': [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    '3': ["#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "],
    '4': ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    '5': ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    '6': ["  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "],
    '7': ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    '8': [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    '9': [" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "],
    'A': [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    'B': ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    'C': [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    'D': ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    'E': ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    'F': ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    'G': [" ### ", "#   #", "#    ", "#  ##", "#   #", "#   #", " ####"],
    'H': ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    'I': [" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    'J': ["  ###", "   # ", "   # ", "   # ", "   # ", "#  # ", " ##  "],
    'K': ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    'L': ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    'M': ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    'N': ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    'O': [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    'P': ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    'Q': [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    'R': ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    'S': [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    'T': ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    'U': ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    'V': ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    'W': ["#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"],
    'X': ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    'Y': ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    'Z': ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    '.': ["     ", "     ", "     ", "     ", "     ", "  ## ", "  ## "],
    ',': ["     ", "     ", "     ", "     ", "  ## ", "  #  ", " #   "],
    ':': ["     ", "  ## ", "  ## ", "     ", "  ## ", "  ## ", "     "],
    '/': ["    #", "    #", "   # ", "  #  ", " #   ", "#    ", "#    "],
    '-': ["     ", "     ", "     ", "#####", "     ", "     ", "     "],
    '+': ["     ", "  #  ", "  #  ", "#####", "  #  ", "  #  ", "     "],
    '%': ["##  #", "##  #", "   # ", "  #  ", " #   ", "#  ##", "#  ##"],
    '(': ["   # ", "  #  ", " #   ", " #   ", " #   ", "  #  ", "   # "],
    ')': [" #   ", "  #  ", "   # ", "   # ", "   # ", "  #  ", " #   "],
    '[': [" ### ", " #   ", " #   ", " #   ", " #   ", " #   ", " ### "],
    ']': [" ### ", "   # ", "   # ", "   # ", "   # ", "   # ", " ### "],
    '<': ["   # ", "  #  ", " #   ", "#    ", " #   ", "  #  ", "   # "],
    '>': [" #   ", "  #  ", "   # ", "    #", "   # ", "  #  ", " #   "],
    '=': ["     ", "     ", "#####", "     ", "#####", "     ", "     "],
    '*': ["     ", "# # #", " ### ", "#####", " ### ", "# # #", "     "],
    '_': ["     ", "     ", "     ", "     ", "     ", "     ", "#####"],
    '!': ["  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "     ", "  #  "],
    '?': [" ### ", "#   #", "    #", "   # ", "  #  ", "     ", "  #  "],
}

FIRST = 32
LAST = 127


def glyph_for(ch):
    """Return the 7x5 rows for ch (fallback: space)."""
    return GLYPHS.get(ch, GLYPHS[' '])


def pack(ch):
    """5 bytes; byte i = column i, bit0 = top row."""
    rows = glyph_for(ch)
    out = []
    for col in range(5):
        b = 0
        for row in range(7):
            if rows[row][col] == '#':
                b |= (1 << row)
        out.append(b)
    return out


def render(text, scale=1):
    lines = [[] for _ in range(7 * scale)]
    for ch in text:
        rows = glyph_for(ch)
        for r in range(7):
            line = ""
            for c in range(5):
                line += "#" if rows[r][c] == '#' else (("." * 1) if scale == 1 else "." * scale)
            lines[r].extend(list(line + "."))
    return "\n".join("".join(l) for l in lines)


def main():
    table = []
    for code in range(FIRST, LAST):
        ch = chr(code)
        cols = pack(ch)
        table.append((ch, cols))

    if "--check" in sys.argv:
        print(render("6/6 STRESS 8 INST"))
        print()
        print(render("HALF 32.3FPS 2INST"))
        return

    out = []
    out.append("/**")
    out.append(" * spine_font.h - 5x7 bitmap font for the overlay API")
    out.append(" *")
    out.append(" * Generated by DSH/middleware/gen_font.py (do not edit by hand).")
    out.append(" * 5 bytes per glyph, column-major, bit0 = top row.")
    out.append(" * Covers ASCII %d..%d; unknown characters render as space." % (FIRST, LAST - 1))
    out.append(" */")
    out.append("")
    out.append("#ifndef __SPINE_FONT_H")
    out.append("#define __SPINE_FONT_H")
    out.append("")
    out.append("#include <stdint.h>")
    out.append("")
    out.append("#define SPINE_FONT_FIRST   (%d)" % FIRST)
    out.append("#define SPINE_FONT_LAST    (%d)" % (LAST - 1))
    out.append("#define SPINE_FONT_W       5")
    out.append("#define SPINE_FONT_H       7")
    out.append("")
    out.append("static const uint8_t g_spine_font[%d][5] = {" % len(table))

    for ch, cols in table:
        disp = ch if 32 <= ord(ch) < 127 else '?'
        label = "  /* %s */" % (("\\ '%s'" % disp) if disp == ' ' else "'%s'" % disp)
        out.append("    { 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X },%s"
                   % (cols[0], cols[1], cols[2], cols[3], cols[4], label))

    out.append("};")
    out.append("")
    out.append("#endif /* __SPINE_FONT_H */")
    print("\n".join(out))


if __name__ == "__main__":
    main()
