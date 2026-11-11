#!/usr/bin/env python3
"""
dex_api.py <apk_path> <decoded_folder>
Fixes apktool's minSdkVersion in apktool.yml so that modern bytecode instructions compile cleanly.
"""
import sys
import re
from pathlib import Path

TARGET_API = "30"


def fix_apktool_yml(dec_dir: Path):
    yml_path = dec_dir / "apktool.yml"
    if not yml_path.exists():
        print(f"Warning: {yml_path} not found.")
        return False

    content = yml_path.read_text(encoding="utf-8")
    content = re.sub(r"sdkInfo:\n(?:\s+.*\n)*", "", content)
    content = re.sub(r"^apiLevel:.*\n", "", content, flags=re.MULTILINE)

    sdk_block = (
        f"\nsdkInfo:\n"
        f"  minSdkVersion: '{TARGET_API}'\n"
        f"  targetSdkVersion: '34'\n"
        f"apiLevel: '{TARGET_API}'\n"
    )

    new_content = content.strip() + "\n" + sdk_block
    yml_path.write_text(new_content, encoding="utf-8")
    print(f"Configured {yml_path} with API level {TARGET_API}")
    return True


def main(argv):
    if len(argv) < 3:
        print("Usage: python3 dex_api.py <apk_path> <decoded_dir>")
        return 2
    dec_dir = Path(argv[2])
    fix_apktool_yml(dec_dir)
    return 0


if name == "main":
    sys.exit(main(sys.argv))
