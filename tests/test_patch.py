"""Runs the patcher on a tiny fake apktool folder and checks every promised change."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import patch_max

TRACKER = """.class public Lcom/my/tracker/MyTracker;
.super Ljava/lang/Object;

.method public static flush()V
    .locals 2
    sget-object v0, Lcom/my/tracker/MyTracker;->a:Lcom/my/tracker/obfuscated/i0;
    invoke-virtual {v0}, Lcom/my/tracker/obfuscated/i0;->a()V
    return-void
.end method

.method public static trackLoginEvent(Ljava/lang/String;Ljava/lang/String;Ljava/util/Map;)V
    .locals 1
    invoke-static {}, Lx;->send()V
    return-void
.end method

.method public static trackLoginEvent(Ljava/lang/String;Ljava/lang/String;)V
    .locals 1
    const/4 v0, 0x0
    invoke-static {p0, p1, v0}, Lcom/my/tracker/MyTracker;->trackLoginEvent(Ljava/lang/String;Ljava/lang/String;Ljava/util/Map;)V
    return-void
.end method

.method public static getTrackerParams()Lcom/my/tracker/MyTrackerParams;
    .locals 1
    sget-object v0, Lcom/my/tracker/MyTracker;->a:Lcom/my/tracker/obfuscated/i0;
    return-object v0
.end method
"""

ADID = """.class public Lcom/google/android/gms/ads/identifier/AdvertisingIdClient;
.super Ljava/lang/Object;

.method public static getAdvertisingIdInfo(Landroid/content/Context;)Lcom/google/android/gms/ads/identifier/AdvertisingIdClient$Info;
    .locals 5
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/io/IOException;
        }
    .end annotation
    const/4 v0, 0x0
    return-object v0
.end method
"""

OTHER = """.class public Lfoo/Bar;
.method static go()V
    .locals 1
    const-string v0, "https://tracker-api.vk-analytics.ru/v3/x"
    const-string v1, "https://max.ru/keep-me"
    return-void
.end method
"""

MANIFEST = """<manifest package="ru.oneme.app">
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="com.google.android.gms.permission.AD_ID"/>
</manifest>
"""

STRINGS = '<resources><string name="app_name">MAX</string><string name="x">y</string></resources>'


def build(root: Path):
    (root / "smali/com/my/tracker").mkdir(parents=True)
    (root / "smali/com/my/tracker/MyTracker.smali").write_text(TRACKER)
    (root / "smali_classes2/com/google/android/gms/ads/identifier").mkdir(parents=True)
    (root / "smali_classes2/com/google/android/gms/ads/identifier/AdvertisingIdClient.smali").write_text(ADID)
    (root / "smali/foo").mkdir()
    (root / "smali/foo/Bar.smali").write_text(OTHER)
    (root / "AndroidManifest.xml").write_text(MANIFEST)
    (root / "res/values").mkdir(parents=True)
    (root / "res/values/strings.xml").write_text(STRINGS)


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        check.failed += 1
check.failed = 0


with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    build(root)
    rc = patch_max.main(["patch_max.py", str(root)])
    check(rc == 0, "patcher exit code 0")

    t = (root / "smali/com/my/tracker/MyTracker.smali").read_text()
    check("sget-object v0, Lcom/my/tracker/MyTracker;->a" in t and t.count("return-void") == 3, "tracker: untouched getTrackerParams still there")
    check("invoke-static {}, Lx;->send()V" not in t, "tracker: send body of trackLoginEvent(3) removed")
    check("invoke-virtual {v0}, Lcom/my/tracker/obfuscated/i0;->a()V" not in t, "tracker: flush emptied")
    check(".method public static getTrackerParams()Lcom/my/tracker/MyTrackerParams;" in t, "tracker: getTrackerParams kept")
    check(t.count(".end method") == 4, "tracker: all 4 methods still closed")

    a = (root / "smali_classes2/com/google/android/gms/ads/identifier/AdvertisingIdClient.smali").read_text()
    check("00000000-0000-0000-0000-000000000000" in a and "return-object v0" in a, "ad id: zero id returned")
    check("Ljava/io/IOException;" not in a, "ad id: old body gone")

    o = (root / "smali/foo/Bar.smali").read_text()
    check("blocked.invalid/v3/x" in o and "tracker-api.vk-analytics.ru" not in o, "hosts: tracker replaced")
    check("https://max.ru/keep-me" in o, "hosts: MAX's own address untouched")

    check("AD_ID" not in (root / "AndroidManifest.xml").read_text(), "manifest: AD_ID removed")
    check("android.permission.INTERNET" in (root / "AndroidManifest.xml").read_text(), "manifest: other permissions kept")
    s = (root / "res/values/strings.xml").read_text()
    check('name="app_name">MAX Clean<' in s and 'name="x">y<' in s, "label: changed, other strings kept")

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root / "smali").mkdir()
    (root / "AndroidManifest.xml").write_text("<manifest/>")
    check(patch_max.main(["p", str(root)]) == 1, "not MAX -> refuses (exit 1)")

import analyze_apk
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    build(root)
    rep = analyze_apk.main(root)
    check("android.permission.INTERNET" in rep, "report: lists permissions")
    check("MyTracker (VK analytics)" in rep, "report: finds MyTracker")
    check("tracker-api.vk-analytics.ru" in rep and "max.ru" in rep, "report: lists hosts")

if check.failed:
    print(f"{check.failed} FAILED"); sys.exit(1)
print("ALL PASSED")
