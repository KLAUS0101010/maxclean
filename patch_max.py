#!/usr/bin/env python3
"""
MAX Clean patcher.

Usage: python3 patch_max.py <folder decoded by apktool>

What it does to the *official* MAX app (every step is reported, nothing is silent):
  1. Tracker host names inside the code are replaced by a name that does not exist,
     so the app cannot send anything there.
  2. MyTracker's "send an event" methods are turned into empty methods.
  3. The Google advertising id function returns the "no id" value (all zeros).
  4. The advertising-id permission is removed from the manifest.
  5. The app label becomes "MAX Clean", so you can see which build you installed.
Third-party trackers only. Nothing here can hide you from MAX's own servers.
"""
import re
import sys
from pathlib import Path

DEAD_HOST = "blocked.invalid"

# found in MAX's own code (tracker-api.vk-analytics.ru) + common analytics endpoints
HOSTS = [
    "tracker-api.vk-analytics.ru",
    "tracker-api.my.com",
    "app-measurement.com",
    "firebase-settings.crashlytics.com",
    "reports.crashlytics.com",
    "api.appsflyer.com",
    "app.adjust.com",
    "appmetrica.yandex.ru",
    "mc.yandex.ru",
    "sentry.io",
]

# MyTracker methods that only send data. All return void.
# initTracker / getTrackerParams / getTrackerConfig are left alone: MAX calls them
# afterwards and an un-started tracker would crash the app.
TRACKER_VOID_METHODS = ["flush", "trackLaunchManually", "trackLoginEvent", "trackRegistrationEvent"]

ZERO_AD_ID = "00000000-0000-0000-0000-000000000000"
INFO_CLS = "Lcom/google/android/gms/ads/identifier/AdvertisingIdClient$Info;"


def smali_files(root: Path):
    return [p for d in root.glob("smali*") if d.is_dir() for p in d.rglob("*.smali")]


def replace_hosts(root: Path):
    changed, total = 0, 0
    for f in smali_files(root):
        text = f.read_text(encoding="utf-8", errors="surrogateescape")
        new = text
        for h in HOSTS:
            if h in new:
                total += new.count(h)
                new = new.replace(h, DEAD_HOST)
        if new != text:
            f.write_text(new, encoding="utf-8", errors="surrogateescape")
            changed += 1
    return changed, total


def empty_void_methods(text: str, names):
    """Replace the body of every `.method ... name(...)V` with `return-void`."""
    count = 0
    for name in names:
        pat = re.compile(
            r"(\.method [^\n]*\b" + re.escape(name) + r"\([^\n]*\)V\n)(.*?)(\.end method)",
            re.DOTALL,
        )
        text, n = pat.subn(lambda m: m.group(1) + "    .locals 0\n    return-void\n" + m.group(3), text)
        count += n
    return text, count


def patch_mytracker(root: Path):
    done = 0
    for f in smali_files(root):
        if f.as_posix().endswith("com/my/tracker/MyTracker.smali"):
            text = f.read_text(encoding="utf-8", errors="surrogateescape")
            new, n = empty_void_methods(text, TRACKER_VOID_METHODS)
            f.write_text(new, encoding="utf-8", errors="surrogateescape")
            done += n
    return done


def patch_ad_id(root: Path):
    body = (
        "    .locals 3\n"
        f"    new-instance v0, {INFO_CLS}\n"
        f'    const-string v1, "{ZERO_AD_ID}"\n'
        "    const/4 v2, 0x1\n"
        f"    invoke-direct {{v0, v1, v2}}, {INFO_CLS}-><init>(Ljava/lang/String;Z)V\n"
        "    return-object v0\n"
    )
    pat = re.compile(
        r"(\.method [^\n]*\bgetAdvertisingIdInfo\(Landroid/content/Context;\)" + re.escape(INFO_CLS) + r"\n)(.*?)(\.end method)",
        re.DOTALL,
    )
    done = 0
    for f in smali_files(root):
        if f.as_posix().endswith("ads/identifier/AdvertisingIdClient.smali"):
            text = f.read_text(encoding="utf-8", errors="surrogateescape")
            new, n = pat.subn(lambda m: m.group(1) + body + m.group(3), text)
            if n:
                f.write_text(new, encoding="utf-8", errors="surrogateescape")
                done += n
    return done


def patch_manifest(root: Path):
    mf = root / "AndroidManifest.xml"
    text = mf.read_text(encoding="utf-8")
    new, n = re.subn(
        r'[ \t]*<uses-permission[^>]*com\.google\.android\.gms\.permission\.AD_ID[^>]*/>\n?', "", text)
    mf.write_text(new, encoding="utf-8")
    return n


def patch_label(root: Path):
    f = root / "res" / "values" / "strings.xml"
    if not f.exists():
        return 0
    text = f.read_text(encoding="utf-8")
    new, n = re.subn(r'(<string name="app_name">)[^<]*(</string>)', r"\1MAX Clean\2", text)
    if n:
        f.write_text(new, encoding="utf-8")
    return n


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    if not (root / "AndroidManifest.xml").exists():
        print("error: not an apktool output folder:", root)
        return 2

    files, hosts = replace_hosts(root)
    print(f"[1] tracker hosts replaced: {hosts} occurrence(s) in {files} file(s)")
    t = patch_mytracker(root)
    print(f"[2] MyTracker send-methods emptied: {t}")
    a = patch_ad_id(root)
    print(f"[3] advertising-id function replaced: {a}")
    m = patch_manifest(root)
    print(f"[4] AD_ID permission removed: {m}")
    l = patch_label(root)
    print(f"[5] app label changed: {l}")

    if hosts == 0 and t == 0:
        print("error: neither tracker hosts nor MyTracker found; this does not look like MAX. Nothing patched.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
