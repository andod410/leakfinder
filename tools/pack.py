"""Packa programmet till textdelar (för lagring i Claude-projektet) och packa upp igen.

  python tools/pack.py pack  <källmapp> <utmapp> <namn>   → <namn>-del1.txt, -del2.txt … (högst MAX tecken var)
  python tools/pack.py unpack <utmapp> <del1.txt> [<del2.txt> …]

Varje fil skrivs som en rad "===== FIL: sökväg (N tecken) =====" följd av innehållet. Uppackningen kontrollerar
längden, så en avkortad del upptäcks.
"""
import os
import sys

MAX = 240_000
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "privat"}  # privat/ = solverfilen, aldrig i projektet
SKIP_EXT = {".pyc", ".zip", ".png", ".db", ".pkl", ".sqlite"}


def files(root):
    for d, ds, fs in os.walk(root):
        ds[:] = sorted(x for x in ds if x not in SKIP_DIRS)
        for f in sorted(fs):
            if os.path.splitext(f)[1].lower() in SKIP_EXT:
                continue
            p = os.path.join(d, f)
            yield os.path.relpath(p, root).replace(os.sep, "/"), p


def pack(root, out, name):
    os.makedirs(out, exist_ok=True)
    parts, cur = [], []
    size = 0
    for rel, p in files(root):
        txt = open(p, encoding="utf-8", newline="").read()
        block = f"===== FIL: {rel} ({len(txt)} tecken) =====\n{txt}\n"
        if cur and size + len(block) > MAX:
            parts.append("".join(cur)); cur, size = [], 0
        cur.append(block); size += len(block)
    if cur:
        parts.append("".join(cur))
    paths = []
    for i, body in enumerate(parts, 1):
        head = f"# {name} – del {i} av {len(parts)}\n# Uppackning: python tools/pack.py unpack <mapp> <alla delar>\n\n"
        fp = os.path.join(out, f"{name}-del{i}.txt")
        open(fp, "w", encoding="utf-8", newline="").write(head + body)
        paths.append(fp)
    return paths


def unpack(out, parts):
    import re
    n = 0
    for part in parts:
        s = open(part, encoding="utf-8", newline="").read()
        for m in re.finditer(r"^===== FIL: (.+?) \((\d+) tecken\) =====\n", s, re.M):
            rel, ln = m.group(1), int(m.group(2))
            body = s[m.end():m.end() + ln]
            if len(body) != ln:
                raise SystemExit(f"Avkortad fil: {rel}")
            fp = os.path.join(out, rel)
            os.makedirs(os.path.dirname(fp) or ".", exist_ok=True)
            open(fp, "w", encoding="utf-8", newline="").write(body)
            n += 1
    return n


if __name__ == "__main__":
    if sys.argv[1] == "pack":
        print("\n".join(pack(sys.argv[2], sys.argv[3], sys.argv[4])))
    else:
        print(unpack(sys.argv[2], sys.argv[3:]), "filer")
