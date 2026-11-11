#!/usr/bin/env python3
"""Tests for patch_max.py, graft_apk.py, check_manifest.py on a small mock of MAX (shaped like the real decompiled code).
Run: python3 -I tests/test_patch.py"""
import json
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
import patch_max  # noqa: E402
import graft_apk  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


MY_TRACKER = """.class public final Lcom/my/tracker/MyTracker;
.super Ljava/lang/Object;

.method public static flush()V
    .locals 2
    sget-object v0, Lcom/my/tracker/MyTracker;->a:Lcom/my/tracker/obfuscated/i0;
    invoke-virtual {v0}, Lcom/my/tracker/obfuscated/i0;->a()V
    return-void
.end method

.method public static getTrackerParams()Lcom/my/tracker/MyTrackerParams;
    .locals 1
    const/4 v0, 0x0
    return-object v0
.end method

.method public static handleDeeplink(Landroid/content/Intent;)Ljava/lang/String;
    .locals 1
    const/4 v0, 0x0
    return-object v0
.end method

.method public static initTracker(Ljava/lang/String;Landroid/app/Application;)V
    .locals 1
    const-string v0, "init"
    return-void
.end method

.method public static trackLaunchManually(Landroid/app/Activity;)V
    .locals 1
    const-string v0, "launch"
    return-void
.end method

.method public static trackLoginEvent(Ljava/lang/String;Ljava/lang/String;)V
    .locals 1
    const-string v0, "login2"
    return-void
.end method

.method public static trackLoginEvent(Ljava/lang/String;Ljava/lang/String;Ljava/util/Map;)V
    .locals 1
    const-string v0, "login3"
    return-void
.end method

.method public static trackRegistrationEvent(Ljava/lang/String;Ljava/lang/String;)V
    .locals 1
    const-string v0, "reg"
    return-void
.end method
"""

CALL_SENDER = """.class public final Lru/ok/android/externcalls/analytics/CallAnalyticsSender;
.super Ljava/lang/Object;

.method public final declared-synchronized initialize(Lru/ok/android/externcalls/analytics/config/CallAnalyticsConfig;)V
    .locals 1
    const-string v0, "init"
    return-void
.end method

.method public final send(Lru/ok/android/externcalls/analytics/events/CallAnalyticsEvent;)V
    .locals 2
    const-string v0, "send"
    return-void
.end method

.method public final forceSendScheduledEvents()V
    .locals 2
    const-string v0, "force"
    return-void
.end method
"""

IN7 = """.class public final Ldefpackage/in7;
.super Ljava/lang/Object;

.method public final c()Z
    .locals 3
    iget-object v0, p0, Ldefpackage/in7;->Y:Lt97;
    invoke-interface {v0}, Lt97;->getValue()Ljava/lang/Object;
    move-result-object v0
    sget-object v1, Lru/ok/tamtam/android/prefs/PmsKey;->analytics-enabled:Lru/ok/tamtam/android/prefs/PmsKey;
    const/4 v2, 0x1
    invoke-interface {v0, v1, v2}, Ljb5;->m(Lru/ok/tamtam/android/prefs/PmsKey;Z)Z
    move-result v0
    xor-int/2addr v0, v2
    return v0
.end method

.method public final d()Z
    .locals 1
    const/4 v0, 0x0
    return v0
.end method
"""

# must NOT be touched: other analytics-like keys
OTHER_KEYS = """.class public final Ldefpackage/zzz;
.super Ljava/lang/Object;

.method public final a()Z
    .locals 2
    sget-object v1, Lru/ok/tamtam/android/prefs/PmsKey;->wm-analytics-enabled:Lru/ok/tamtam/android/prefs/PmsKey;
    const/4 v0, 0x0
    return v0
.end method

.method public final b()Z
    .locals 2
    sget-object v1, Lru/ok/tamtam/android/prefs/PmsKey;->analytics-permissions:Lru/ok/tamtam/android/prefs/PmsKey;
    const/4 v0, 0x0
    return v0
.end method
"""

TRACER = """.class public final Lj3d;
.super Ljava/lang/Object;

.method public final a()V
    .locals 2
    const-string v0, "https://sdk-api.apptracer.ru"
    const-string v1, "tracker-api.vk-analytics.ru"
    return-void
.end method
"""

UNTOUCHED = """.class public final Lpl/untouched;
.super Ljava/lang/Object;

.method public final x()V
    .locals 1
    const-string v0, "api.oneme.ru"
    return-void
.end method
"""

MANIFEST = """<?xml version="1.0" encoding="utf-8" standalone="no"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="ru.oneme.app">
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="com.google.android.gms.permission.AD_ID"/>
    <application android:icon="@mipmap/ic_launcher" android:label="@string/app_name" android:name="one.me.android.App">
        <activity android:exported="true" android:label="@string/app_name" android:name="one.me.android.MainActivity">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
        <activity android:exported="true" android:name="one.me.android.deeplink.LinkInterceptorActivity">
            <intent-filter android:autoVerify="true">
                <action android:name="android.intent.action.VIEW"/>
                <category android:name="android.intent.category.DEFAULT"/>
                <category android:name="android.intent.category.BROWSABLE"/>
                <data android:scheme="https"/>
                <data android:host="max.ru" android:pathPrefix="/join"/>
                <data android:host="max.ru" android:pathPrefix="/u"/>
            </intent-filter>
            <intent-filter>
                <action android:name="android.intent.action.VIEW"/>
                <category android:name="android.intent.category.DEFAULT"/>
                <data android:scheme="max"/>
            </intent-filter>
        </activity>
        <activity android:exported="false" android:name="one.me.android.Other"/>
    </application>
</manifest>
"""


def make_tree(tmp: Path):
    d = tmp / "dec"
    (d / "smali/com/my/tracker").mkdir(parents=True)
    (d / "smali_classes2/ru/ok/android/externcalls/analytics").mkdir(parents=True)
    (d / "smali_classes3/defpackage").mkdir(parents=True)
    (d / "smali_classes4/pl/untouched").mkdir(parents=True)
    (d / "smali/com/my/tracker/MyTracker.smali").write_text(MY_TRACKER)
    (d / "smali_classes2/ru/ok/android/externcalls/analytics/CallAnalyticsSender.smali").write_text(CALL_SENDER)
    (d / "smali_classes3/defpackage/in7.smali").write_text(IN7)
    (d / "smali_classes3/defpackage/zzz.smali").write_text(OTHER_KEYS)
    (d / "smali_classes3/defpackage/j3d.smali").write_text(TRACER)
    (d / "smali_classes4/pl/untouched/U.smali").write_text(UNTOUCHED)
    return d


def run(*args):
    return subprocess.run([sys.executable, "-I", str(ROOT / "patch_max.py"), *map(str, args)],
                          capture_output=True, text=True)


def test_dex():
    with tempfile.TemporaryDirectory() as t:
        d = make_tree(Path(t))
        r = run("dex", d, "full")
        check(r.returncode == 0, "dex full: exit 0\n" + r.stdout + r.stderr)
        mt = (d / "smali/com/my/tracker/MyTracker.smali").read_text()
        # stubbed
        for name in ("flush", "trackLaunchManually", "trackLoginEvent", "trackRegistrationEvent"):
            blk = mt.split(f"{name}(")[1].split(".end method")[0]
            check("return-void" in blk and "sget" not in blk and '"launch"' not in blk and '"login' not in blk and '"reg"' not in blk,
                  f"MyTracker.{name} is a stub")
        # both trackLoginEvent overloads
        check(mt.count(".locals 0") == 5, "MyTracker: 5 stubs (flush, launch, 2x login, registration)")
        # kept
        check('"init"' in mt, "MyTracker.initTracker kept")
        check("return-object v0" in mt.split("getTrackerParams")[1].split(".end method")[0], "getTrackerParams kept")
        check("handleDeeplink" in mt and mt.count("return-object v0") == 2, "handleDeeplink kept")
        cs = (d / "smali_classes2/ru/ok/android/externcalls/analytics/CallAnalyticsSender.smali").read_text()
        check('"init"' in cs and '"send"' not in cs and '"force"' not in cs, "CallAnalytics: send/force stubbed, initialize kept")
        # kill switch
        i7 = (d / "smali_classes3/defpackage/in7.smali").read_text()
        c = i7.split(".method public final c()Z")[1].split(".end method")[0]
        check("const/4 v0, 0x1" in c and "return v0" in c and "invoke-interface" not in c, "in7.c() answers 'analytics disabled'")
        check(".method public final d()Z\n    .locals 1\n    const/4 v0, 0x0" in i7, "in7.d() untouched")
        zz = (d / "smali_classes3/defpackage/zzz.smali").read_text()
        check(zz == OTHER_KEYS, "wm-analytics-enabled / analytics-permissions are not touched")
        # hosts
        tr = (d / "smali_classes3/defpackage/j3d.smali").read_text()
        check('"https://0.0.0.0"' in tr and '"0.0.0.0"' in tr and "apptracer" not in tr and "vk-analytics" not in tr, "hosts -> 0.0.0.0")
        check((d / "smali_classes4/pl/untouched/U.smali").read_text() == UNTOUCHED, "api.oneme.ru and other classes untouched")
        rep = json.loads((d / "patch-report.json").read_text())
        check(rep["touched_dex"] == ["classes.dex", "classes2.dex", "classes3.dex"], f"touched dex = 1,2,3 (not 4): {rep['touched_dex']}")


def test_dex_hosts_only():
    with tempfile.TemporaryDirectory() as t:
        d = make_tree(Path(t))
        r = run("dex", d, "hosts")
        check(r.returncode == 0, "dex hosts: exit 0")
        check((d / "smali/com/my/tracker/MyTracker.smali").read_text() == MY_TRACKER, "hosts-only: MyTracker untouched")
        check((d / "smali_classes3/defpackage/in7.smali").read_text() == IN7, "hosts-only: in7 untouched")
        rep = json.loads((d / "patch-report.json").read_text())
        check(rep["touched_dex"] == ["classes3.dex"], f"hosts-only touches classes3 only: {rep['touched_dex']}")


def test_dex_not_max():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "x"
        (d / "smali/a").mkdir(parents=True)
        (d / "smali/a/A.smali").write_text(".class public La/A;\n.super Ljava/lang/Object;\n")
        r = run("dex", d, "full")
        check(r.returncode == 1 and "does not look like MAX" in r.stdout, "not MAX -> error, exit 1")
        check(run("dex", Path(t) / "none").returncode == 2, "no smali -> exit 2")


def test_manifest():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "res"
        d.mkdir()
        (d / "AndroidManifest.xml").write_text(MANIFEST)
        r = run("manifest", d)
        check(r.returncode == 0, "manifest: exit 0\n" + r.stdout)
        m = (d / "AndroidManifest.xml").read_text()
        check(m.count('android:host="www.max.ru"') == 2, "www.max.ru twin for each max.ru tag (2)")
        check('<data android:host="www.max.ru" android:pathPrefix="/join"/>' in m, "twin keeps pathPrefix /join")
        check('<data android:host="www.max.ru" android:pathPrefix="/u"/>' in m, "twin keeps pathPrefix /u")
        check('android:autoVerify="true"' in m, "autoVerify kept")
        check("AD_ID" not in m and "android.permission.INTERNET" in m, "AD_ID removed, INTERNET kept")
        check(m.count('android:label="MAX Clean"') == 2, "label: application + launcher activity")
        check('android:label="@string/app_name"' not in m, "no old label left")
        check('<data android:scheme="max"/>' in m, "max:// scheme filter untouched")
        import xml.dom.minidom
        xml.dom.minidom.parseString(m.encode())
        check(True, "result is well-formed XML")
        r2 = run("manifest", d)
        m2 = (d / "AndroidManifest.xml").read_text()
        check(r2.returncode == 0 and m2 == m, "second run changes nothing (idempotent)")


def test_manifest_fallback():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "res"
        d.mkdir()
        (d / "AndroidManifest.xml").write_text(
            MANIFEST.replace('max.ru" android:pathPrefix="/join"', 'example.org" android:pathPrefix="/join"')
            .replace('max.ru" android:pathPrefix="/u"', 'example.org" android:pathPrefix="/u"'))
        r = run("manifest", d)
        m = (d / "AndroidManifest.xml").read_text()
        check(r.returncode == 0 and m.count('android:host="www.max.ru"') == 1 and m.count('android:host="max.ru"') == 1,
              "no max.ru filter: new filter added to LinkInterceptorActivity")
        import xml.dom.minidom
        dom = xml.dom.minidom.parseString(m.encode())
        acts = [a for a in dom.getElementsByTagName("activity")
                if a.getAttribute("android:name").endswith("LinkInterceptorActivity")]
        check(len(acts) == 1 and any("www.max.ru" in f.toxml() for f in acts[0].getElementsByTagName("intent-filter")),
              "fallback filter sits inside LinkInterceptorActivity")


def test_manifest_errors():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "res"
        d.mkdir()
        (d / "AndroidManifest.xml").write_bytes(b"\x03\x00\x08\x00\xff\xfe")
        check(run("manifest", d).returncode == 2, "binary manifest -> exit 2")
        (d / "AndroidManifest.xml").write_text(MANIFEST.replace("LinkInterceptorActivity", "Gone").replace('"max.ru"', '"e.org"'))
        check(run("manifest", d).returncode == 1, "no max.ru and no link activity -> exit 1")


def fake_dex(classes: int, tag: bytes) -> bytes:
    h = bytearray(0x70)
    h[:8] = b"dex\n035\x00"
    struct.pack_into("<I", h, 0x60, classes)
    return bytes(h) + tag


def test_graft():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        orig, new, out = t / "o.apk", t / "n.apk", t / "g.apk"
        with zipfile.ZipFile(orig, "w") as z:
            z.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00ORIG")
            z.writestr("classes.dex", fake_dex(3, b"o1"), compress_type=zipfile.ZIP_STORED)
            z.writestr("classes2.dex", fake_dex(5, b"o2"))
            z.writestr("classes3.dex", fake_dex(7, b"o3"))
            zi = zipfile.ZipInfo("resources.arsc")
            zi.compress_type = zipfile.ZIP_STORED
            z.writestr(zi, b"ARSC-ORIGINAL")
            z.writestr("lib/arm64-v8a/libx.so", b"SO")
            z.writestr("META-INF/MANIFEST.MF", b"old")
            z.writestr("META-INF/CERT.SF", b"old")
            z.writestr("META-INF/CERT.RSA", b"old")
            z.writestr("META-INF/services/keep.me", b"keep")
        with zipfile.ZipFile(new, "w") as z:
            z.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00NEW")
            z.writestr("classes.dex", fake_dex(3, b"n1"))
            z.writestr("classes2.dex", fake_dex(5, b"n2"))
            z.writestr("classes3.dex", fake_dex(7, b"n3"))
            z.writestr("resources.arsc", b"ARSC-REBUILT")
            z.writestr("lib/arm64-v8a/libx.so", b"REBUILT")
        graft_apk.graft(orig, out, new, new, ["classes2.dex"])
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            check(z.read("AndroidManifest.xml").endswith(b"NEW"), "graft: manifest from rebuilt")
            check(z.read("classes2.dex").endswith(b"n2"), "graft: classes2.dex from rebuilt")
            check(z.read("classes.dex").endswith(b"o1") and z.read("classes3.dex").endswith(b"o3"), "graft: other dex from original")
            check(z.read("resources.arsc") == b"ARSC-ORIGINAL" and z.getinfo("resources.arsc").compress_type == zipfile.ZIP_STORED,
                  "graft: resources.arsc original and stored")
            check(z.read("lib/arm64-v8a/libx.so") == b"SO", "graft: libs from original")
            check(not any(n in names for n in ("META-INF/MANIFEST.MF", "META-INF/CERT.SF", "META-INF/CERT.RSA")), "graft: old signature dropped")
            check("META-INF/services/keep.me" in names, "graft: other META-INF kept")
            check(z.getinfo("classes.dex").compress_type == zipfile.ZIP_STORED, "graft: compression of untouched entries kept")
        # class count mismatch
        bad = t / "b.apk"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("classes2.dex", fake_dex(4, b"x"))
        try:
            graft_apk.graft(orig, t / "x.apk", None, bad, ["classes2.dex"])
            check(False, "graft: class count mismatch must fail")
        except SystemExit as e:
            check("classes" in str(e), "graft: class count mismatch fails")
        # missing entry
        try:
            graft_apk.graft(orig, t / "y.apk", bad, None, [])
            check(False, "graft: missing manifest must fail")
        except SystemExit:
            check(True, "graft: manifest missing in rebuilt fails")


def test_check_manifest():
    import check_manifest
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        a, b, c = t / "a", t / "b", t / "c"
        a.write_text("E: application (line=5)\n  A: android:icon(0x01010002)=@0x7f0f0000\n  A: android:label(0x01010001)=@0x7f120027\n"
                     "  E: uses-permission (line=3)\n    A: android:name(0x01010003)=\"com.google.android.gms.permission.AD_ID\"\n")
        b.write_text("E: application (line=9)\n  A: android:icon(0x01010002)=@0x7f0f0000\n  A: android:label(0x01010001)=\"MAX Clean\"\n"
                     "  E: data (line=70)\n    A: android:host(0x01010028)=\"www.max.ru\"\n")
        c.write_text("E: application (line=5)\n  A: android:icon(0x01010002)=@0x7f0f0123\n")
        check(check_manifest.main(str(a), str(b)) == 0, "check_manifest: intended changes pass")
        check(check_manifest.main(str(a), str(c)) == 1, "check_manifest: shifted resource id fails")


if __name__ == "__main__":
    for fn in (test_dex, test_dex_hosts_only, test_dex_not_max, test_manifest, test_manifest_fallback,
               test_manifest_errors, test_graft, test_check_manifest):
        fn()
    print("\nALL PASSED" if not FAILS else f"\n{len(FAILS)} FAILED")
    sys.exit(1 if FAILS else 0)
