#!/usr/bin/env python3
"""
check_manifest.py <orig.txt> <new.txt>

Both files are `aapt2 dump xmltree --file AndroidManifest.xml` of the original and the patched apk.
The new manifest was compiled by aapt2, the original by the app's own build, so if a resource id ended up different
(then the grafted manifest would point at the wrong icon / theme / activity), a line of the original would be gone.
Rule: every line of the original may only be missing if it is one of the changes we make on purpose
(AD_ID permission, the launcher label). Added lines are free. Source line numbers are ignored.
"""
import re
import sys
from collections import Counter

ALLOWED_GONE = re.compile(r"AD_ID|android:label|^E: uses-permission$")


def norm(path):
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = re.sub(r"\s*\(line=\d+\)", "", line.rstrip("\n"))
        if line.strip():
            out.append(line.strip())
    return out


def main(a, b):
    old, new = Counter(norm(a)), Counter(norm(b))
    gone = [l for l in old if old[l] > new.get(l, 0) and not ALLOWED_GONE.search(l)]
    added = [l for l in new if new[l] > old.get(l, 0)]
    print(f"lines in original: {sum(old.values())}, in patched: {sum(new.values())}; "
          f"added: {len(added)}, unexpectedly gone: {len(gone)}")
    for l in added[:40]:
        print("  +", l)
    if gone:
        print("MANIFEST MISMATCH, these lines of the original are missing (resource ids may have shifted):")
        for l in gone[:40]:
            print("  -", l)
        return 1
    print("manifest check passed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
