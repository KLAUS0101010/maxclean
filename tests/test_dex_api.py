import sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import dex_api

fails = 0
def check(c, m):
    global fails
    print(("ok   " if c else "FAIL ") + m)
    if not c: fails += 1

def make_apk(path, versions):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("AndroidManifest.xml", b"x")
        for name, v in versions.items():
            z.writestr(name, b"dex\n%03d\x00" % v + b"\x00" * 16)
        z.writestr("classes.dexx", b"dex\n041\x00")        # not a dex entry: must be ignored

with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    # the situation from the real MAX build: old main dex, newer second dex
    make_apk(d / "a.apk", {"classes.dex": 35, "classes2.dex": 38})
    check(dex_api.dex_versions(d / "a.apk") == {"classes.dex": 35, "classes2.dex": 38}, "reads versions, ignores look-alikes")
    check(dex_api.needed_api({"a": 35, "b": 38}) == 26, "035 + 038 -> api 26")
    check(dex_api.needed_api({"a": 35}) is None, "only 035 -> nothing needed")
    check(dex_api.needed_api({"a": 35, "b": 39, "c": 38}) == 28, "highest wins (039 -> 28)")
    check(dex_api.needed_api({"a": 40}) == 30 and dex_api.needed_api({"a": 41}) == 35, "040 -> 30, 041 -> 35")

    # apktool.yml variants
    low = "version: 2.10.0\nsdkInfo:\n  minSdkVersion: 23\npackageInfo:\n  forcedPackageId: null\n"
    new, msg = dex_api.fix_yml(low, 26)
    check("minSdkVersion: 26" in new and "forcedPackageId: null" in new and "23" not in new, "low level raised, rest kept")
    quoted = "sdkInfo:\n  minSdkVersion: '21'\n  targetSdkVersion: '34'\n"
    new, _ = dex_api.fix_yml(quoted, 26)
    check("minSdkVersion: '26'" in new and "targetSdkVersion: '34'" in new, "quoted style kept, target untouched")
    high = "sdkInfo:\n  minSdkVersion: '30'\n"
    new, msg = dex_api.fix_yml(high, 26)
    check(new == high and "nothing changed" in msg, "already high enough -> untouched")
    new, _ = dex_api.fix_yml("version: 2.10.0\nfoo: 1\n", 26)
    check(new.endswith("sdkInfo:\n  minSdkVersion: '26'\n") and "foo: 1" in new, "missing sdkInfo -> added")
    new, _ = dex_api.fix_yml("sdkInfo:\n  targetSdkVersion: '34'\nx: 1\n", 26)
    check("minSdkVersion: '26'" in new and "targetSdkVersion: '34'" in new, "sdkInfo without min -> min added")
    once, _ = dex_api.fix_yml(low, 26)
    twice, _ = dex_api.fix_yml(once, 26)
    check(once == twice, "second run changes nothing")

    # whole run
    (d / "dec").mkdir()
    (d / "dec" / "apktool.yml").write_text(low)
    check(dex_api.main(["x", str(d / "a.apk"), str(d / "dec")]) == 0, "main exits 0")
    check("minSdkVersion: 26" in (d / "dec" / "apktool.yml").read_text(), "main wrote the fix")
    make_apk(d / "old.apk", {"classes.dex": 35})
    (d / "dec2").mkdir(); (d / "dec2" / "apktool.yml").write_text(low)
    dex_api.main(["x", str(d / "old.apk"), str(d / "dec2")])
    check((d / "dec2" / "apktool.yml").read_text() == low, "old-format only -> file untouched")
    check(dex_api.main(["x", str(d / "nope.apk"), str(d / "dec")]) == 2, "missing apk -> exit 2")

print("ALL PASSED" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
