#!/usr/bin/env python3
"""
dex_api.py <apk_path> <decoded_folder>

Fixes apktool's apiLevel in apktool.yml after unpacking with -r.
Apktool defaults to an older API level when resources aren't parsed,
which breaks reassembling smali containing modern bytecode instructions.
"""
import sys
import zipfile
import struct
import re
from pathlib import Path

DEFAULT_TARGET_API = 28


def get_max_dex_version(apk_path: Path) -> int:
    """Reads DEX header format versions from all classes*.dex in the APK."""
    max_ver = 35
    if not apk_path.exists():
        return max_ver

    try:
        with zipfile.ZipFile(apk_path, "r") as z:
            for name in z.namelist():
                if name.startswith("classes") and name.endswith(".dex"):
                    data = z.read(name)
                    if data[:4] == b"dex\n":
                        ver_str = data[4:7].decode("ascii", errors="ignore")
                        if ver_str.isdigit():
                            ver = int(ver_str)
                            if ver > max_ver:
                                max_ver = ver
    except Exception as e:
        print(f"Warning: could not inspect dex headers: {e}")

    return max_ver


def update_apktool_yml(yml_path: Path, api_level: int):
    if not yml_path.exists():
        print(f"Warning: {yml_path} not found.")
        return False

    content = yml_path.read_text(encoding="utf-8")

    # If apiLevel is already present, update it; otherwise add it
    if re.search(r"^apiLevel:\s*'?\d+'?", content, flags=re.MULTILINE):
        content = re.sub(
            r"^apiLevel:\s*'?\d+'?",
            f"apiLevel: '{api_level}'",
            content,
            flags=re.MULTILINE,
        )
    else:
        # Insert apiLevel right under versionInfo or at the top
        if "versionInfo:" in content:
            content = content.replace("versionInfo:\n", f"versionInfo:\n  apiLevel: '{api_level}'\n")
        else:
            content = f"apiLevel: '{api_level}'\n" + content

    yml_path.write_text(content, encoding="utf-8")
    return True


def main(argv):
    if len(argv) < 3:
        print("Usage: python3 dex_api.py <apk_path> <decoded_dir>")
        return 2

    apk_path = Path(argv[1])
    dec_dir = Path(argv[2])
    yml_path = dec_dir / "apktool.yml"

    dex_ver = get_max_dex_version(apk_path)
    
    # DEX 038/039 requires at least Android 8.0/9.0 (API 26/28)
    api_to_set = DEFAULT_TARGET_API
    if dex_ver >= 39:
        api_to_set = 28
    elif dex_ver == 38:
        api_to_set = 26

    print(f"Setting apktool apiLevel to {api_to_set} (detected max dex version: {dex_ver})")
    if update_apktool_yml(yml_path, api_to_set):
        print(f"Successfully updated {yml_path}")
    else:
        print(f"Notice: skipped updating apktool.yml")

    return 0


if name == "main":
    sys.exit(main(sys.argv))
