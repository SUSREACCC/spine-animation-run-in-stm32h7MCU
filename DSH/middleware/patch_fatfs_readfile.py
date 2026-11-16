#!/usr/bin/env python3
"""Strengthen the FatFs self-test: descend one directory level and read a real file.

Run from the project root:  python DSH/middleware/patch_fatfs_readfile.py
"""
import io

PATH = "User/selftest.c"

FUNC = r'''
/*--------------------------------------------------------------- FATFS */
static FATFS   g_fs;
static FIL     g_fil;
static DIR     g_dir;
static FILINFO g_fno;

/* open <dir>/<name> and read the first bytes; returns 1 on success */
static uint8_t fatfs_probe_file(const char *dir, const char *name)
{
    char path[96];
    UINT br = 0u;
    uint8_t head[16];

    if (dir[0] != 0)
    {
        sprintf(path, "0:/%s/%s", dir, name);
    }
    else
    {
        sprintf(path, "0:/%s", name);
    }

    if (f_open(&g_fil, path, FA_READ) != FR_OK)
    {
        printf("  read      : open failed: %s\r\n", path);
        return 0u;
    }

    if ((f_read(&g_fil, head, sizeof(head), &br) != FR_OK) || (br == 0u))
    {
        f_close(&g_fil);
        printf("  read      : short read: %s\r\n", path);
        return 0u;
    }

    printf("  read      : %s -> %u B, %02X %02X %02X %02X ...\r\n",
           path, (unsigned)br, head[0], head[1], head[2], head[3]);

    f_close(&g_fil);
    return 1u;
}

static uint8_t test_fatfs(void)
{
    FRESULT fr;
    DWORD   fre_clust = 0;
    DWORD   tot_sect;
    DWORD   fre_sect;
    UINT    i;
    UINT    nfiles = 0;
    uint8_t listed = 0;
    uint8_t readok = 0;
    char    subdir[32];

    subdir[0] = 0;

    fr = f_mount(&g_fs, "0:", 1);
    if (fr != FR_OK)
    {
        printf("  f_mount 0:: error %u\r\n", (unsigned)fr);
        return ST_FAIL;
    }

    fr = f_getfree("0:", &fre_clust, 0);
    if (fr == FR_OK)
    {
        tot_sect = (DWORD)(g_fs.n_fatent - 2u) * g_fs.csize;
        fre_sect = fre_clust * g_fs.csize;
        printf("  volume    : FAT%d, total %lu MB, free %lu MB\r\n",
               (g_fs.fs_type == FS_FAT32) ? 32 : (int)g_fs.fs_type,
               (unsigned long)(tot_sect / 2048u), (unsigned long)(fre_sect / 2048u));
    }
    else
    {
        printf("  f_getfree : error %u\r\n", (unsigned)fr);
    }

    fr = f_opendir(&g_dir, "0:/");
    if (fr != FR_OK)
    {
        printf("  f_opendir : error %u\r\n", (unsigned)fr);
        return ST_FAIL;
    }

    for (i = 0u; i < 12u; i++)
    {
        fr = f_readdir(&g_dir, &g_fno);
        if ((fr != FR_OK) || (g_fno.fname[0] == 0))
        {
            break;
        }
        printf("   %s%s  %lu B\r\n", g_fno.fname,
               ((g_fno.fattrib & AM_DIR) != 0u) ? "/" : " ",
               (unsigned long)g_fno.fsize);
        nfiles++;
        listed = 1u;

        if (((g_fno.fattrib & AM_DIR) != 0u) && (subdir[0] == 0) &&
            (strcmp(g_fno.fname, ".") != 0) && (strcmp(g_fno.fname, "..") != 0))
        {
            strncpy(subdir, g_fno.fname, sizeof(subdir) - 1u);
            subdir[sizeof(subdir) - 1u] = 0;
        }

        if ((readok == 0u) && ((g_fno.fattrib & (AM_DIR | AM_SYS | AM_HID)) == 0u) &&
            (g_fno.fsize > 16u))
        {
            readok = fatfs_probe_file("", g_fno.fname);
        }
    }
    f_closedir(&g_dir);

    /* nothing readable at root: descend one level into the first directory */
    if ((readok == 0u) && (subdir[0] != 0))
    {
        char path[96];

        sprintf(path, "0:/%s", subdir);
        if (f_opendir(&g_dir, path) == FR_OK)
        {
            for (i = 0u; (i < 12u) && (readok == 0u); i++)
            {
                if ((f_readdir(&g_dir, &g_fno) != FR_OK) || (g_fno.fname[0] == 0))
                {
                    break;
                }
                if (((g_fno.fattrib & (AM_DIR | AM_SYS | AM_HID)) == 0u) && (g_fno.fsize > 16u))
                {
                    readok = fatfs_probe_file(subdir, g_fno.fname);
                }
            }
            f_closedir(&g_dir);
        }
    }

    printf("  entries   : %u listed, file read %s\r\n",
           (unsigned)nfiles, (readok != 0u) ? "OK" : "n/a");

    return (listed != 0u) ? ST_OK : ST_FAIL;
}
'''

src = io.open(PATH, encoding="utf-8").read()
start = src.index("/*--------------------------------------------------------------- FATFS */")
end = src.index("/*--------------------------------------------------------------- screen */")
src = src[:start] + FUNC.strip() + "\n\n" + src[end:]
io.open(PATH, "w", encoding="utf-8", newline="").write(src)
print("test_fatfs() replaced with directory-descending version")
