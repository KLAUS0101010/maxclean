"""
graft_apk.py <original.apk> <out.apk> [--manifest-from <apk>] [--dex-from <apk> (--dex classesN.dex ... | --report patch-report.json)]

Builds the result from the ORIGINAL apk and takes from rebuilt apks only what we really changed:
  --dex-from       apk built from the patched smali; only the classesN.dex files that contain patched classes are taken
                   (the list is --dex ... or "touched_dex" of patch-report.json)
  --manifest-from  apk built from the patched manifest; only AndroidManifest.xml is taken
Everything else (resources.arsc, res/, lib/, assets/, all other dex files) stays byte for byte as in the original
and keeps its compression, so a rebuild cannot break what was not touched.
Old signature files (META-INF/*.SF|*.RSA|*.DSA|*.EC|MANIFEST.MF) are dropped: sign the result afterwards.
Checks: a replaced dex must have the same number of classes as the original; the manifest must be binary XML.
"""
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

SIG = re.compile(r"^META-INF/(MANIFEST\.MF|[^/]+\.(SF|RSA|DSA|EC))$", re.I)


def dex_classes(data: bytes) -> int:
    if data[:4] != b"dex\n":
        raise ValueError("not a dex file")
    return struct.unpack_from("<I", data, 0x60)[0]


def graft(original: Path, out: Path, manifest_from=None, dex_from=None, dex=()):
    """Returns a list of log lines."""
    log = []
    dex = list(dex)
    if dex and not dex_from:
        raise SystemExit("error: --dex needs --dex-from")
    zm = zipfile.ZipFile(manifest_from) if manifest_from else None
    zd = zipfile.ZipFile(dex_from) if dex_from else None
    try:
        with zipfile.ZipFile(original) as zo, zipfile.ZipFile(out, "w") as zw:
            names_o = set(zo.namelist())
            for what, z, items in (("dex", zd, dex), ("manifest", zm, ["AndroidManifest.xml"] if zm else [])):
                missing = [n for n in items if n not in names_o or n not in set(z.namelist())]
                if missing:
                    raise SystemExit(f"error: not found in original or rebuilt apk: {', '.join(missing)}")
            for info in zo.infolist():
                name = info.filename
                if SIG.match(name):
                    continue
                data = zo.read(name)
                if name in dex:
                    new = zd.read(name)
                    a, b = dex_classes(data), dex_classes(new)
                    if a != b:
                        raise SystemExit(f"error: {name}: {a} classes in the original, {b} in the rebuilt one")
                    log.append(f"{name}: taken from rebuilt ({b} classes)")
                    data = new
                elif zm and name == "AndroidManifest.xml":
                    new = zm.read(name)
                    if new[:4] != b"\x03\x00\x08\x00":
                        raise SystemExit("error: rebuilt AndroidManifest.xml is not binary XML")
                    log.append("AndroidManifest.xml: taken from rebuilt")
                    data = new
                zi = zipfile.ZipInfo(name, info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zi.create_system = info.create_system
                zw.writestr(zi, data)
    finally:
        for z in (zm, zd):
            if z:
                z.close()
    return log


def main(argv):
    args = argv[1:]
    if len(args) < 2:
        print(__doc__)
        return 2
    original, out = Path(args[0]), Path(args[1])
    manifest_from = dex_from = report = None
    dex, i = [], 2
    while i < len(args):
        a = args[i]
        if a in ("--manifest-from", "--dex-from", "--report"):
            i += 1
            v = Path(args[i])
            if a == "--manifest-from":
                manifest_from = v
            elif a == "--dex-from":
                dex_from = v
            else:
                report = v
        elif a == "--dex":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                dex.append(args[i])
                i += 1
            continue
        else:
            print("unknown argument", a)
            return 2
        i += 1
    if report:
        dex += [d for d in json.loads(report.read_text()).get("touched_dex", []) if d not in dex]
    for line in graft(original, out, manifest_from, dex_from, dex):
        print(" ", line)
    print(f"written {out} ({out.stat().st_size} bytes): original kept, {len(dex)} dex replaced, "
          f"manifest {'replaced' if manifest_from else 'kept'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
