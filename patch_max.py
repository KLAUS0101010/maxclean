#!/usr/bin/env python3
"""
MAX Clean patcher (v2). Written against the real decompiled MAX 25.7.x code.

Usage:
  python3 patch_max.py dex      <apktool folder, decoded with -r>  [hosts|full]
  python3 patch_max.py manifest <apktool folder, decoded with --no-src>

"dex" mode (tracking removal), every step is reported:
  1. Hosts of tracking services are replaced with 0.0.0.0 (nothing can be sent there):
       tracker-api.vk-analytics.ru / tracker-api.my.com   MyTracker (VK)
       sdk-api.apptracer.ru                               VK Tracer (crashes, profiler, heap dumps, disk usage)
  2. (mode "full") Send-methods become stubs that return at once:
       MyTracker.flush / trackLaunchManually / trackLoginEvent / trackRegistrationEvent
       CallAnalyticsSender.send / forceSendScheduledEvents   (OK.ru calls analytics inside MAX)
     Not touched on purpose: MyTracker.initTracker / getTrackerParams / handleDeeplink
     (MAX calls getTrackerParams().setCustomUserId(...) at login, and handleDeeplink() on every opened link).
  3. (mode "full") MAX's own analytics (events/logs it sends through its own API connection) is switched off with the
     switch the app already has: PmsKey "analytics-enabled". The method that reads it is made to answer "disabled".
     All sending code in the app asks this method first and returns early, so nothing else changes.
  Nothing is deleted, no classes are removed.

"manifest" mode:
  4. Links: every <data android:host="max.ru"> gets a twin for www.max.ru (same scheme / path rules).
     If the manifest has no max.ru filter at all, a new filter is added to LinkInterceptorActivity.
  5. The advertising-id permission (AD_ID) is removed.
  6. The app name on the launcher becomes "MAX Clean".

Writes patch-report.json into the folder: which smali files were touched (graft_apk.py needs this to
know which classesN.dex have to be taken from the rebuilt apk).
Only third-party tracking and MAX's own analytics are handled. Messages, login, calls, push are not touched.
"""
import json
import re
import sys
from pathlib import Path

DEAD_HOST = "0.0.0.0"

HOSTS = [
    "tracker-api.vk-analytics.ru",
    "tracker-api.my.com",
    "sdk-api.apptracer.ru",
]

# (class file, [void methods that only send data])
VOID_STUBS = [
    ("com/my/tracker/MyTracker.smali",
     ["flush", "trackLaunchManually", "trackLoginEvent", "trackRegistrationEvent"]),
    ("ru/ok/android/externcalls/analytics/CallAnalyticsSender.smali",
     ["send", "forceSendScheduledEvents"]),
]

# the app's own analytics switch: PmsKey.analytics-enabled (jadx shows it as f<N>analyticsenabled)
KILL_SWITCH_REF = re.compile(
    r"->(?:analytics-enabled|f\d+analyticsenabled):Lru/ok/tamtam/android/prefs/PmsKey;")

LABEL = "MAX Clean"
LINK_ACTIVITY = "one.me.android.deeplink.LinkInterceptorActivity"
WWW = "www.max.ru"
BARE = "max.ru"

METHOD_HEADER = re.compile(r"^\.method\s+(?P<mods>.*?)(?P<name>[^\s(]+)\((?P<args>[^)]*)\)(?P<ret>\S+)\s*$")


# ------------------------------------------------------------------ smali helpers
def smali_dirs(root: Path):
    return sorted(d for d in root.glob("smali*") if d.is_dir())


def smali_files(root: Path):
    return [p for d in smali_dirs(root) for p in d.rglob("*.smali")]


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="surrogateescape")


def write(p: Path, text: str):
    p.write_text(text, encoding="utf-8", errors="surrogateescape")


def split_methods(text: str):
    """Yield (kind, lines): kind 'other' for everything outside methods, 'method' for a whole .method..end method."""
    out, cur, in_m = [], [], False
    for line in text.splitlines(keepends=True):
        if not in_m and line.startswith(".method "):
            if cur:
                out.append(("other", cur))
            cur, in_m = [line], True
        elif in_m and line.startswith(".end method"):
            cur.append(line)
            out.append(("method", cur))
            cur, in_m = [], False
        else:
            cur.append(line)
    if cur:
        out.append(("method" if in_m else "other", cur))
    return out


def header_of(lines):
    return METHOD_HEADER.match(lines[0].rstrip("\n"))


def has_code(mods: str) -> bool:
    words = mods.split()
    return "abstract" not in words and "native" not in words


def rebuild(parts, replace):
    """replace(lines, header) -> new lines or None to keep."""
    changed = 0
    chunks = []
    for kind, lines in parts:
        if kind == "method":
            h = header_of(lines)
            new = replace(lines, h) if h else None
            if new is not None:
                lines = new
                changed += 1
        chunks.append("".join(lines))
    return "".join(chunks), changed


# ------------------------------------------------------------------ dex-side patches
def replace_hosts(root: Path, touched: set):
    files = total = 0
    for f in smali_files(root):
        text = read(f)
        if not any(h in text for h in HOSTS):
            continue
        new = text
        for h in HOSTS:
            total += new.count(h)
            new = new.replace(h, DEAD_HOST)
        write(f, new)
        touched.add(f)
        files += 1
    return files, total


def patch_void_stubs(root: Path, touched: set):
    report = {}
    for f in smali_files(root):
        rel = f.as_posix()
        for suffix, names in VOID_STUBS:
            if not rel.endswith(suffix):
                continue

            def stub(lines, h, names=names):
                if h["name"] in names and h["ret"] == "V" and has_code(h["mods"]):
                    return [lines[0], "    .locals 0\n", "    return-void\n", lines[-1]]
                return None

            new, n = rebuild(split_methods(read(f)), stub)
            if n:
                write(f, new)
                touched.add(f)
            report[suffix] = report.get(suffix, 0) + n
    return report


def patch_kill_switch(root: Path, touched: set):
    """Every `()Z` method that reads PmsKey.analytics-enabled now returns true ("analytics is disabled")."""
    hits = []
    for f in smali_files(root):
        text = read(f)
        if "analytics" not in text or not KILL_SWITCH_REF.search(text):
            continue

        def stub(lines, h):
            if h["args"] == "" and h["ret"] == "Z" and has_code(h["mods"]) \
                    and any(KILL_SWITCH_REF.search(l) for l in lines):
                return [lines[0], "    .locals 1\n", "    const/4 v0, 0x1\n", "    return v0\n", lines[-1]]
            return None

        new, n = rebuild(split_methods(text), stub)
        if n:
            write(f, new)
            touched.add(f)
            hits.append((f.as_posix(), n))
    return hits


def dex_name(root: Path, f: Path) -> str:
    top = f.relative_to(root).parts[0]
    if top == "smali":
        return "classes.dex"
    m = re.fullmatch(r"smali_classes(\d+)", top)
    if not m:
        raise ValueError("unexpected smali folder " + top)
    return f"classes{m.group(1)}.dex"


def run_dex(root: Path, mode: str, report: dict) -> int:
    touched = set()
    files, hosts = replace_hosts(root, touched)
    print(f"[1] tracker hosts -> {DEAD_HOST}: {hosts} occurrence(s) in {files} file(s)")
    stubs, kills = {}, []
    if mode == "full":
        stubs = patch_void_stubs(root, touched)
        print(f"[2] send-methods stubbed: {sum(stubs.values())}")
        for k, v in sorted(stubs.items()):
            print(f"      {k}: {v}")
        kills = patch_kill_switch(root, touched)
        print(f"[3] MAX own analytics switched off (analytics-enabled): {sum(n for _, n in kills)} method(s)")
        for p, n in kills:
            print(f"      {p}: {n}")
        if not kills:
            print("    WARNING: analytics switch not found; MAX's own analytics stays on")
        if not stubs.get("com/my/tracker/MyTracker.smali"):
            print("    WARNING: MyTracker stubs not found")
    if hosts == 0 and not stubs:
        print("error: no tracker hosts and no tracker classes found: this does not look like MAX. Nothing patched.")
        return 1
    report.update(
        mode=mode,
        hosts_replaced=hosts,
        stubs=stubs,
        kill_switch=[p for p, _ in kills],
        touched_smali=sorted(p.relative_to(root).as_posix() for p in touched),
        touched_dex=sorted({dex_name(root, p) for p in touched}),
    )
    print("dex files that changed:", ", ".join(report["touched_dex"]) or "none")
    return 0


# ------------------------------------------------------------------ manifest patches
DATA_TAG = re.compile(r"[ \t]*<data\b[^>]*?/>[ \t]*\n?")
FILTER_BLOCK = re.compile(r"<intent-filter\b[^>]*>.*?</intent-filter>", re.S)


def add_www_to_filters(text: str):
    """In each intent-filter, for every <data ... host=max.ru ...> add the same tag for www.max.ru."""
    bare_attr = f'android:host="{BARE}"'
    www_attr = f'android:host="{WWW}"'
    added = 0

    def fix_block(m):
        nonlocal added
        block = m.group(0)
        out, pos = [], 0
        for dm in DATA_TAG.finditer(block):
            tag = dm.group(0)
            if bare_attr not in tag:
                continue
            twin = tag.replace(bare_attr, www_attr)
            if twin.strip() in block:
                continue
            out.append(block[pos:dm.end()])
            out.append(twin if twin.endswith("\n") else twin + "\n")
            pos = dm.end()
            added += 1
        out.append(block[pos:])
        return "".join(out)

    return FILTER_BLOCK.sub(fix_block, text), added


NEW_FILTER = (
    '            <intent-filter>\n'
    '                <action android:name="android.intent.action.VIEW"/>\n'
    '                <category android:name="android.intent.category.DEFAULT"/>\n'
    '                <category android:name="android.intent.category.BROWSABLE"/>\n'
    '                <data android:scheme="https"/>\n'
    '                <data android:scheme="http"/>\n'
    f'                <data android:host="{BARE}"/>\n'
    f'                <data android:host="{WWW}"/>\n'
    '            </intent-filter>\n'
)


def add_fallback_filter(text: str):
    """No max.ru filter in the manifest: give the link activity one."""
    m = re.search(r'<activity\b[^>]*android:name="' + re.escape(LINK_ACTIVITY) + r'"[^>]*?(/?)>', text)
    if not m:
        return text, False
    if m.group(1) == "/":  # <activity .../>  ->  <activity ...> filter </activity>
        head = m.group(0)[:-2].rstrip() + ">\n"
        return text[:m.start()] + head + NEW_FILTER + "        </activity>" + text[m.end():], True
    end = text.find("</activity>", m.end())
    if end == -1:
        return text, False
    return text[:end] + NEW_FILTER + "        " + text[end:], True


def remove_ad_id(text: str):
    return re.subn(r'[ \t]*<uses-permission\b[^>]*com\.google\.android\.gms\.permission\.AD_ID[^>]*/>[ \t]*\n?', "", text)


def set_labels(text: str):
    """Launcher name. The <application> label and the label of the activity with MAIN+LAUNCHER."""
    n = 0

    def set_attr(tag: str):
        nonlocal n
        new, k = re.subn(r'android:label="[^"]*"', f'android:label="{LABEL}"', tag, count=1)
        n += k
        return new

    text = re.sub(r"<application\b[^>]*>", lambda m: set_attr(m.group(0)), text, count=1)

    def activity(m):
        block = m.group(0)
        if "android.intent.category.LAUNCHER" not in block:
            return block
        head_end = block.find(">") + 1
        return set_attr(block[:head_end]) + block[head_end:]

    text = re.sub(r"<activity\b[^>]*?/>|<activity\b[^>]*?>.*?</activity>", activity, text, flags=re.S)
    return text, n


def run_manifest(root: Path, report: dict) -> int:
    mf = root / "AndroidManifest.xml"
    try:
        text = mf.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        print("error: AndroidManifest.xml is missing or binary (folder must be decoded with --no-src, not -r)")
        return 2
    if "<manifest" not in text:
        print("error: this is not a decoded manifest")
        return 2
    text, www = add_www_to_filters(text)
    fallback = False
    if www == 0 and f'android:host="{WWW}"' not in text:
        text, fallback = add_fallback_filter(text)
    text, ad = remove_ad_id(text)
    text, lab = set_labels(text)
    mf.write_text(text, encoding="utf-8")
    print(f"[4] www.max.ru added next to max.ru: {www} <data> tag(s); fallback filter added: {fallback}")
    print(f"[5] AD_ID permission removed: {ad}")
    print(f"[6] launcher label set to '{LABEL}': {lab} place(s)")
    if www == 0 and not fallback and f'android:host="{WWW}"' not in text:
        print(f"error: neither a max.ru filter nor {LINK_ACTIVITY} found in the manifest; links not handled")
        return 1
    report.update(manifest=dict(www_added=www, fallback_filter=fallback, ad_id_removed=ad, labels=lab))
    return 0


# ------------------------------------------------------------------ main
def main(argv):
    if len(argv) < 3 or argv[1] not in ("dex", "manifest"):
        print(__doc__)
        return 2
    root = Path(argv[2])
    report_path = root / "patch-report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    if argv[1] == "dex":
        mode = argv[3] if len(argv) > 3 else "full"
        if mode not in ("hosts", "full"):
            print("mode must be hosts or full")
            return 2
        if not smali_dirs(root):
            print("error: no smali folders in", root)
            return 2
        rc = run_dex(root, mode, report)
    else:
        rc = run_manifest(root, report)
    if rc == 0:
        report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
