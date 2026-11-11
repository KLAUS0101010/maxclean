#!/usr/bin/env python3
"""
dex_api.py <apk_path> <decoded_folder>

Fixes apktool's minSdkVersion in apktool.yml after unpacking with -r.
Apktool defaults to API 15 when resources are not decoded, which causes
smali to fail on modern bytecode instructions (invoke-polymorphic, etc.).
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

    # Удаляем старый sdkInfo и apiLevel, если они есть
    content = re.sub(r"sdkInfo:\n(?:\s+.*\n)*", "", content)
    content = re.sub(r"^apiLevel:.*\n", "", content, flags=re.MULTILINE)

    # Прописываем блок sdkInfo, откуда Apktool 2.10+ считывает API для smali
    sdk_block = (
        f"\nsdkInfo:\n"
        f"  minSdkVersion: '{TARGET_API}'\n"
        f"  targetSdkVersion: '34'\n"
        f"apiLevel: '{TARGET_API}'\n"
    )

    new_content = content.strip() + "\n" + sdk_block
    yml_path.write_text(new_content, encoding="utf-8")
    print(f"Successfully configured {yml_path} with minSdkVersion: '{TARGET_API}'")
    return True


def main(argv):
    if len(argv) < 3:
        print("Usage: python3 dex_api.py <apk_path> <decoded_dir>")
        return 2

    dec_dir = Path(argv[2])
    fix_apktool_yml(dec_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
