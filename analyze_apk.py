#!/usr/bin/env python3
"""Makes a small text report (a few KB) about an apktool-decoded app: what it asks for and where it may connect."""
import re, sys
from collections import Counter
from pathlib import Path

KNOWN = {  # directory prefix in smali -> what it is
    "com/my/tracker": "MyTracker (VK analytics)",
    "com/google/firebase/analytics": "Firebase Analytics",
    "com/google/firebase/crashlytics": "Firebase Crashlytics",
    "com/google/android/gms/measurement": "Google Analytics for Firebase",
    "com/google/android/gms/ads": "Google Ads / advertising id",
    "io/appmetrica": "Yandex AppMetrica",
    "com/yandex/metrica": "Yandex Metrica",
    "com/appsflyer": "AppsFlyer",
    "com/adjust": "Adjust",
    "io/sentry": "Sentry",
    "com/facebook": "Facebook SDK",
    "com/mixpanel": "Mixpanel",
    "com/amplitude": "Amplitude",
    "com/onesignal": "OneSignal",
    "com/huawei/hms": "Huawei HMS",
    "ru/mail": "Mail.ru / VK libraries",
    "com/vk": "VK libraries",
    "ru/ok": "OK.ru libraries",
}


def main(root: Path) -> str:
    out = []
    mf = (root / "AndroidManifest.xml").read_text(encoding="utf-8", errors="replace")
    out.append("== PERMISSIONS ==")
    for p in sorted(set(re.findall(r'<uses-permission[^>]*android:name="([^"]+)"', mf))):
        out.append("  " + p)

    out.append("\n== MANIFEST META-DATA that looks like analytics/ads ==")
    for k in sorted(set(re.findall(r'<meta-data[^>]*android:name="([^"]+)"', mf))):
        if re.search(r"analytic|firebase|metrica|tracker|ads|crash|appsflyer|adjust|sentry|facebook", k, re.I):
            out.append("  " + k)

    smali = [d for d in root.glob("smali*") if d.is_dir()]
    out.append("\n== KNOWN SDKs FOUND (folder -> number of files) ==")
    found = Counter()
    hosts = Counter()
    top = Counter()
    for d in smali:
        for f in d.rglob("*.smali"):
            rel = f.relative_to(d).as_posix()
            parts = rel.split("/")
            if len(parts) > 1:
                top["/".join(parts[:2])] += 1
            for prefix, name in KNOWN.items():
                if rel.startswith(prefix + "/"):
                    found[(prefix, name)] += 1
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for h in re.findall(r"https?://([A-Za-z0-9][A-Za-z0-9.-]{2,}\.[A-Za-z]{2,})", text):
                hosts[h.lower()] += 1
    for (prefix, name), n in sorted(found.items()):
        out.append(f"  {prefix:40s} {name}  ({n} files)")
    if not found:
        out.append("  (none of the known ones)")

    out.append("\n== BIGGEST TOP-LEVEL PACKAGES (to spot unknown SDKs) ==")
    for k, n in top.most_common(40):
        out.append(f"  {k:40s} {n}")

    out.append(f"\n== HOSTS FOUND IN THE CODE ({len(hosts)} different; top 150) ==")
    for h, n in hosts.most_common(150):
        out.append(f"  {h}  x{n}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2 or not (Path(sys.argv[1]) / "AndroidManifest.xml").exists():
        print("usage: analyze_apk.py <apktool folder>")
        sys.exit(2)
    print(main(Path(sys.argv[1])), end="")
