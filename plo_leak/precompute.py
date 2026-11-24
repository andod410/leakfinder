"""Färdiga urval på disk och förberäkning i bakgrunden (2.79).

1. Urvalscache: en färdig analys (mallvariablerna C) sparas på disk per urval. Nyckeln innehåller allt som kan påverka
   innehållet: faktabutikens signatur, urvalet, spelaren, läget (Visa urvalet / snabb / full), sparade regler och
   frysta regler (filernas innehåll), modellsignaturen för varianten, sessionsgränsen, databasinfo och ett
   fingeravtryck av hela programmets källkod. Bara analyser som inte sparar något (regler sparas bara vid full analys
   av hela varianten) läggs i cachen – en träff ger därför exakt samma sida som en ny beräkning. Faktatabellen sparas
   inte i filen; den som redan finns i minnet kopplas in vid läsning.

2. Kön: när en analys är klar startar `schedule()` en bakgrundsprocess per kärna utom en (lägsta prioritet) som räknar
   de vanligaste urvalen i ordning efter sannolikhet:
     a) "Visa urvalet" för huvudvarianten (alla nivåer), varje nivå inom den (flest händer först), vanliga bord,
        Rush & Cash, senaste 15 000, därefter övriga varianter (och deras nivåer);
     b) analysresultaten för full analys per variant (bara de sparade analysresultaten värms – regler och
        modellsignatur skrivs inte, så inget av det du ser ändras av att kön har körts).
   `cancel()` stoppar kön direkt (webben anropar den när du startar något); kön startas om efter nästa analys och
   hoppar då över allt som redan finns på disk.
"""
from __future__ import annotations

import hashlib
import io
import os
import pickle
import threading
import time
import uuid
from pathlib import Path

CTX_DIR = "urval"
KEEP = 40             # högst så många sparade urval …
MAX_BYTES = 1_500_000_000  # … och högst 1,5 GB (äldsta tas bort först)
LATEST_N = 15000

_LOAD = threading.local()


# ---------------------------------------------------------------- urvalscachen
def _file_hash(p) -> str:
    try:
        return hashlib.sha1(Path(p).read_bytes()).hexdigest()[:16]
    except OSError:
        return "-"


def _env_sig(cache_dir, variants) -> str:
    """Filer utanför databasen som påverkar sidan: sparade regler, frysta regler, sessionsgräns."""
    from .forward import _path as frozen_path
    from .practice import rules_path
    from .report import _session_limit
    parts = []
    for v in [None] + sorted(set(variants)):
        parts.append(_file_hash(rules_path(v)))
        parts.append(_file_hash(frozen_path(cache_dir, v)) if v else "")
    parts.append(repr(_session_limit()))
    return "|".join(parts)


def context_key(*, data_sig, sel_key, hero, variants, cache_dir, flags: dict, stored, db_info) -> str:
    from .analyses import module_fingerprint
    code = module_fingerprint(*_all_modules())
    st = None if not stored else (stored.get("sig"), stored.get("n"),
                                  stored.get("date") if flags.get("use_quick") else None)
    raw = repr((code, data_sig, sel_key, hero, sorted(flags.items()), st, db_info, _env_sig(cache_dir, variants)))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _all_modules():
    pkg = Path(__file__).resolve().parent
    return tuple(sorted(p.stem for p in pkg.glob("*.py")))


class _Pickler(pickle.Pickler):
    def __init__(self, f, ft):
        super().__init__(f, protocol=pickle.HIGHEST_PROTOCOL)
        self._ft = ft

    def persistent_id(self, obj):
        return "FT" if obj is self._ft else None

    def reducer_override(self, obj):
        from .aggregate import LazyHands
        if type(obj) is LazyHands:
            return _lazy, (obj.__getstate__(),)
        return NotImplemented


class _Unpickler(pickle.Unpickler):
    def __init__(self, f, ft):
        super().__init__(f)
        self._ft = ft

    def persistent_load(self, pid):
        if pid == "FT":
            return self._ft
        raise pickle.UnpicklingError(pid)


def _lazy(state):
    from .aggregate import LazyHands
    o = LazyHands.__new__(LazyHands)
    o.__dict__.update(state)
    o._lookup = getattr(_LOAD, "lookup", None)
    o._cache = {}
    return o


def _ctx_path(cache_dir, key) -> Path:
    return Path(cache_dir) / CTX_DIR / f"{key}.pkl"


def has_context(cache_dir, key) -> bool:
    return _ctx_path(cache_dir, key).exists()


def load_context(cache_dir, key, ft, lookup):
    p = _ctx_path(cache_dir, key)
    if not p.exists():
        return None
    try:
        _LOAD.lookup = lookup
        from .signcache import verify
        data = verify(p.read_bytes())   # 2.81: bara signerade filer läses
        if data is None:
            return None
        C = _Unpickler(io.BytesIO(data), ft).load()
    except Exception:
        return None
    finally:
        _LOAD.lookup = None
    try:
        os.utime(p)  # nyligen använd: tas bort sist
    except OSError:
        pass
    return C


def save_context(cache_dir, key, C, ft) -> None:
    p = _ctx_path(cache_dir, key)
    try:
        buf = io.BytesIO()
        _Pickler(buf, ft).dump(C)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{uuid.uuid4().hex[:8]}.tmp")
        from .signcache import sign
        tmp.write_bytes(sign(buf.getvalue()))   # 2.81: signerad
        os.replace(tmp, p)
        files = sorted(p.parent.glob("*.pkl"), key=lambda f: f.stat().st_mtime, reverse=True)
        total = 0
        for i, f in enumerate(files):
            total += f.stat().st_size
            if i >= KEEP or (total > MAX_BYTES and i > 0):
                f.unlink(missing_ok=True)
    except Exception:
        pass  # cachen får aldrig stoppa en analys


# ---------------------------------------------------------------- kön
def plan(ft, hero: str | None = None) -> list:
    """Urvalen i ordning efter hur troligt det är att du byter till dem. (läge, urvalsfält)"""
    import numpy as np
    from collections import Counter
    from .selection import TABLE_CODES
    H = ft.H
    if not ft.n:
        return []
    games = Counter(int(x) for x in H["nh"].tolist())
    order = [g for g, _ in games.most_common()]
    out = []
    for i, g in enumerate(order):
        name = f"PLO{g}"
        gm = H["nh"] == g
        out.append(("view", {"games": (name,)}))
        stakes = Counter(H["stake"][gm].tolist())
        if len(stakes) > 1:
            for k, _ in stakes.most_common():
                out.append(("view", {"games": (name,), "stake": ft.label("stake", int(k))}))
        if i == 0:
            tt = set(np.unique(H["ttype"][gm]).tolist())
            for t in ("vanliga", "rush"):
                if TABLE_CODES.get(t) in tt and len(tt) > 1:
                    out.append(("view", {"games": (name,), "table": t}))
            if int(gm.sum()) > LATEST_N:
                out.append(("view", {"games": (name,), "latest": LATEST_N}))
    for g in order:
        out.append(("warm", {"games": (f"PLO{g}",)}))
    return out


_STATE = {"pool": None, "thread": None, "gen": 0, "done": 0, "total": 0, "running": False, "finished": False}
_SLOCK = threading.Lock()


def status() -> dict:
    with _SLOCK:
        return {k: _STATE[k] for k in ("done", "total", "running", "finished")}


def cancel() -> None:
    """Stoppa kön direkt (påbörjade beräkningar kastas, inget halvfärdigt sparas)."""
    with _SLOCK:
        _STATE["gen"] += 1
        pool, _STATE["pool"] = _STATE["pool"], None
        _STATE["running"] = False
    if pool is not None:
        try:
            pool.terminate()
        except Exception:
            pass


def workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


def schedule(db_path, hero: str, hero_given: bool = False, delay: float = 2.0) -> None:
    """Starta kön i bakgrunden (efter en analys). Ersätter en kö som redan går."""
    cancel()
    with _SLOCK:
        gen = _STATE["gen"]
        _STATE.update(done=0, total=0, finished=False)
    t = threading.Thread(target=_drive, args=(gen, str(db_path), hero, bool(hero_given), delay), daemon=True,
                         name="forberakning")
    with _SLOCK:
        _STATE["thread"] = t
    t.start()


def _drive(gen, db_path, hero, hero_given, delay):
    try:
        _drive2(gen, db_path, hero, hero_given, delay)
    except Exception:
        pass
    finally:
        with _SLOCK:
            if gen == _STATE["gen"]:
                _STATE.update(pool=None, running=False, finished=True)


def _drive2(gen, db_path, hero, hero_given, delay):
    import multiprocessing as mp
    time.sleep(delay)
    from .db import HandDB
    try:
        db = HandDB(db_path)
        ft = db.facts(hero).load()
        tasks = plan(ft, hero)
        del ft
        db.con.close()
    except Exception:
        return
    with _SLOCK:
        if gen != _STATE["gen"]:
            return
        pool = mp.get_context("spawn").Pool(min(workers(), max(len(tasks), 1)), initializer=_init,
                                             initargs=(db_path, hero))
        _STATE.update(pool=pool, done=0, total=len(tasks), running=True)
    for _ in pool.imap(_work, [(t, hero_given) for t in tasks]):
        with _SLOCK:
            if gen != _STATE["gen"]:
                return
            _STATE["done"] += 1
    pool.close()


def _low_priority() -> None:
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x40)  # IDLE_PRIORITY_CLASS
        else:
            os.nice(19)
    except Exception:
        pass


_W: dict = {}


def _init(db_path, hero):
    _low_priority()
    _W.update(db_path=db_path, hero=hero)


def _worker_data():
    from .db import HandDB, set_active
    if "db" not in _W:
        _W["db"] = HandDB(_W["db_path"])
        set_active(None)
    db = _W["db"]
    store = db.facts(_W["hero"])
    sig = store.signature()
    if _W.get("sig") != sig:
        _W.update(sig=sig, ft=store.load())
    return db, _W["ft"], sig


def _work(arg):
    (kind, fields), hero_given = arg
    try:
        from .pipeline import build, warm_full
        from .selection import Selection
        db, ft, sig = _worker_data()
        hero = _W["hero"]
        cache_dir = db.path.parent / (db.path.stem + "_resultat")
        sel = Selection(**fields)
        if kind == "warm":
            warm_full(ft, hero, db.get_hand, sel, data_sig=sig, cache_dir=cache_dir)
            return True
        a_, b_ = db.span()
        db_info = {"count": db.count(), "first": a_, "last": b_}
        build(ft, hero, db.get_hand, sel, use_db=True, hero_given=hero_given, imports=[], db_info=db_info,
              data_sig=sig, cache_dir=cache_dir, as_context=True, view=True)
        return True
    except Exception:
        return False
