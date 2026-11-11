#!/usr/bin/env python3
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

VOID_STUBS = [
    ("com/my/tracker/MyTracker.smali",
     ["flush", "trackLaunchManually", "trackLoginEvent", "trackRegistrationEvent"]),
    ("ru/ok/android/externcalls/analytics/CallAnalyticsSender.smali",
     ["send", "forceSendScheduledEvents"]),
]

KILL_SWITCH_REF = re.compile(
    r"->(?:analytics-enabled|f\d+analyticsenabled):Lru/ok/tamtam/android/prefs/PmsKey;")

METHOD_HEADER = re.compile(r"^\.method\s+(?P<mods>.*?)(?P<name>[^\s(]+)\((?P<args>[^)]*)\)(?P<ret>\S+)\s*$")


def smali_dirs(root: Path):
    return sorted(d for d in root.glob("smali*") if d.is_dir())


def smali_files(root: Path):
    return [p for d in smali_dirs(root) for p in d.rglob("*.smali")]


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="surrogateescape")


def write(p: Path, text: str):
    p.write_text(text, encoding="utf-8", errors="surrogateescape")


def split_methods(text: str):
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
    print(f"[1] tracker hosts -> {DEAD_HOST}: {hosts} in {files} file(s)")
    stubs, kills = {}, []
    if mode == "full":
        stubs = patch_void_stubs(root, touched)
        print(f"[2] send-methods stubbed: {sum(stubs.values())}")
        kills = patch_kill_switch(root, touched)
        print(f"[3] MAX analytics switched off: {sum(n for _, n in kills)} method(s)")

    if hosts == 0 and not stubs:
        print("error: no tracker hosts found. Nothing patched.")
        return 1

    report.update(
        mode=mode,
        hosts_replaced=hosts,
        stubs=stubs,
        kill_switch=[p for p, _ in kills],
        touched_smali=sorted(p.relative_to(root).as_posix() for p in touched),
        touched_dex=sorted({dex_name(root, p) for p in touched}),
    )
    print("dex files changed:", ", ".join(report["touched_dex"]) or "none")
    return 0


def main(argv):
    if len(argv) < 3 or argv[1] != "dex":
        print("Usage: python3 patch_max.py dex <decoded_folder> [hosts|full]")
        return 2
    root = Path(argv[2])
    mode = argv[3] if len(argv) > 3 else "full"
    report_path = root / "patch-report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}

    if not smali_dirs(root):
        print("error: no smali folders in", root)
        return 2

    rc = run_dex(root, mode, report)
    if rc == 0:
        report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
