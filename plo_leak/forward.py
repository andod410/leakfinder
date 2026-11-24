"""Framåttest (2.71): reglerna frysta 2026-11-13 prövas bara på händer spelade EFTER frysdatum.

Tidigare "holdout" delade samma databas som reglerna formades på – det ger för optimistiska resultat.
Här letas reglerna en gång i händerna före frysdatum, sparas oförändrade (fryst definition) och
mäts sedan bara på nya händer. Det är det enda testet som kan göra en regel "bekräftad".

Utfall per regel (samma kriterier som holdout.py): "håller" kräver minst 100 brott, minst 20 spelpass,
familjekorrigerat 95 %-intervall under noll och bootstrap. Alternativ-action-jämförelser (3-betta mot syna)
kan inte bekräftas av en observationsjämförelse och märks "inte oberoende".
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

FREEZE_DATE = "2026-11-13"
MIN_BEFORE = 20000


def freeze_ts() -> int:
    """Frysgränsen i handtid – samma tidsräkning som faktatabellen (facts.ts_of), oberoende av datorns tidszon.
    (Före 2.73 räknades den i datorns lokala tid och hamnade en timme fel i Sverige.)"""
    from .facts import ts_of
    return ts_of(datetime.strptime(FREEZE_DATE, "%Y-%m-%d"))


def rules_hash(doc: dict | None) -> str | None:
    """Fingeravtryck av de frysta reglernas definitioner (inte kostnader eller texter). Samma hash = samma frysta regler,
    t.ex. på Mac och PC. Sparas i nattkvittot, morgonrapporten och rules.json så att den kan jämföras med projektet."""
    import hashlib
    from .holdout import _definition
    rules = (doc or {}).get("rules") or []
    if not rules:
        return None
    try:
        defs = sorted(f"{r.get('id')}={_definition(r)}" for r in rules)
    except Exception:
        return None
    return hashlib.sha256("\n".join(defs).encode("utf-8")).hexdigest()[:16]


def rules_order_hash(doc: dict | None) -> str | None:
    """2.81: fingeravtryck som också täcker regelordningen. En hand räknas mot den FÖRSTA regel som matchar, så två
    regelsamlingar med samma definitioner i olika ordning kan ge olika tilldelning – samma rules_hash men olika
    order_hash. (rules_hash behålls oförändrad så att den frysta samlingen går att känna igen.)"""
    import hashlib
    from .holdout import _definition
    rules = (doc or {}).get("rules") or []
    if not rules:
        return None
    try:
        defs = [f"{i}:{r.get('id')}={_definition(r)}" for i, r in enumerate(rules)]
    except Exception:
        return None
    return hashlib.sha256(("violation_index-v1\n" + "\n".join(defs)).encode("utf-8")).hexdigest()[:16]


def _path(cache_dir, variant) -> Path | None:
    if cache_dir is None:
        return None
    base = Path(cache_dir).parent if Path(cache_dir).name.endswith("_resultat") else Path(cache_dir)
    return base / f"frysta_regler_{variant or 'PLO'}_{FREEZE_DATE}.json"


def _jsonable(o):
    return o.tolist() if hasattr(o, "tolist") else str(o)


def frozen_rules(st, hero, cache_dir, variant):
    """Läser de frysta reglerna, eller fryser dem nu (letas bara i händer före frysdatum)."""
    p = _path(cache_dir, variant)
    if p is not None and p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    ft = st.ft
    rows = np.asarray(st.rows, dtype=np.int64)
    before = rows[ft.H["ts"][rows] < freeze_ts()]
    if len(before) < MIN_BEFORE:
        return None
    from .aggregate import build_stats
    from .analyses import REGISTRY, Ctx
    from .holdout import DISCOVERY
    from .practice import build_rules
    mask = np.zeros(ft.n, bool)
    mask[before] = True
    st_old = build_stats(ft, mask, hero, getattr(st.hands_by_id, "_lookup", None))
    ctx = Ctx(st=st_old, hero=hero, strict=True)
    R: dict = {}
    for name in DISCOVERY:
        R[name] = REGISTRY[name]["fn"](ctx, R)
    doc = build_rules(R["ranges"], R["guide"], R["rundowns"], st_old, R.get("nut_fold"), R.get("likely") or [])
    doc = json.loads(json.dumps(doc, default=_jsonable, ensure_ascii=False))
    from . import __version__
    doc["frozen"] = {"date": FREEZE_DATE, "hands_before": int(len(before)), "version": __version__,
                     "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
    if p is not None and doc.get("rules"):  # en tom regelsamling fryses inte
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
    return doc


def forward_test(st, frozen: dict) -> dict:
    """Mäter varje fryst regel på händer efter frysdatum."""
    from .fatigue import _cluster_mean_se
    from .holdout import _verdict
    from .practice import broke_mask, first_rows, violation_index
    rules = (frozen or {}).get("rules") or []
    pre = getattr(getattr(st, "decisions", None), "pre", None)
    if not rules or pre is None or pre.ft is None or not len(pre):
        return {}
    H = pre.ft.H
    new = H["ts"][pre.hidx] >= freeze_ts()
    first = first_rows(pre) & ~np.isnan(pre.delta)
    vi = violation_index(rules, pre)
    base = first & broke_mask(rules, pre, vi) & new
    n_new = int(len(np.unique(pre.hidx[new])))
    # 2.81: fasta avläsningar vid 20/40/80 spelpass efter frysdatum (seqtest) – inte löpande på allt underlag
    from .seqtest import cohorts, next_look, pass_order, sequential
    nh = H["ts"] >= freeze_ts()
    allr = np.flatnonzero(nh)
    coh = cohorts(H["ts"][allr], H["clu"][allr])
    n_pass = len(pass_order(H["ts"][allr], H["clu"][allr]))
    out = []
    for i, r in enumerate(rules):
        mi = base & (vi == i)

        def cell(cm, fam, mi=mi):
            m = mi & cm
            n = int(m.sum())
            mean, se = _cluster_mean_se(pre.delta[m], pre.clu[m]) if n >= 2 else (float("nan"), float("nan"))
            nc = int(len(np.unique(pre.clu[m]))) if n else 0
            v = _verdict(mean, se, n, True, fam, nc)
            if v == "håller":
                from .statlib import bootstrap_t_p
                if bootstrap_t_p(pre.delta[m], pre.clu[m]) > 0.05 / fam:
                    v = "osäkert"
            return {"n": n, "clusters": nc, "mean": float(mean) if np.isfinite(mean) else None,
                    "se": float(se) if np.isfinite(se) else None, "verdict": v}
        if r.get("cmp", "fold") != "fold":
            res = cell(np.ones(len(pre), bool), len(rules))
            res["verdict"], res["look"] = "inte oberoende", None
        else:
            res = sequential(cell, pre.clu, coh, len(rules))
            if not res.get("look"):
                res.update(cell(np.zeros(len(pre), bool), len(rules)))
                res["verdict"] = "för få"
        out.append({"id": r.get("id"), "title": r.get("title"), **res})
    fz = (frozen or {}).get("frozen") or {}
    return {"date": FREEZE_DATE, "hands_after": n_new, "rules": out, "hash": rules_hash(frozen),
            "order_hash": rules_order_hash(frozen),
            "frozen_created": fz.get("created"), "frozen_version": fz.get("version"),
            "need": "minst 100 brott och 20 spelpass per regel efter frysdatum",
            "passes_after": n_pass, "looks": [20, 40, 80], "next_look": next_look(n_pass),
            "method": "2.81: avläsning bara vid 20/40/80 pass (de första K passen), felrisken delad på avläsningarna"}
