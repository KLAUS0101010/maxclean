#!/usr/bin/env python3
"""Tests for dex_api.py"""
import sys
import tempfile
import zipfile
import struct
from pathlib import Path

ROOT = Path(file).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dex_api


def fake_dex_file(version: int = 39) -> bytes:
    h = bytearray(0x70)
    ver_str = f"{version:03d}\x00".encode("ascii")
    h[:8] = b"dex\n" + ver_str
    struct.pack_into("<I", h, 0x60, 10)
    return bytes(h)


def test_update_apktool_yml():
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        yml = t / "apktool.yml"
        yml.write_text("version: 2.10.0\napkFileName: max.apk\napiLevel: '15'\n")

        apk = t / "test.apk"
        with zipfile.ZipFile(apk, "w") as z:
            z.writestr("classes.dex", fake_dex_file(39))

        ret = dex_api.main(["dex_api.py", str(apk), str(t)])
        assert ret == 0, "dex_api returned non-zero"
        updated = yml.read_text()
        assert "apiLevel: '28'" in updated, f"Expected apiLevel 28, got:\n{updated}"
        print("ok    dex_api: successfully updated apktool.yml")


if name == "main":
    test_update_apktool_yml()
    print("\nALL PASSED")
