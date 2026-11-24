"""Test på nya händer: håller reglerna på händer som inte användes för att hitta dem?

Händerna delas i tid: de äldsta OLD_SHARE (två tredjedelar) och de nyaste. Programmet letar regler bara i
de äldre händerna, precis som vanligt. Sedan mäts den regel som hittades i de äldre händerna (med de
gränser och undantag som valdes där) på de nya händerna: vad har dina brott mot den gett jämfört med fold?
De nya händerna har då inte använts alls för att välja ut regeln, så måttet blir inte uppblåst av urvalet.
En regel från hela databasen som saknar motsvarighet i de äldre händerna mäts med sina egna gränser men
kan inte bli bekräftad. Sökningen i de äldre händerna sparas, så den görs om bara när nya händer kommer in.

Utfall per regel:
* "håller"       – identisk fryst regel, minst 20 sessioner, korrigerat 95 %-intervall och bootstrap stöder förlust.
* "osäkert"      – testets osäkerhet tillåter både vinst och förlust.
* "håller inte"  – korrigerat intervall visar vinst i testperioden: regeln tas bort.
* "inte oberoende" – ändrad/ny regel eller observationsjämförelse mellan olika actions.
* "för få"       – färre än MIN_NEW brott bland de nya händerna.

Kostnaden per brott blir försiktig: den som är minst negativ av den tidigare försiktiga kostnaden och
snittet på de nya händerna. Reglar som inte hittades i de äldre händerna kan inte vara "bekräftade".
"""
from __future__ import annotations

import os

import numpy as np

OLD_SHARE = 2 / 3
MIN_TOTAL = int(os.environ.get("PLO_HOLDOUT_MIN", "90000"))
MIN_NEW = 100
DISCOVERY = ("ranges", "guide", "rundowns", "nut_fold", "likely")


def _discover_old(st, hero, cache_key, cache_dir):
    import hashlib
    import pickle
    from .practice import RULES_VERSION
    ft = st.ft
    rows = np.asarray(st.rows, dtype=np.int64)
    path = None
    if cache_key and cache_dir:
        from .analyses import fingerprint, module_fingerprint  # 2.79: källkodsavtryck i stället för programversion
        fp = module_fingerprint("holdout", "practice") + "".join(fingerprint(d) for d in DISCOVERY)
        h = hashlib.sha1(f"{cache_key}|holdout-doc|{len(rows)}|{RULES_VERSION}|{fp}".encode()).hexdigest()[:24]
        path = cache_dir / f"{h}.pkl"
        if path.exists():
            try:
                return __import__("plo_leak.signcache", fromlist=["x"]).loads(path.read_bytes())
            except Exception:
                pass
    from .aggregate import build_stats
    from .analyses import REGISTRY, Ctx
    from .practice import build_rules
    order = rows[np.argsort(ft.H["ts"][rows], kind="stable")]
    target = int(len(order) * OLD_SHARE)
    # Entire sessions must lie on only one side of the split.
    boundaries = np.flatnonzero(np.diff(ft.H["clu"][order])) + 1
    k = int(boundaries[np.argmin(abs(boundaries - target))]) if len(boundaries) else target
    mask = np.zeros(ft.n, bool)
    mask[order[:k]] = True
    st_old = build_stats(ft, mask, hero, getattr(st.hands_by_id, "_lookup", None))
    ctx = Ctx(st=st_old, hero=hero, strict=True)
    R: dict = {}
    for name in DISCOVERY:
        R[name] = REGISTRY[name]["fn"](ctx, R)
    doc = build_rules(R["ranges"], R["guide"], R["rundowns"], st_old, R.get("nut_fold"), R.get("likely") or [])
    out = (doc, int(ft.H["ts"][order[k]]), k, len(order) - k)
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(__import__("plo_leak.signcache", fromlist=["x"]).dumps(out))
            import os as _os
            _os.replace(tmp, path)
        except Exception:
            pass
    return out


def _spots(r) -> tuple:
    return tuple(r.get("spots") or ())


def _definition(r):
    """Only executable rule semantics, never fitted costs or display text."""
    import json
    keys = ("type", "spot", "spots", "pos", "positions", "nut", "combo", "thr", "weights", "cut_pct",
            "num_cards", "groups", "cond", "bad_kind", "cmp", "except", "except_combo")
    d = {k: r[k] for k in keys if k in r and r[k] is not None}
    for k in ("spots", "positions", "groups", "except", "except_combo"):
        if k in d:
            d[k] = sorted(d[k])
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def _match(r, old_rules):
    signature = _definition(r)
    return next((o for o in old_rules if _definition(o) == signature), None)


def _verdict(mean, se, n, found, families=1, clusters=20):
    from statistics import NormalDist
    if not found:
        return "inte oberoende"
    if n < MIN_NEW or clusters < 20 or not np.isfinite(mean) or not np.isfinite(se):
        return "för få"
    z = NormalDist().inv_cdf(1 - 0.05 / (2 * max(families, 1)))
    if mean + z * se < 0:
        return "håller"
    if mean - z * se > 0:
        return "håller inte"
    return "osäkert"


def _same(r, old_rules) -> bool:
    return _match(r, old_rules) is not None


def validate(doc: dict, st, hero: str, cache_key=None, cache_dir=None) -> dict:
    """Lägger "holdout" på varje regel, justerar nivå och kostnad och flyttar regler som inte håller till
    doc["dropped"]. Gör inget om databasen är för liten."""
    from .fatigue import _cluster_mean_se
    from .practice import broke_mask, first_rows, violation_index
    from .threebet import strat_diff
    rules = (doc or {}).get("rules") or []
    if not rules:
        return doc
    if st is None or len(st.rows) < MIN_TOTAL or not getattr(st, "decisions", None):
        out = dict(doc)
        out["rules"] = [{**r, "level": "trolig", "holdout": {"found_old": False, "verdict": "för få",
                          "n_new": 0, "mean_new": None, "se_new": None}} for r in rules]
        return out
    old_doc, cut_ts, n_old, n_new = _discover_old(st, hero, cache_key, cache_dir)
    old_rules = old_doc.get("rules") or []
    pre = st.decisions.pre
    H = pre.ft.H
    new = H["ts"][pre.hidx] >= cut_ts
    first = first_rows(pre) & ~np.isnan(pre.delta)
    vi = violation_index(rules, pre)
    base = first & broke_mask(rules, pre, vi)
    vi_old = violation_index(old_rules, pre) if old_rules else np.full(len(pre), -1)
    base_old = first & broke_mask(old_rules, pre, vi_old) if old_rules else np.zeros(len(pre), bool)
    old_idx = {id(o): j for j, o in enumerate(old_rules)}
    keep, dropped = [], list(doc.get("dropped") or [])
    for i, r in enumerate(rules):
        o = _match(r, old_rules)
        found = o is not None
        if r.get("cmp", "fold") == "fold":
            # mät regeln som den såg ut i de äldre händerna (dess gränser/undantag), annars hela databasens
            m = (base_old & (vi_old == old_idx[id(o)]) & new) if found else (base & (vi == i) & new)
            n = int(m.sum())
            mean, se = _cluster_mean_se(pre.delta[m], pre.clu[m]) if n >= 2 else (float("nan"), float("nan"))
            bad = mean < 0          # brotten förlorar = regeln håller
        else:
            mean, se, n = strat_diff(pre, new)
            bad = mean > 0          # 3-bet bättre än syn = regeln håller
            mean = -mean            # visas som kostnad per brott (negativ = brott kostar)
        nc = int(len(np.unique(pre.clu[m]))) if r.get("cmp", "fold") == "fold" else 0
        verdict = _verdict(mean, se, n, found, len(rules), nc)
        # Alternative-action contrasts have selection bias; do not promote them to confirmed.
        if r.get("cmp", "fold") != "fold":
            verdict = "inte oberoende"
        if verdict == "håller":
            from .statlib import bootstrap_t_p
            if bootstrap_t_p(pre.delta[m], pre.clu[m]) > 0.05 / max(len(rules), 1):
                verdict = "osäkert"
        r = dict(r)
        if verdict != "håller":
            r["why"] = "Oberoende holdout: " + verdict + ". Historiskt underlag: " + r.get("why", "")
        r["holdout"] = {"found_old": found, "n_new": n, "mean_new": float(mean) if np.isfinite(mean) else None,
                        "se_new": float(se) if np.isfinite(se) else None, "verdict": verdict, "clusters": nc,
                        "definition_frozen": found, "family_tests": len(rules)}
        if verdict == "håller inte":
            dropped.append({"id": r["id"], "title": r["title"], "n": n, "mean": float(mean), "se": float(se),
                            "reason": "höll inte på nya händer"})
            continue
        c = float(r.get("careful", r.get("cost") or 0.0))
        if verdict == "håller":
            c = max(c, min(float(mean), 0.0))
        else:
            c = 0.0  # uncertain historical costs are not a demonstrated recoverable gain
        r["careful"] = c
        if not found or verdict != "håller":
            r["level"] = "trolig"
        keep.append(r)
    out = dict(doc)
    out["rules"] = keep
    out["dropped"] = dropped
    from .facts import dt_of
    out["holdout"] = {"cut": dt_of(cut_ts).strftime("%Y-%m-%d"), "n_old": n_old, "n_new": n_new,
                      "old_found": [o["title"] for o in old_rules]}
    return out
