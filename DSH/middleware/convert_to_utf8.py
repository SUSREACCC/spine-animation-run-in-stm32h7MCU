#!/usr/bin/env python3
"""Convert all GBK-encoded project sources to UTF-8 (no BOM).

- Scans Drivers/, Middlewares/, User/, Projects/ for .c/.h/.s/.txt/.uvprojx/...
- Files that already decode as UTF-8 are left untouched.
- Files that decode as GBK (cp936) are backed up to save/<timestamp>/<path>
  and rewritten as UTF-8 without BOM.
- UTF-8 BOM is deliberately NOT written: ARM Compiler 5's armasm rejects a BOM
  ("A1167F: Invalid line start").

Usage: python DSH/middleware/convert_to_utf8.py [--dry-run]
"""
import datetime
import os
import shutil
import sys

ROOTS = ["Drivers", "Middlewares", "User", "Projects"]
EXTS = {".c", ".h", ".s", ".S", ".txt", ".md", ".uvprojx", ".uvoptx", ".ini", ".json"}


def iter_sources():
    for root in ROOTS:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if os.path.splitext(fn)[1] in EXTS:
                    yield os.path.join(dirpath, fn)


def main():
    dry = "--dry-run" in sys.argv
    ts = datetime.datetime.now().strftime("%y-%m-%d-%H-%M")
    backup_root = os.path.join("save", ts)

    converted, skipped, failed = [], 0, []
    mb = 0

    for path in iter_sources():
        raw = open(path, "rb").read()
        try:
            raw.decode("utf-8")
            skipped += 1
            continue
        except UnicodeDecodeError:
            pass

        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError as exc:
            failed.append((path, str(exc)))
            continue

        converted.append((path, len(text)))
        mb += os.path.getsize(path)

        if dry:
            continue

        dst = os.path.join(backup_root, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(path, dst)

        with open(path, "wb") as f:
            f.write(text.encode("utf-8"))

    print(f"{'[dry-run] ' if dry else ''}converted: {len(converted)}  already-utf8: {skipped}  failed: {len(failed)}")
    for p, n in converted:
        print(f"   {p}  ({n} chars)")
    for p, e in failed:
        print(f"   FAILED {p}: {e}")
    if not dry and converted:
        print(f"\nbackup of originals -> {backup_root}")


if __name__ == "__main__":
    main()
