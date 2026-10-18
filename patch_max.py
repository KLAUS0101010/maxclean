#!/usr/bin/env python3
"""
MAX Clean patcher.

Usage: python3 patch_max.py <folder decoded by apktool>

What it does to the *official* MAX app (every step is reported, nothing is silent):
  1. Tracker host names inside the code are replaced by 0.0.0.0 (no DNS lookup happens,
     the connection is refused at once), so nothing can be sent there.
  2. Nothing is deleted. Tracker classes stay, and every method keeps existing and keeps
     being callable. "Send" methods become stubs that return at once without doing anything:
       - MyTracker: flush / trackLaunchManually / trackLoginEvent / trackRegistrationEvent
       - OK.ru calls analytics: CallAnalyticsSender.send / forceSendScheduledEvents
       - AppMetrica, Yandex Metrica, Firebase Analytics: every public void method (only if the app has them)
     initTracker / getTrackerParams / getTrackerConfig / getInstanceId are NOT touched: MAX calls
     MyTracker.getTrackerParams().setCustomUserId(...) at login, and an un-started tracker would crash there.
     With the host dead the real tracker has nowhere to send, so it is safe to leave it running.
  3. The Google advertising id function returns the "no id" value (all zeros), not null.
  4. The advertising-id permission is removed from the manifest.
  5. The app label becomes "MAX Clean", so you can see which build you installed.
Third-party trackers only. Nothing here can hide you from MAX's own servers.
"""
import re
import sys
from pathlib import Path

DEAD_HOST = "0.0.0.0"

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

# Methods that only send data and return void. They are kept (still callable) but do nothing.
# (path ending of the .smali file, [method names])
VOID_STUBS = [
    ("com/my/tracker/MyTracker.smali",
     ["flush", "trackLaunchManually", "trackLoginEvent", "trackRegistrationEvent"]),
    ("ru/ok/android/externcalls/analytics/CallAnalyticsSender.smali",
     ["send", "forceSendScheduledEvents"]),
]

# Third-party analytics classes where every public void method is only "report something".
# Constructors and static initialisers are never touched. Skipped silently if the app does not have them.
ALL_VOID_CLASSES = [
    "io/appmetrica/analytics/AppMetrica.smali",
    "com/yandex/metrica/YandexMetrica.smali",
    "com/google/firebase/analytics/FirebaseAnalytics.smali",
]

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


STUB_BODY = "    .locals 0\n    return-void\n"


def _has_code(header: str) -> bool:
    return " abstract " not in header and " native " not in header


def empty_void_methods(text: str, names):
    """Replace the body of every `.method ... name(...)V` with `return-void` (abstract/native are left alone)."""
    count = 0
    for name in names:
        pat = re.compile(
            r"(\.method [^\n]*\b" + re.escape(name) + r"\([^\n]*\)V\n)(.*?)(\.end method)",
            re.DOTALL,
        )

        def sub(m):
            nonlocal count
            if not _has_code(m.group(1)):
                return m.group(0)
            count += 1
            return m.group(1) + STUB_BODY + m.group(3)

        text = pat.sub(sub, text)
    return text, count


def empty_all_public_void(text: str):
    """Every `.method public ... name(...)V` except <init>/<clinit> becomes `return-void`."""
    count = 0
    pat = re.compile(r"(\.method public [^\n]*\b(?!<init>|<clinit>)\w+\([^\n]*\)V\n)(.*?)(\.end method)", re.DOTALL)

    def sub(m):
        nonlocal count
        if "<init>" in m.group(1) or "<clinit>" in m.group(1) or not _has_code(m.group(1)):
            return m.group(0)
        count += 1
        return m.group(1) + STUB_BODY + m.group(3)

    return pat.sub(sub, text), count


def patch_stubs(root: Path):
    report = {}
    for f in smali_files(root):
        rel = f.as_posix()
        for suffix, names in VOID_STUBS:
            if rel.endswith(suffix):
                text = f.read_text(encoding="utf-8", errors="surrogateescape")
                new, n = empty_void_methods(text, names)
                f.write_text(new, encoding="utf-8", errors="surrogateescape")
                report[suffix] = report.get(suffix, 0) + n
        for suffix in ALL_VOID_CLASSES:
            if rel.endswith(suffix):
                text = f.read_text(encoding="utf-8", errors="surrogateescape")
                new, n = empty_all_public_void(text)
                f.write_text(new, encoding="utf-8", errors="surrogateescape")
                report[suffix] = report.get(suffix, 0) + n
    return report


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


MODES = ("none", "hosts", "code", "all")
MODE_HELP = """modes (3rd argument, default "all"):
  none   change nothing (control build: only repack + re-sign)
  hosts  only replace tracker host names with 0.0.0.0
  code   hosts + method stubs + advertising id        (works on a `apktool d -r` folder)
  all    code + manifest permission + app label       (needs a fully decoded folder)"""


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__)
        print(MODE_HELP)
        return 2
    mode = argv[2] if len(argv) == 3 else "all"
    if mode not in MODES:
        print("unknown mode:", mode)
        print(MODE_HELP)
        return 2
    root = Path(argv[1])
    if not any(root.glob("smali*")):
        print("error: no smali folders in", root)
        return 2
    print(f"mode: {mode}")
    if mode == "none":
        print("nothing changed (control build)")
        return 0

    files, hosts = replace_hosts(root)
    print(f"[1] tracker hosts replaced: {hosts} occurrence(s) in {files} file(s)")
    t = a = m = l = 0
    if mode in ("code", "all"):
        stubs = patch_stubs(root)
        t = sum(stubs.values())
        print(f"[2] send-methods stubbed (kept callable, do nothing): {t}")
        for k, v in sorted(stubs.items()):
            print(f"      {k}: {v}")
        a = patch_ad_id(root)
        print(f"[3] advertising-id function replaced: {a}")
    if mode == "all":
        mf = root / "AndroidManifest.xml"
        try:
            m = patch_manifest(root)
            l = patch_label(root)
        except UnicodeDecodeError:
            print("[4][5] manifest is binary (folder was decoded with -r): manifest and label left as they are")
        else:
            print(f"[4] AD_ID permission removed: {m}")
            print(f"[5] app label changed: {l}")

    if hosts == 0 and t == 0:
        print("error: neither tracker hosts nor tracker classes found; this does not look like MAX. Nothing patched.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
