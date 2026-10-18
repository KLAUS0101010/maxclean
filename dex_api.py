#!/usr/bin/env python3
"""
dex_api.py <original.apk> <folder made by apktool d>

Why this exists: apktool rebuilds all code with ONE "api level". After `apktool d -r` it guesses that
level from the main classes.dex, but one of the other dex files of the app may use newer instructions
(for example `invoke-polymorphic`, which is what VarHandle calls compile to). Then the rebuild stops with
    Cannot read field "format" because "<parameter1>" is null / Could not smali file: ...

This script reads the real dex versions out of the ORIGINAL apk and, if the level in apktool.yml is too low,
raises it to the lowest level that covers every dex file. Nothing else is changed.
(With `-r` the manifest is copied as it is, so the raised level does not touch the manifest.)
"""
import re
import sys
import zipfile
from pathlib import Path

# dex format version -> lowest smali api level that writes/accepts it (measured with apktool 2.10.0)
VERSION_TO_API = {35: None, 37: 24, 38: 26, 39: 28, 40: 30, 41: 35}


def dex_versions(apk: Path):
    out = {}
    with zipfile.ZipFile(apk) as z:
        for name in z.namelist():
            if re.fullmatch(r"classes\d*\.dex", name):
                head = z.read(name)[:8]
                m = re.fullmatch(rb"dex\n(\d{3})\x00", head)
                if m:
                    out[name] = int(m.group(1))
    return out


def needed_api(versions):
    best = None
    for v in versions.values():
        api = VERSION_TO_API.get(v, VERSION_TO_API[max(VERSION_TO_API)] if v > 41 else None)
        if api is not None and (best is None or api > best):
            best = api
    return best


MIN_LINE = re.compile(r"^(\s+minSdkVersion:\s*)(['\"]?)(\d+)(['\"]?)\s*$", re.M)


def fix_yml(text: str, api: int):
    """Returns (new_text, message)."""
    if "sdkInfo:" not in text:
        add = f"sdkInfo:\n  minSdkVersion: '{api}'\n"
        return (text if text.endswith("\n") else text + "\n") + add, f"no sdkInfo, added minSdkVersion {api}"
    m = MIN_LINE.search(text)
    if m:
        cur = int(m.group(3))
        if cur >= api:
            return text, f"minSdkVersion {cur} is already enough (needed {api}), nothing changed"
        new = MIN_LINE.sub(lambda mm: f"{mm.group(1)}{mm.group(2)}{api}{mm.group(4)}", text, count=1)
        return new, f"minSdkVersion raised {cur} -> {api}"
    new = re.sub(r"^sdkInfo:\s*\n", f"sdkInfo:\n  minSdkVersion: '{api}'\n", text, count=1, flags=re.M)
    return new, f"sdkInfo had no minSdkVersion, added {api}"


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    apk, folder = Path(argv[1]), Path(argv[2])
    yml = folder / "apktool.yml"
    if not apk.exists() or not yml.exists():
        print("error: need the original apk and an apktool folder with apktool.yml")
        return 2
    versions = dex_versions(apk)
    if not versions:
        print("error: no classes*.dex found in", apk)
        return 1
    print("dex versions in the original:", ", ".join(f"{k}={v:03d}" for k, v in sorted(versions.items())))
    api = needed_api(versions)
    if api is None:
        print("all dex files are the old plain format: apktool's default is fine, nothing changed")
        return 0
    new, msg = fix_yml(yml.read_text(encoding="utf-8"), api)
    yml.write_text(new, encoding="utf-8")
    print("apktool.yml:", msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
