"""2.76: jämförelse av dina preflopbeslut mot en preflopsolver (PLO Trainer, PLO6 GG 5-max 100bb).

Solverfilen lägger du själv in (Solver-sidan → Lägg in solverfil). Den sparas i en egen mapp bredvid
databasen (`<databas>_solver/solver.json`), aldrig i programmappen, och tas aldrig med i export, delning,
djupanalys eller sessionsfiler. Programmet fungerar som vanligt utan fil.

Solverns frekvenser gäller en handgrupp (t.ex. "AA ds, 1 nötfärg"), inte en exakt hand. Resultat mot fold är
hela handens utfall (preflop + postflop) och observationella – visa riktning, inte exakt preflopkostnad.

Solver-sidan visas inte medan GG-klienten körs (eller när det inte går att kontrollera): solverfrekvenser
under spel kan räknas som otillåten realtidshjälp.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .solvergroups import ALL_NODES, CLASSIFIER_VERSION, EXTRA_NODES, NODE_LABEL, NODES, OPEN_NODES, classify, short

SOLVER_FORMAT = 1
H4_START = "2026-11-17"   # framåttest H4 räknar bara händer från detta datum
H4_TEXT = "Spel där solvern nästan aldrig gör samma sak (< 10 % i handgruppen) förlorar mot fold"
EXPECT = {"Cash", "Preflop", "5-Max", "100bb", "3.5x"}
_CACHE: dict = {}


# ------------------------------------------------------------------ fil
def solver_dir(db) -> Path:
    return db.path.parent / (db.path.stem + "_solver")


def solver_path(db) -> Path:
    return solver_dir(db) / "solver.json"


def normalize(raw: dict) -> dict:
    """Läs solverfilen och gör en tabell {nod: {(l0,), (l0,l1), (l0,l1,l2): [fold, syn, höj]}}.
    Hanterar nivåförskjutning (en nod kan börja på djup 1) och skräprader; noder med bara fold/höj får syn = 0."""
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), dict):
        raise ValueError("Filen är inte en solverfil (saknar 'nodes').")
    missing = [n for n in NODES if n not in raw["nodes"]]
    if missing:
        raise ValueError("Solverfilen saknar lägen: " + ", ".join(NODE_LABEL[n] for n in missing))
    tab = {}
    for n in NODES:
        rows = raw["nodes"][n].get("rows") or []
        if not rows:
            raise ValueError(f"Läget {NODE_LABEL[n]} är tomt i solverfilen.")
        tab[n] = _node_table(rows, n)
    return tab


def _node_table(rows, n):
    """Raderna för ett läge -> {(l0,), (l0,l1), (l0,l1,l2): [fold, syn, höj]}. Rader kan vara dict (lab, d, f) eller
    lista [lab, djup, f, vikt] (2.78)."""
    rows = [r if isinstance(r, dict) else {"lab": r[0], "d": r[1], "f": r[2]} for r in rows]
    if True:
        m0 = rows[0]["d"]
        T, l0, l1 = {}, None, None
        for r in rows:
            d = r.get("d", -1) - m0
            f = [float(x) for x in (r.get("f") or [])]
            if d < 0 or d > 2 or len(f) not in (2, 3):
                continue
            if len(f) == 2:
                f = [f[0], 0.0, f[1]]
            if abs(sum(f) - 100) > 1.0:
                continue
            if d == 0:
                l0, l1 = r["lab"], None
                T[(l0,)] = f
            elif d == 1 and l0:
                l1 = r["lab"]
                T[(l0, l1)] = f
            elif d == 2 and l0 and l1:
                T[(l0, l1, r["lab"])] = f
        if len([k for k in T if len(k) == 1]) < 12:
            raise ValueError(f"Läget {NODE_LABEL.get(n, n)} har för få handgrupper – fel filformat?")
        return T


def normalize_extra(raw: dict) -> dict:
    """2.78: de extra lägena (mot 3-bet, kallsyn, överkall, limp, 4-bet). Saknade lägen hoppas över."""
    out = {}
    for n in EXTRA_NODES:
        node = (raw.get("nodes") or {}).get(n)
        if node and node.get("rows"):
            try:
                out[n] = _node_table(node["rows"], n)
            except ValueError:
                continue
    return out


def file_hash(tab: dict) -> str:
    s = json.dumps({n: sorted((list(k), v) for k, v in T.items()) for n, T in tab.items()}, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def save_upload(db, data: bytes) -> dict:
    """Kontrollera och spara en uppladdad solverfil. Svar: info-dict (fel ger ValueError)."""
    try:
        raw = json.loads(data.decode("utf-8"))
    except Exception:
        raise ValueError("Filen gick inte att läsa som JSON.")
    tab = normalize(raw)
    p = solver_path(db)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    try:
        (p.parent / "solver_avvald").unlink()   # 2.81: en ny uppladdning häver ett tidigare avval
    except OSError:
        pass
    _CACHE.clear()
    return info(db)


def remove(db) -> None:
    try:
        solver_path(db).unlink()
    except OSError:
        pass
    try:   # 2.81: beständigt avval – den medföljande filen läggs inte in igen vid nästa sidladdning eller omstart
        solver_path(db).parent.mkdir(parents=True, exist_ok=True)
        (solver_path(db).parent / "solver_avvald").write_text("1", encoding="utf-8")
    except OSError:
        pass
    _CACHE.clear()


BUNDLED = Path(__file__).resolve().parents[1] / "privat" / "solver.json"
BUNDLED_EXTRA = Path(__file__).resolve().parents[1] / "privat" / "solver_extra.json"


def _install_bundled(db) -> None:
    """2.77.2 (Andreas 2026-11-18): solverfilen följer med i programmets mapp privat/ och läggs in automatiskt
    första gången. Mappen privat/ tas aldrig med i kodpaketet till projektet, i export eller i delning."""
    try:
        if BUNDLED.exists() and not solver_path(db).exists() and not (solver_path(db).parent / "solver_avvald").exists():
            save_upload(db, BUNDLED.read_bytes())
    except Exception:
        pass


def load(db):
    """(tabell, info) eller (None, None) om ingen fil finns. Fel i filen ger (None, {'error': ...})."""
    p = solver_path(db)
    if not p.exists():
        _install_bundled(db)
    if not p.exists():
        return None, None
    key = (str(p), p.stat().st_mtime)
    if key in _CACHE:
        return _CACHE[key]
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        tab = normalize(raw)
    except Exception as e:
        return None, {"error": str(e)}
    try:  # 2.78: extra lägen från privat/solver_extra.json (programmappen) eller <databas>_solver/solver_extra.json
        for src in (solver_dir(db) / "solver_extra.json", BUNDLED_EXTRA):
            if src.exists():
                tab.update(normalize_extra(json.loads(src.read_text(encoding="utf-8"))))
                break
    except Exception:
        pass
    st_raw = raw.get("settings") or []
    # 2.81: inställningarna kan vara en text eller en lista med ord
    settings = st_raw if isinstance(st_raw, str) else " ".join(str(x) for x in st_raw)
    warn = [x for x in EXPECT if x.lower() not in settings.lower()]
    inf = {"hash": file_hash(tab), "tree": raw.get("tree", ""), "settings": settings, "warn": warn,
           "extracted": raw.get("extracted", ""), "format": SOLVER_FORMAT, "classifier": CLASSIFIER_VERSION}
    _CACHE.clear()
    _CACHE[key] = (tab, inf)
    return tab, inf


def info(db):
    return load(db)[1]


# ------------------------------------------------------------------ uppslag
def lookup(tab: dict, node: str, c):
    """[fold, syn, höj] för handen c (från classify) i läget, med reserv till grövre nivå. Svar (f, nivå, l2)."""
    T = tab.get(node) or {}
    l0, l1, cands, _ = c
    for s in cands:
        if (l0, l1, s) in T:
            return T[(l0, l1, s)], 3, s
    if (l0, l1) in T:
        return T[(l0, l1)], 2, None
    if (l0,) in T:
        return T[(l0,)], 1, None
    return None, 0, None


def _hands_groups(ft, idx):
    """Gruppindelning för raderna idx i hands-tabellen (cachas på handens id)."""
    from .facts import decode_cards
    H = ft.H
    out = []
    cache = _CACHE.setdefault("groups", {})
    for j in idx:
        hid = H["id"][j]
        g = cache.get(hid)
        if g is None:
            g = cache[hid] = classify(decode_cards(H["hole"][j])) or False
        out.append(g)
    return out


def _cse(x, c):
    from .statlib import cluster_se
    x = np.asarray(x, float)
    if len(x) < 2:
        return float(x.mean()) if len(x) else None, None
    return float(x.mean()), float(cluster_se(x, np.asarray(c)))


def decisions(st, tab):
    """Alla första preflopbeslut i urvalet i solverlägen, med solverns frekvenser. Svar: dict med numpy-kolumner."""
    ft = st.ft
    S = ft.t.get("spn")
    X = ft.t.get("spx")
    has_s = S is not None and len(S["hidx"])
    has_x = X is not None and len(X["hidx"])
    if not has_s and not has_x:   # 2.81: extralägena får finnas utan grundlägen
        return None
    if has_s:
        keep = st.mask[S["hidx"]] if getattr(st, "mask", None) is not None else np.ones(len(S["hidx"]), bool)
        hidx, node, act, delta = S["hidx"][keep], S["node"][keep], S["act"][keep], S["delta"][keep]
    else:
        hidx, node = np.zeros(0, np.int64), np.zeros(0, np.int16)
        act, delta = np.zeros(0, np.int8), np.zeros(0, float)
    if X is not None and len(X["hidx"]):  # 2.78: extra lägen; resultat mot fold = handens all-in EV + investerat före beslutet
        kx = st.mask[X["hidx"]] if getattr(st, "mask", None) is not None else np.ones(len(X["hidx"]), bool)
        xh = X["hidx"][kx]
        xd = ft.H["ev"][xh] + X["inv"][kx]
        xd = np.where(X["act"][kx] == 0, np.nan, xd)
        # 2.81: BB mot SB-limp kan checka gratis – en jämförelse "mot fold" säger inget där, så inget delta alls
        try:
            from .solvergroups import ALL_NODES as _AN
            chk = _AN.index("F-F-F-C")
            xd = np.where(X["node"][kx] == chk, np.nan, xd)
        except ValueError:
            pass
        hidx = np.concatenate([hidx, xh])
        node = np.concatenate([node.astype(np.int16), X["node"][kx].astype(np.int16)])
        act = np.concatenate([act, X["act"][kx]])
        delta = np.concatenate([delta, xd])
    groups = _hands_groups(ft, hidx)
    n = len(hidx)
    sf = np.full((n, 3), np.nan)
    lvl = np.zeros(n, np.int8)
    lab = []
    for k in range(n):
        g = groups[k]
        if not g:
            lab.append(None)
            continue
        nd = ALL_NODES[int(node[k])]
        if nd not in tab:
            lab.append(None)
            continue
        f, lv, l2 = lookup(tab, nd, g)
        if f is not None:
            sf[k] = f
            lvl[k] = lv
        lab.append(short(g[0], g[1], l2) if f is not None else None)
    ok = ~np.isnan(sf[:, 0])
    H = ft.H
    return {"hidx": hidx[ok], "node": node[ok], "act": act[ok], "delta": delta[ok], "sf": sf[ok], "lvl": lvl[ok],
            "lab": np.asarray(lab, dtype=object)[ok], "ts": H["ts"][hidx[ok]], "clu": H["clu"][hidx[ok]],
            "excluded": int((~ok).sum())}


def compare(st, tab, hands_total: int | None = None) -> dict:
    """Allt som Solver-sidan visar."""
    from datetime import datetime
    from .facts import EPOCH, dt_of
    D = decisions(st, tab)
    if D is None or not len(D["hidx"]):
        return {"empty": True}
    N = hands_total or int(st.hands)
    act, sf, node, delta = D["act"], D["sf"], D["node"], D["delta"]
    s_act = sf[np.arange(len(act)), act]
    played = act > 0
    # 1. frekvenser per läge
    lagen = []
    for i, nd in enumerate(ALL_NODES):
        m = node == i
        if not m.any():
            continue
        du = [float((act[m] == a).mean() * 100) for a in range(3)]
        so = [float(x) for x in sf[m].mean(0)]
        lagen.append({"node": nd, "label": NODE_LABEL[nd], "n": int(m.sum()), "du": du, "sol": so, "open": nd in OPEN_NODES,
                      "diff": max(abs(du[a] - so[a]) for a in range(3))})
    # 2. avvikande spel (< 10 %) mot huvudlinjen (≥ 50 %)
    dev = played & (s_act < 10) & ~np.isnan(delta)
    main = played & (s_act >= 50) & ~np.isnan(delta)
    m_dev, se_dev = _cse(delta[dev], D["clu"][dev]) if dev.any() else (None, None)
    m_main, se_main = _cse(delta[main], D["clu"][main]) if main.any() else (None, None)
    rows = []
    for i, nd in enumerate(ALL_NODES):
        for a in (1, 2):
            m = dev & (node == i) & (act == a)
            if m.sum() < 20:
                continue
            mm, se = _cse(delta[m], D["clu"][m])
            rows.append({"label": NODE_LABEL[nd], "act": "syn" if a == 1 else ("öppning" if nd in OPEN_NODES else ("höj" if nd in EXTRA_NODES else "3-bet")),
                         "n": int(m.sum()), "mean": mm, "ci": 1.96 * se if se is not None else None,
                         "total": float(delta[m].sum()), "per100": float(100 * delta[m].sum() / N) if N else None,
                         "sol_fold": float(sf[m, 0].mean())})
    rows.sort(key=lambda r: r["total"])
    # dyraste grupper
    grp = {}
    for k in np.flatnonzero(dev):
        key = (int(node[k]), int(act[k]), D["lab"][k])
        grp.setdefault(key, []).append(k)
    groups = []
    for (i, a, lab), ks in grp.items():
        if len(ks) < 30:
            continue
        ks = np.asarray(ks)
        mm, se = _cse(delta[ks], D["clu"][ks])
        groups.append({"label": NODE_LABEL[ALL_NODES[i]], "act": "syn" if a == 1 else ("öppning" if ALL_NODES[i] in OPEN_NODES else "höj"),
                       "group": lab, "n": len(ks), "sol": [float(x) for x in sf[ks].mean(0)], "mean": mm,
                       "ci": 1.96 * se if se is not None else None, "total": float(delta[ks].sum())})
    groups.sort(key=lambda r: r["total"])
    # 3. foldade händer som solvern spelar ≥ 70 %
    mf = (act == 0) & (sf[:, 0] <= 30)
    missed = {}
    for k in np.flatnonzero(mf):
        key = (NODE_LABEL[ALL_NODES[int(node[k])]], D["lab"][k])
        missed[key] = missed.get(key, 0) + 1
    missed_rows = [{"label": a, "group": b, "n": c} for (a, b), c in sorted(missed.items(), key=lambda kv: -kv[1])[:12]]
    # 4. trend per månad
    months = {}
    for k in range(len(act)):
        mo = dt_of(int(D["ts"][k])).strftime("%Y-%m")
        months.setdefault(mo, []).append(k)
    trend = []
    for mo in sorted(months):
        ks = np.asarray(months[mo])
        trend.append({"month": mo, "n": len(ks), "dev": float(100 * dev[ks].mean()) if len(ks) else 0.0,
                      "missed": float(100 * mf[ks].mean()), "match": float(np.nanmean(s_act[ks]))})
    # 5. framåttest H4
    t0 = int((datetime.fromisoformat(H4_START) - EPOCH).total_seconds())
    after = D["ts"] >= t0
    h4m = dev & after
    h4 = {"start": H4_START, "text": H4_TEXT, "n": int(h4m.sum()), "clusters": int(len(set(D["clu"][h4m].tolist()))),
          "decisions_after": int(after.sum())}
    if h4["n"] >= 2:
        mm, se = _cse(delta[h4m], D["clu"][h4m])
        h4.update(mean=mm, ci=1.96 * se if se is not None else None)
        if h4["n"] < 100 or h4["clusters"] < 20:
            h4["verdict"] = "för få"
        elif se is not None and mm + 1.96 * se < 0:
            h4["verdict"] = "håller"
        elif se is not None and mm - 1.96 * se > 0:
            h4["verdict"] = "håller inte"
        else:
            h4["verdict"] = "oklart"
    else:
        h4.update(mean=None, ci=None, verdict="för få")
    h4["share"] = float(100 * dev[after].mean()) if after.any() else None
    return {"empty": False, "decisions": int(len(act)), "excluded": D["excluded"], "hands": N,
            "lvl3": float(100 * (D["lvl"] == 3).mean()), "lagen": lagen,
            "dev": {"n": int(dev.sum()), "mean": m_dev, "ci": 1.96 * se_dev if se_dev is not None else None,
                    "per100": float(100 * delta[dev].sum() / N) if N else None,
                    "per100_ci": float(100 * 1.96 * se_dev * dev.sum() / N) if (N and se_dev is not None) else None,
                    "share": float(100 * dev.mean())},
            "main": {"n": int(main.sum()), "mean": m_main, "ci": 1.96 * se_main if se_main is not None else None},
            "rows": rows[:10], "groups": groups[:15], "missed": {"n": int(mf.sum()), "rows": missed_rows},
            "trend": trend, "h4": h4}
