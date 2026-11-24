"""Exportera händer i originalformatet, för import i DriveHUD, HoldemManager och liknande.

Varje hand sparas med exakt den text den hade i filen den lästes in från (GG:s handhistorik
eller DriveHUD-exporten), och händerna skrivs ut i tidsordning. Händer som lästes in av en äldre
version (innan originaltexten sparades) återskapas i GG:s format från den tolkade handen (hhwrite),
så att alla händer kommer med. Som standard delas de upp i en
fil per dag och nivå – ungefär som GG:s egna filer – och läggs i en zip-fil som DriveHUD och
HoldemManager kan läsa direkt (eller packas upp och importeras som mapp).
"""
from __future__ import annotations

import re
import time
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

import numpy as np

KEEP = 5  # så många exportfiler sparas, äldre tas bort
NAME_OK = re.compile(r"^PLO_export_[0-9_]+_\d+h\.zip$")


def export_dir(db) -> Path:
    d = db.path.parent / (db.path.stem + "_export")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clean(d: Path) -> None:
    files = sorted(d.glob("PLO_export_*.zip"), key=lambda p: p.stat().st_mtime)
    for p in files[:-KEEP]:
        try:
            p.unlink()
        except OSError:
            pass


def _safe(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z.$_-]+", "-", s).strip("-")


class _DirWriter:
    """Skriver filerna som vanliga .txt-filer i en mapp (samma gränssnitt som zip-filen)."""

    def __init__(self, folder: Path, prefix: str):
        self.folder, self.prefix, self.written = folder, prefix, []

    def writestr(self, name, data):
        p = self.folder / f"{self.prefix} {name}"
        p.write_bytes(data)
        self.written.append(p)

    def open(self, name, mode="w", force_zip64=False):
        p = self.folder / f"{self.prefix} {name}"
        self.written.append(p)
        return p.open("wb")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _rebuild(blob):
    """Handen i GG:s format, återskapad från den tolkade handen (när originaltexten saknas)."""
    from .hhwrite import to_gg_text
    if not blob:
        return None
    import pickle
    try:
        from .parser import fix_dead_sb_positions
        h = pickle.loads(zlib.decompress(blob))
        fix_dead_sb_positions(h)
        return to_gg_text(h)
    except Exception:
        return None


def write_export(db, ft, rows, split: str = "dag", progress=None, folder=None, fmt: str = "zip") -> dict:
    """Skriv händerna (rader i faktatabellen, i tidsordning). split: "dag" = en fil per dag, variant
    och nivå; "en" = alla händer i en fil. folder = mapp att spara i (annars programmets exportmapp).
    fmt: "zip" = en zip-fil, "txt" = vanliga textfiler direkt i mappen."""
    from .facts import dt_of
    H = ft.H
    rows = np.asarray(rows, dtype=np.int64)
    rows = rows[np.argsort(H["ts"][rows], kind="stable")]
    own = folder is None
    d = export_dir(db) if own else Path(folder).expanduser()
    if not own:
        d.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S_%f}"
    path = d / f"PLO_export_{stamp}_{len(rows)}h.zip"
    if fmt == "txt" and not own:
        path = d
    stats = {"hands": 0, "missing": 0, "rebuilt": 0, "files": 0, "path": path, "name": path.name,
             "first": None, "last": None, "folder": str(d), "own": own, "fmt": fmt if not own else "zip"}
    groups: dict = {}

    def name_of(j):
        day = dt_of(H["ts"][j]).strftime("%Y%m%d")
        return f"GG{day} - PLO-{int(H['nh'][j])} - ${ft.label('stake', int(H['stake'][j])).replace('/', '-$')}"

    def flush(zf):
        for key in list(groups):
            texts = groups.pop(key)
            fname = f"{_safe(key)} - {len(texts)} hands.txt"
            zf.writestr(fname, "".join(texts).encode("utf-8"))
            stats["files"] += 1

    ids = [str(x) for x in H["id"][rows]]
    out = (_DirWriter(d, f"PLO_export_{stamp}") if stats["fmt"] == "txt"
           else zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6))
    try:
        with out as zf:
            one = zf.open(f"PLO_export_{len(rows)}_hands.txt", "w", force_zip64=True) if split == "en" else None
            cur_day = None
            for a in range(0, len(rows), 500):
                chunk = ids[a:a + 500]
                q = ("SELECT id, raw, CASE WHEN raw IS NULL THEN blob END FROM hands WHERE id IN (%s)"
                     % ",".join("?" * len(chunk)))
                raw, blobs = {}, {}
                for hid, r, b in db.con.execute(q, chunk):
                    raw[hid] = r
                    if b is not None:
                        blobs[hid] = b
                for k, hid in enumerate(chunk):
                    j = int(rows[a + k])
                    r = raw.get(hid)
                    if r:
                        text = zlib.decompress(r).decode("utf-8")
                    else:
                        text = _rebuild(blobs.get(hid))  # originaltexten saknas: återskapa handen
                        if text is None:
                            stats["missing"] += 1
                            continue
                        stats["rebuilt"] += 1
                    day = dt_of(H["ts"][j]).strftime("%Y%m%d")
                    if split != "en" and cur_day is not None and day != cur_day:
                        flush(zf)  # händerna kommer i tidsordning: föregående dag är klar
                    cur_day = day
                    text = text.strip("\n") + "\n\n\n"
                    if one is not None:
                        one.write(text.encode("utf-8"))  # en enda fil skrivs direkt, utan att hållas i minnet
                    else:
                        groups.setdefault(name_of(j), []).append(text)
                    stats["hands"] += 1
                    stats["first"] = stats["first"] or dt_of(H["ts"][j]).strftime("%Y-%m-%d")
                    stats["last"] = dt_of(H["ts"][j]).strftime("%Y-%m-%d")
                if progress:
                    progress(min(a + 500, len(rows)), len(rows))
            if one is not None:
                one.close()
                stats["files"] = 1
            flush(zf)
    except BaseException:   # 2.88: avbrutet (eller fel) – ingen halvfärdig fil får ligga kvar
        try:
            if stats["fmt"] == "txt":
                for p_ in getattr(out, "written", []):
                    p_.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    if stats["fmt"] == "txt":
        stats["size_mb"] = round(sum(p.stat().st_size for p in out.written) / 1e6, 1)
        stats["files"] = len(out.written)
        stats["time"] = time.time()
        return stats
    if not stats["hands"]:
        try:
            path.unlink()
        except OSError:
            pass
        stats["path"] = None
    if own:
        _clean(d)  # bara programmets egen exportmapp städas, aldrig en mapp du valt
    stats["size_mb"] = round(path.stat().st_size / 1e6, 1) if stats["path"] else 0
    stats["time"] = time.time()
    return stats
