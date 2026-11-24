"""Framåttest av postflop-riktlinjerna (2.72).

Varje riktlinje är omskriven till *situation + rekommenderad handling*. Testet använder bara händer spelade efter
frysdatumet (forward.FREEZE_DATE) – riktlinjerna formulerades på äldre händer, så de nya händerna har inte använts för att
välja ut dem.

För varje riktlinje räknas:
* tillfällen (situationen inträffade och du gjorde en av de jämförda handlingarna),
* hur ofta du följde rekommendationen (beteende – det du styr över),
* resultat räknat från beslutet i andel av potten (from_here_pot) när du följde mot när du inte följde,
  med felmarginal klustrad per spelpass och Bonferroni över alla riktlinjer.

OBS: jämförelsen mellan två handlingar är observationell – du väljer själv när du följer. "håller framåt" betyder att
riktningen håller på nya händer, inte att effekten är kausalt bevisad. Därför blir ingen riktlinje "bekräftad" här.
"""
from __future__ import annotations

import numpy as np

MIN_ARM = 30        # minst så många beslut i varje arm (följde / följde inte)
MIN_CLUSTERS = 20


def _f(r, k):
    v = r.get(k)
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


def _hu(r):
    return int(r.get("players") or 0) == 2


def _need(r):
    fp = _f(r, "facing_pct")
    return fp / (100 + fp) if fp is not None else None


def _draw(r):
    so = _f(r, "straight_outs") or 0
    return bool(r.get("flush_draw")) or so >= 8


def _conn(r):
    return (r.get("board_type") or "") in ("lågt sammanhängande", "högt sammanhängande") or (_f(r, "straight_outs") or 0) >= 4


def _fold_group(r):
    mf, hand = _f(r, "made_frac"), r.get("hand") or ""
    paired = str(r.get("board_paired") or "0") in ("1", "1.0", "True")
    return mf is not None and ((hand == "kåk" and mf > 0.16) or (hand == "färg" and paired) or (hand == "två par" and not paired))


# (nr, guideline-id, kort text, situation(r) -> bool, rekommenderad(r) -> bool)
SPECS = [
    ("#1", "pf_river_bluff", "River HU, luft, ingen bet framför: betta",
     lambda r: r["street"] == "river" and r["facing"] == "ingen" and _hu(r) and (_f(r, "beat_frac") or 0) > 0.6
     and r["action"] in ("check", "bet"),
     lambda r: r["action"] == "bet"),
    ("#2", "pf_flop_raise_medium", "Flop HU mot bet, medelstark hand: höj",
     lambda r: r["street"] == "flop" and r["facing"] == "bet" and _hu(r) and str(r.get("facing_allin")) in ("0", "0.0")
     and _f(r, "made_frac") is not None and 0.10 <= _f(r, "made_frac") <= 0.35 and r["action"] in ("call", "raise"),
     lambda r: r["action"] == "raise"),
    ("#3", "pf_pfa_oop_bet", "Höjare ur position, stark hand på floppen: betta",
     lambda r: r["street"] == "flop" and r["facing"] == "ingen" and int(r.get("pfa") or 0) == 1 and int(r.get("ip") or 0) == 0
     and _f(r, "made_frac") is not None and 0.03 <= _f(r, "made_frac") <= 0.25 and r["action"] in ("check", "bet"),
     lambda r: r["action"] == "bet"),
    ("#4", "pf_turn_after_check", "Turn efter checkad flop, svag hand: betta",
     lambda r: r["street"] == "turn" and r["facing"] == "ingen" and r.get("prev_aggressor") == "ingen"
     and (_f(r, "made_frac") or 0) > 0.45 and r["action"] in ("check", "bet"),
     lambda r: r["action"] == "bet"),
    ("#5", "pf_allin_draw_call", "Drag mot all-in, krav ≤ 34 %: syna",
     lambda r: r["street"] in ("flop", "turn") and r["facing"] != "ingen" and str(r.get("facing_allin")) in ("1", "1.0")
     and _draw(r) and _need(r) is not None and _need(r) <= 0.34 and r["action"] in ("call", "fold"),
     lambda r: r["action"] == "call"),
    ("#6", "pf_cbet_ip", "C-bet HU som preflop-höjare: betta",
     lambda r: r["street"] == "flop" and r["facing"] == "ingen" and int(r.get("pfa") or 0) == 1 and _hu(r)
     and r["action"] in ("check", "bet"),
     lambda r: r["action"] == "bet"),
    ("#8", "pf_river_mw_bluff", "River multiway, luft: bluffa ibland",
     lambda r: r["street"] == "river" and r["facing"] == "ingen" and not _hu(r) and (_f(r, "beat_frac") or 0) > 0.6
     and r["action"] in ("check", "bet"),
     lambda r: r["action"] == "bet"),
    ("#9", "pf_river_nuts_ip", "River i position, högst 10 % slår dig: betta",
     lambda r: r["street"] == "river" and r["facing"] == "ingen" and int(r.get("ip") or 0) == 1
     and _f(r, "beat_frac") is not None and _f(r, "beat_frac") <= 0.10 and r["action"] in ("check", "bet"),
     lambda r: r["action"] == "bet"),
    ("#11", "pf_river_bigbet_call", "River mot ≥ ⅔ pott med kåk > 16 %/färg parat/två par oparat: folda (förregistrerad)",
     lambda r: r["street"] == "river" and r["facing"] in ("bet", "raise") and (_f(r, "facing_size_pct") or 0) >= 66
     and _fold_group(r) and r["action"] in ("call", "fold"),
     lambda r: r["action"] == "fold"),
    ("#13", "set_cr", "Set mot bet efter din check: check-raisa (bottenset: bara med stege möjlig)",
     lambda r: r["street"] == "flop" and r["facing"] == "bet" and int(r.get("order") or 1) >= 2 and bool(r.get("set_rank"))
     and r["action"] in ("call", "raise"),
     lambda r: (r["action"] == "raise") == (r.get("set_rank") in ("topp", "mellan") or _conn(r))),
    ("#14", "cbet_size", "C-bet med par + drag eller på högt bord: 70 %+",
     lambda r: r["street"] == "flop" and r["facing"] == "ingen" and int(r.get("pfa") or 0) == 1 and r["action"] == "bet"
     and _f(r, "size_pct") is not None
     and ((r.get("hand") == "par" and _draw(r)) or ((r.get("board_type") or "").startswith("högt") and r.get("hand") != "högt kort")),
     lambda r: (_f(r, "size_pct") or 0) >= 70),
]


def _cluster_diff(y, g, c):
    """Medelskillnad (g=1 minus g=0) med kluster-robust felmarginal (regression på en dummy, kluster = spelpass)."""
    y, g = np.asarray(y, float), np.asarray(g, float)
    X = np.column_stack([np.ones_like(g), g])
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    _, inv = np.unique(c, return_inverse=True)
    k = inv.max() + 1
    S = np.column_stack([np.bincount(inv, weights=X[:, j] * e, minlength=k) for j in range(2)])
    V = XtX_inv @ (S.T @ S) @ XtX_inv * (k / max(k - 1, 1))
    return float(b[1]), float(np.sqrt(max(V[1, 1], 0.0))), int(k)


def evaluate(rows: list, clusters: list) -> list:
    """rows = postflop-rader som dict (med 'from_here_pot'), clusters = spelpass per rad."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - 0.05 / (2 * len(SPECS)))
    out = []
    for nr, gid, text, sit, rec in SPECS:
        idx = [i for i, r in enumerate(rows) if _safe(sit, r)]
        fol = np.array([bool(_safe(rec, rows[i])) for i in idx], bool)
        y = np.array([_f(rows[i], "from_here_pot") for i in idx], dtype=float)
        ok = np.isfinite(y)
        n, nf = len(idx), int(fol.sum())
        res = {"nr": nr, "id": gid, "text": text, "n": n, "followed": nf,
               "follow_pct": 100.0 * nf / n if n else None, "diff": None, "se": None, "clusters": 0}
        cl = np.array([clusters[i] for i in idx])
        if n and ok.sum() >= 2 and 0 < fol[ok].sum() < ok.sum():
            d, se, k = _cluster_diff(y[ok], fol[ok], cl[ok])
            res.update(diff=d, se=se, clusters=k)
        # 2.73: minimiantalet gäller samma observationer som analysen (bara beslut med känt utfall)
        nf_ok, nd_ok = int(fol[ok].sum()), int((~fol[ok]).sum())
        res.update(n_used=int(ok.sum()))
        if min(nf_ok, nd_ok) < MIN_ARM or res["clusters"] < MIN_CLUSTERS or res["se"] is None or not np.isfinite(res["se"]):
            v = "för få"
        elif res["diff"] - z * res["se"] > 0:
            v = "håller framåt"
        elif res["diff"] + z * res["se"] < 0:
            v = "håller inte"
        else:
            v = "osäkert"
        res["verdict"] = v
        out.append(res)
    return out


SPECS_FROZEN = "2026-11-14"   # definitionerna nedan låstes med 2.73 (oförändrade sedan 2.72, 2026-11-14)
SPECS_FROZEN_HASH = "eee8fd8d3da53304"


def specs_hash() -> str:
    """Fingeravtryck av riktlinjernas definitioner (källtexten i SPECS). Ändras en definition ändras hashen – då är händer
    som redan setts inte längre ett oberoende test för den riktlinjen."""
    import hashlib
    import inspect
    import sys
    src = inspect.getsource(sys.modules[__name__])
    a, b = src.index("def _f("), src.index("SPECS_FROZEN = ")
    return hashlib.sha256(" ".join(src[a:b].split()).encode("utf-8")).hexdigest()[:16]


def _safe(fn, r):
    try:
        return fn(r)
    except Exception:
        return False


def _row_cache_path(cache_dir, hero: str):
    """2.79: radcache per hand (raderna beror bara på handen, hero och handens EV). Filnamnet bär ett källkodsavtryck
    av raderna och parsern, så den kastas automatiskt när beräkningen ändras."""
    if cache_dir is None:
        return None
    import hashlib
    from pathlib import Path
    from .analyses import module_fingerprint
    from .parser import PARSER_VERSION
    fp = hashlib.sha1(f"{module_fingerprint('postflop_rows', 'parser')}|P{PARSER_VERSION}|{hero}".encode()).hexdigest()[:20]
    return Path(cache_dir) / f"pfrows_{fp}.pkl"


def _load_row_cache(path) -> dict:
    import pickle
    try:
        return __import__("plo_leak.signcache", fromlist=["x"]).loads(path.read_bytes()) if path is not None and path.exists() else {}
    except Exception:
        return {}


def _save_row_cache(path, d: dict) -> None:
    import os
    import pickle
    import uuid
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_bytes(__import__("plo_leak.signcache", fromlist=["x"]).dumps(d))
        os.replace(tmp, path)
    except Exception:
        pass


PAR_MIN = 300       # 2.79: så många nya händer innan raderna räknas i flera processer
_WARM: dict = {}    # 2.79: cache-fil -> tråd som räknar rader i förväg (analyses.run startar den)


def _rows_worker(args):
    """Arbetsprocess: rader för en del av händerna. Handen läses från databasen exakt som HandDB.get_hand."""
    import sqlite3
    from .db import hand_from_row
    from .postflop_rows import rows_for_hand
    dbpath, hero, items = args
    con = sqlite3.connect(dbpath, timeout=30)
    out = {}
    try:
        for hid, ev in items:
            h = hand_from_row(con.execute("SELECT blob, raw FROM hands WHERE id=?", (hid,)).fetchone())
            if h is None:
                continue
            try:
                xs = rows_for_hand(h, hero, ev, draws=False)
            except Exception:
                xs = None
            out[hid] = (ev, xs)
    finally:
        con.close()
    return out


def _db_path_of(st):
    hb = getattr(st, "hands_by_id", None)
    lk = getattr(hb, "_lookup", None)
    owner = getattr(lk, "__self__", None)
    p = getattr(owner, "path", None)
    return str(p) if p is not None and getattr(lk, "__name__", "") == "get_hand" else None


def _missing(st, rc, cut):
    H = st.ft.H
    r = np.asarray(st.rows, dtype=np.int64)
    r = r[H["ts"][r] >= cut]
    out = []
    for j in r.tolist():
        hid = str(H["id"][j])
        ev = float(H["ev"][j])
        hit = rc.get(hid)
        if hit is not None and (hit[0] == ev or (hit[0] != hit[0] and ev != ev)):
            continue
        out.append((hid, ev))
    return out


def _parallel_rows(dbpath, hero, items) -> dict:
    """Rader för många händer i alla kärnor utom en. Varje hand räknas för sig (egen slumpfrö per bord),
    så resultatet är detsamma som när de räknas en i taget."""
    import multiprocessing as mp
    from .night import cpu_procs
    n = cpu_procs()
    if n <= 1 or len(items) < PAR_MIN:
        return _rows_worker((dbpath, hero, items))
    size = max(100, -(-len(items) // (n * 4)))
    chunks = [(dbpath, hero, items[k:k + size]) for k in range(0, len(items), size)]
    out = {}
    with mp.get_context("spawn").Pool(min(n, len(chunks))) as pool:
        for d in pool.imap(_rows_worker, chunks):
            out.update(d)
    return out


def warm_rows(st, hero: str, cache_dir) -> None:
    """2.79: starta radberäkningen i bakgrunden (flera processer) medan de andra analyserna körs."""
    import threading
    from .forward import freeze_ts as _fts
    cpath = _row_cache_path(cache_dir, hero)
    dbpath = _db_path_of(st)
    if cpath is None or dbpath is None or getattr(st, "ft", None) is None or st.rows is None or str(cpath) in _WARM:
        return
    from .night import cpu_procs
    if cpu_procs() < 2:   # en kärna över: en tråd här skulle bara trängas med analyserna
        return
    rc = _load_row_cache(cpath)
    items = _missing(st, rc, _fts())
    if len(items) < PAR_MIN:
        return

    def job():
        try:
            rc.update(_parallel_rows(dbpath, hero, items))
            _save_row_cache(cpath, rc)
        except Exception:
            pass
    t = threading.Thread(target=job, daemon=True, name="pf-rader")
    _WARM[str(cpath)] = t
    t.start()


def forward_postflop(st, hero: str, freeze_ts: int | None = None, cache_dir=None) -> dict:
    """Riktlinjerna mätta på händer efter frysdatum (rader räknas för just de händerna).
    cache_dir: raderna per hand sparas där, så att bara nya händer räknas när analysen görs om."""
    from .forward import FREEZE_DATE, freeze_ts as _fts
    from .postflop_rows import HEADER, rows_for_hand
    ft = getattr(st, "ft", None)
    if ft is None or st.rows is None:
        return {}
    cut = _fts() if freeze_ts is None else freeze_ts
    H = ft.H
    r = np.asarray(st.rows, dtype=np.int64)
    r = r[H["ts"][r] >= cut]
    cpath = _row_cache_path(cache_dir, hero)
    w = _WARM.pop(str(cpath), None) if cpath is not None else None
    if w is not None:
        w.join()
    rc = _load_row_cache(cpath)
    dirty = False
    dbpath = _db_path_of(st)
    if dbpath is not None:
        items = _missing(st, rc, cut)
        from .night import cpu_procs
        if len(items) >= PAR_MIN and cpu_procs() >= 2:
            try:
                rc.update(_parallel_rows(dbpath, hero, items))
                dirty = True
            except Exception:
                pass
    rows, clus = [], []
    for j in r.tolist():
        hid = str(H["id"][j])
        ev = float(H["ev"][j])
        hit = rc.get(hid)
        if hit is not None and (hit[0] == ev or (hit[0] != hit[0] and ev != ev)):
            xs = hit[1]
        else:
            h = st.hands_by_id.get(hid) if getattr(st, "hands_by_id", None) is not None else None
            if h is None:
                continue
            try:
                xs = rows_for_hand(h, hero, ev, draws=False)
            except Exception:
                xs = None
            rc[hid] = (ev, xs)
            dirty = True
        if xs is None:
            continue
        c = int(H["clu"][j])
        for x in xs:
            rows.append(dict(zip(HEADER, x)))
            clus.append(c)
    if cpath is not None and dirty:
        _save_row_cache(cpath, rc)
    hsh = specs_hash()
    return {"date": FREEZE_DATE, "hands": int(len(r)), "decisions": len(rows), "rules": evaluate(rows, clus),
            "hash": hsh, "hash_ok": hsh == SPECS_FROZEN_HASH, "specs_frozen": SPECS_FROZEN,
            "note": "observationellt: du väljer själv när du följer – riktningen prövas framåt, effekten är inte kausalt bevisad"}
