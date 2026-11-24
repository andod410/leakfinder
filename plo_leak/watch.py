"""Bevakad mapp: nya handhistorikfiler (t.ex. GG:s zip-filer i Hämtade filer) läses in automatiskt.

Zip-filer packas upp i minnet – du behöver aldrig packa upp dem själv, och originalfilerna lämnas
orörda. Filer som redan lästs in (samma storlek och ändringstid) hoppas över, och händer som redan
finns i databasen sparas inte igen. Zip-filer utan handhistorik och ofullständigt nedladdade filer
hoppas över.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

INTERVAL = 4  # 2.79: 10 -> 4 · sekunder mellan kontrollerna medan programmet är öppet
SETTLE = 5  # en fil som ändrats de senaste sekunderna kan fortfarande laddas ner – vänta till nästa gång

STATE = {"last": None, "new": 0, "new_since_view": 0, "error": None, "running": False, "files": 0, "note": None}
WATCH_SUFFIXES = {".zip", ".txt"}
_SEEN: dict = {}  # mapp -> {fil: (storlek, ändringstid)} som redan kontrollerats
_LOCK = threading.Lock()
ON_NEW = None  # anropas (utan argument) när kontrollen hittat nya händer – programmet uppdaterar då analysen


def settings_path(db) -> Path:
    return db.path.parent / (db.path.stem + "_installningar.json")


_SET_LOCK = threading.RLock()  # 2.87 (R8-01): sparningar får inte krocka


def _read_json(p: Path):
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if isinstance(d, dict) else None


def load_settings(db) -> dict:
    """2.87 (R8-01): faller tillbaka på senaste goda kopian (.bak) om filen är tom eller trasig."""
    p = settings_path(db)
    for cand in (p, p.with_suffix(".json.bak")):
        try:
            d = _read_json(cand)
            if d is not None:
                return d
        except (OSError, ValueError):
            continue
    return {}


def save_settings(db, **kw) -> dict:
    """2.87 (R8-01): läs–ändra–skriv under lås, skriv till en tempfil och byt atomiskt, och spara förra goda
    versionen som .bak. Tidigare kunde två samtidiga sparningar eller ett avbrott mitt i skrivningen tömma filen
    (och därmed rakeback-loggen)."""
    import os
    with _SET_LOCK:
        d = load_settings(db)
        d.update(kw)
        p = settings_path(db)
        try:
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            try:
                if p.is_file() and _read_json(p) is not None:
                    bak = p.with_suffix(".json.bak")
                    bak.write_bytes(p.read_bytes())
            except (OSError, ValueError):
                pass
            os.replace(tmp, p)
        except OSError:
            pass
    return d


def _windows_downloads() -> str:
    """Windows: mappen Hämtade filer kan vara flyttad (t.ex. till D: eller OneDrive). Den riktiga
    platsen står i registret."""
    try:
        import os
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            v, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
        return os.path.expandvars(v)
    except Exception:
        return ""


def _xdg_downloads() -> str:
    """Linux: XDG_DOWNLOAD_DIR i ~/.config/user-dirs.dirs."""
    try:
        f = Path.home() / ".config" / "user-dirs.dirs"
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("XDG_DOWNLOAD_DIR="):
                return line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(Path.home()))
    except OSError:
        pass
    return ""


def default_folder() -> str:
    """Hämtade filer på den här datorn – Windows, Mac och Linux."""
    import sys
    cand = []
    if sys.platform == "win32":
        cand.append(_windows_downloads())
    elif sys.platform.startswith("linux"):
        cand.append(_xdg_downloads())
    cand += [str(Path.home() / n) for n in ("Downloads", "Hämtade filer", "Overførsler")]
    for c in cand:
        if c and Path(c).is_dir():
            return str(Path(c))
    return ""


def _foreign(folder: str) -> bool:
    """En sökväg från ett annat operativsystem, t.ex. C:\\... på en Mac (inställningarna följde med databasen)."""
    import os
    win = len(folder) > 2 and folder[1] == ":" and folder[2] in "\\/"
    return (os.name != "nt" and (win or "\\" in folder)) or (os.name == "nt" and folder.startswith("/"))


def folder_of(settings: dict) -> str:
    """Den bevakade mappen. Har ingen mapp valts används Hämtade filer som standard;
    har bevakningen stängts av (watch = None) bevakas ingenting. En sparad mapp från en annan
    dator (Windows-sökväg på Mac eller tvärtom) ersätts av standardmappen."""
    if "watch" not in settings:
        return default_folder()
    f = settings.get("watch") or ""
    if f and _foreign(f):
        return default_folder()
    return f


def normalize(folder: str) -> str:
    """Finder visar ~/Downloads som "Hämtade filer" – skriver du det namnet (eller drar in mappen) blir
    det rätt ändå."""
    f = (folder or "").strip().strip('"').strip("'")
    if not f:
        return ""
    p = Path(f).expanduser()
    if not p.exists() and p.name.lower() in ("hämtade filer", "hamtade filer", "downloads", "overførsler"):
        d = default_folder()
        if d:
            return d
    return str(p)


def folder_problem(folder: str) -> str:
    """Kort förklaring om mappen inte går att läsa, annars tom sträng."""
    import sys
    if not folder:
        return ""
    p = Path(folder).expanduser()
    if not p.is_dir():
        return f"Mappen {folder} finns inte på den här datorn."
    try:
        next(p.iterdir(), None)
    except PermissionError:
        if sys.platform == "darwin":
            return ("macOS stoppar programmet från att läsa mappen. Öppna Systeminställningar → Integritet och "
                    "säkerhet → Filer och mappar → Terminal och slå på Hämtade filer. Starta sedan om programmet.")
        if sys.platform == "win32":
            return ("Windows stoppar programmet från att läsa mappen. Kontrollera Windows-säkerhet → Skydd mot "
                    "virus och hot → Kontrollerad mappåtkomst, och tillåt Python där. Starta sedan om programmet.")
        return "Programmet får inte läsa mappen (behörighet saknas)."
    except OSError as e:
        return f"Mappen går inte att läsa: {e}"
    return ""


def _changed(folder: Path) -> list:
    """Filer som är nya eller ändrade sedan förra kontrollen och inte längre skrivs till."""
    from .parser import _walk
    seen = _SEEN.setdefault(str(folder), {})
    now = time.time()
    out = []
    for f in _walk(folder):
        if f.suffix.lower() not in WATCH_SUFFIXES:
            continue  # bara zip- och textfiler (GG:s format) läses automatiskt
        try:
            st = f.stat()
        except OSError:
            continue
        key = (st.st_size, st.st_mtime_ns)
        if seen.get(str(f)) == key:
            continue
        if now - st.st_mtime < SETTLE:
            continue  # laddas troligen ner just nu
        out.append((f, key))
    return out


def scan(db, run_lock) -> dict | None:
    """Läs in nya filer från den bevakade mappen. Bara nya eller ändrade filer öppnas, så en
    kontroll utan nya filer tar bara en bråkdel av en sekund. Hoppar över om ett jobb pågår."""
    folder = folder_of(load_settings(db))
    prob = folder_problem(folder)
    if prob:
        with _LOCK:
            STATE.update(last=time.time(), error=prob)
        return None
    if not folder:
        return None
    root = Path(folder).expanduser()
    extra = extra_folders(load_settings(db), folder)
    if not run_lock.acquire(blocking=False):
        return None  # en analys pågår – försök igen nästa gång
    try:
        r = scan_now(db, root)
        for x in extra:  # 2.79: Hämtade filer som extra bevakad mapp (GG:s nedladdade zip/txt)
            r2 = scan_now(db, Path(x).expanduser())
            if r2:
                r = r2 if r is None else {**r, "files": r["files"] + r2["files"],
                                          "files_skipped": r["files_skipped"] + r2["files_skipped"],
                                          "hands_new": r["hands_new"] + r2["hands_new"]}
        return r
    finally:
        run_lock.release()


def extra_folders(settings: dict, main: str) -> list:
    """2.79: "Bevaka även Hämtade filer" – när en annan mapp är vald läses GG:s nedladdningar ändå in."""
    if not settings.get("watch_dl"):
        return []
    d = default_folder()
    try:
        if not d or (main and Path(d).expanduser().resolve() == Path(main).expanduser().resolve()):
            return []
    except OSError:
        return []
    return [d] if not folder_problem(d) else []


def scan_now(db, root=None) -> dict | None:
    """Läs in nya filer från den bevakade mappen direkt (anroparen håller jobblåset)."""
    if root is None:
        folder = folder_of(load_settings(db))
        if not folder or folder_problem(folder):
            return None
        root = Path(folder).expanduser()
    try:
        with _LOCK:
            STATE["running"] = True
        changed = _changed(root)
        if changed:
            # Har du redan händer i databasen läses bara händer där du själv fick kort – en fil som
            # hamnat i mappen av misstag (eller från en webbsida) kan då inte blanda in andras händer.
            hero = db.detect_hero() if db.count() else None
            r = db.add_paths([f for f, _ in changed], require_player=hero)
        else:
            r = {"files": 0, "files_skipped": 0, "hands_new": 0}
        seen = _SEEN.setdefault(str(root), {})
        partial = bool(r.get("hands_incomplete") or r.get("rejected"))
        if not partial:   # 2.81: ofullständig import -> filerna kontrolleras igen nästa gång (databasen hoppar över det klara)
            for f, key in changed:
                seen[str(f)] = key
        note = None
        if r.get("hands_incomplete"):
            note = f"{r['hands_incomplete']} hand(er) var inte färdigskrivna – läses in när filen är klar"
        if r.get("rejected"):
            note = (note + " · " if note else "") + f"{len(r['rejected'])} fil(er) i zip avvisades: {r['rejected'][0][2]}"
        with _LOCK:
            STATE.update(last=time.time(), new=r["hands_new"], files=r["files"] - r["files_skipped"], error=None, note=note)
            STATE["new_since_view"] += r["hands_new"]
        return r
    except Exception as e:  # bevakningen får aldrig stoppa programmet
        with _LOCK:
            STATE.update(last=time.time(), error=str(e))
        return None
    finally:
        with _LOCK:
            STATE["running"] = False


def start(get_db, run_lock) -> None:
    """Bakgrundstråd: kollar den bevakade mappen direkt och sedan var INTERVAL:e sekund."""
    def loop():
        time.sleep(2)
        while True:
            try:
                db = get_db()
                if load_settings(db).get("auto", True):
                    r = scan(db, run_lock)
                    if r and r.get("hands_new", 0) > 0 and ON_NEW is not None:
                        ON_NEW()
                    elif ON_NEW is not None and STATE["new_since_view"] > 0:
                        # 2.79: nya händer som inte kom med (ett jobb pågick när de lästes in, eller programmet
                        # startade med en sparad analys som saknar dem) – försök igen tills analysen har dem
                        try:
                            ON_NEW(retry=True)
                        except TypeError:
                            pass
            except Exception:
                pass
            time.sleep(INTERVAL)
    threading.Thread(target=loop, daemon=True, name="bevakad-mapp").start()


def view_opened() -> None:
    """En ny analys har öppnats: nya händer räknas från och med nu."""
    with _LOCK:
        STATE["new_since_view"] = 0
