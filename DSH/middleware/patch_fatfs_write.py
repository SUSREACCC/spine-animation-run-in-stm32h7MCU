#!/usr/bin/env python3
"""FatFs self-test refinements:
  1) skip "System Volume Information" when picking a directory to descend into
  2) add a self-cleaning write/read/delete round-trip (512 B pattern)

Run from the project root:  python DSH/middleware/patch_fatfs_write.py
"""
import io

PATH = "User/selftest.c"

# ---- 1) probe function gains a write round-trip -------------------------
PROBE = r'''
/* small self-cleaning write test: create -> read back -> verify -> delete */
static uint8_t fatfs_write_roundtrip(void)
{
    static const char *NAME = "0:/H7TEST.TXT";
    uint8_t  wr[512];
    uint8_t  rd[512];
    UINT     bw = 0u;
    UINT     br = 0u;
    uint16_t i;
    uint8_t  ok = 0u;

    for (i = 0u; i < sizeof(wr); i++)
    {
        wr[i] = (uint8_t)(i * 31u + 7u);
    }

    if (f_open(&g_fil, NAME, FA_CREATE_ALWAYS | FA_WRITE) != FR_OK)
    {
        printf("  write     : open failed (card write protected?)\r\n");
        return 0u;
    }

    if ((f_write(&g_fil, wr, sizeof(wr), &bw) == FR_OK) && (bw == sizeof(wr)) &&
        (f_sync(&g_fil) == FR_OK))
    {
        ok = 1u;
    }
    f_close(&g_fil);

    if (ok != 0u)
    {
        ok = 0u;
        if (f_open(&g_fil, NAME, FA_READ) == FR_OK)
        {
            if ((f_read(&g_fil, rd, sizeof(rd), &br) == FR_OK) && (br == sizeof(rd)) &&
                (memcmp(wr, rd, sizeof(wr)) == 0))
            {
                ok = 1u;
            }
            f_close(&g_fil);
        }
    }

    printf("  write     : 512 B -> readback %s, delete %s\r\n",
           (ok != 0u) ? "match" : "MISMATCH",
           (f_unlink(NAME) == FR_OK) ? "ok" : "failed");

    return ok;
}
'''

src = io.open(PATH, encoding="utf-8").read()

if "fatfs_write_roundtrip" not in src:
    src = src.replace("static uint8_t test_fatfs(void)", PROBE.strip() + "\n\nstatic uint8_t test_fatfs(void)", 1)

# ---- 2) skip System Volume Information when picking the sub-directory ----
src = src.replace(
    '        if (((g_fno.fattrib & AM_DIR) != 0u) && (subdir[0] == 0) &&\n'
    '            (strcmp(g_fno.fname, ".") != 0) && (strcmp(g_fno.fname, "..") != 0))',
    '        if (((g_fno.fattrib & AM_DIR) != 0u) && (subdir[0] == 0) &&\n'
    '            (strcmp(g_fno.fname, ".") != 0) && (strcmp(g_fno.fname, "..") != 0) &&\n'
    '            (strncmp(g_fno.fname, "System", 6) != 0))', 1)

# ---- 3) run the write round-trip before the summary print ----------------
old = '    printf("  entries   : %u listed, file read %s\\r\\n",\n           (unsigned)nfiles, (readok != 0u) ? "OK" : "n/a");\n\n    return (listed != 0u) ? ST_OK : ST_FAIL;'
new = ('    printf("  entries   : %u listed, file read %s\\r\\n",\n'
       '           (unsigned)nfiles, (readok != 0u) ? "OK" : "n/a");\n\n'
       '    (void)fatfs_write_roundtrip();\n\n'
       '    return (listed != 0u) ? ST_OK : ST_FAIL;')
if "fatfs_write_roundtrip();" not in src:
    src = src.replace(old, new, 1)

io.open(PATH, "w", encoding="utf-8", newline="").write(src)
print("fatfs write round-trip wired in; system dir skipped")
