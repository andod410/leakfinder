"""Undantag i starthandsreglerna: bra händer ska inte räknas som läckor bara för att de hamnar i en
grupp som förlorar i snitt.

En regel som "folda händer med 0 nöt-egenskaper" är bevisad för gruppen som helhet. Gruppen kan ändå
innehålla händer som är lönsamma, t.ex. trippelsuited eller dubbelsuited och sammanhängande händer.
Därför delas varje starthandsregel upp i förutbestämda undergrupper efter handens struktur:

  trippelsuited · dubbelsuited + sammanhängande · dubbelsuited + suited kung · dubbelsuited, övriga ·
  sammanhängande (enkelsuited/rainbow) · övriga

("sammanhängande" = minst fyra olika valörer inom ett spann på fem, ess räknas även som 1.)

Varje undergrupps resultat mot fold skattas med "krympning" (empirisk Bayes): med få händer dras
skattningen mot hela regelns snitt, med många händer får undergruppen tala för sig själv. Hur mycket
undergrupperna skiljer sig åt mäts i datan (DerSimonian–Laird). Säger datan att de inte skiljer sig
alls blir det inga undantag. En undergrupp vars krympta skattning är 0 eller bättre (inte sämre än att
folda) blir ett undantag: de händerna räknas inte som regelbrott, inte i fokus, uppföljningen eller
tränaren. Regelns kostnad räknas om på de undergrupper som är kvar.
"""
from __future__ import annotations

import math

import numpy as np

from .statlib import cluster_se

STRUCT = ["trippelsuited", "dubbelsuited + sammanhängande", "dubbelsuited + suited kung", "dubbelsuited, övriga",
          "sammanhängande (enkelsuited/rainbow)", "övriga"]
CONN = 4        # minst så många valörer inom fem i rad räknas som sammanhängande
MIN_OWN = 30    # färre spelade händer: undergruppen får ingen egen skattning (följer regeln)
RULE_TYPES = ("nut", "combo", "rundown")


def struct_codes(feats: np.ndarray) -> np.ndarray:
    """Undergrupp (index i STRUCT) från faktatabellens handegenskaper (kolumn 5 = antal färger med 2–3
    kort, 8 = sammanhängning 0–5, 11 = suited kung)."""
    f = np.asarray(feats)
    if not len(f):
        return np.zeros(0, np.int8)
    suited, conn, sk = f[:, 5], f[:, 8], f[:, 11] > 0
    out = np.full(len(f), 5, np.int8)
    out[(suited <= 1) & (conn >= CONN)] = 4
    out[suited == 2] = 3
    out[(suited == 2) & sk] = 2
    out[(suited == 2) & (conn >= CONN)] = 1
    out[suited >= 3] = 0
    return out


def struct_of(hole) -> str:
    from .ranges import hand_features
    f = hand_features(hole).copy()
    f[8] = round(f[8] * 5)
    return STRUCT[int(struct_codes(f[None, :])[0])]


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def shrink(x, c, code) -> dict:
    """Krympta skattningar per undergrupp. x = resultat mot fold (spelade händer), c = spelpass,
    code = undergrupp (index i STRUCT)."""
    x, c, code = np.asarray(x, float), np.asarray(c, np.int64), np.asarray(code)
    M = float(x.mean()) if len(x) else 0.0
    rows = []
    for g, name in enumerate(STRUCT):
        mk = code == g
        n = int(mk.sum())
        m = float(x[mk].mean()) if n else None
        se = cluster_se(x[mk], c[mk]) if n >= MIN_OWN else float("nan")
        rows.append({"name": name, "n": n, "mean": m, "se": se if np.isfinite(se) and se > 0 else None})
    use = [r for r in rows if r["se"] is not None]
    tau2 = 0.0
    if len(use) >= 2:
        w = np.array([1.0 / r["se"] ** 2 for r in use])
        mm = np.array([r["mean"] for r in use])
        mw = float((w * mm).sum() / w.sum())
        Q = float((w * (mm - mw) ** 2).sum())
        denom = float(w.sum() - (w ** 2).sum() / w.sum())
        tau2 = max(0.0, (Q - (len(use) - 1)) / denom) if denom > 0 else 0.0
    for r in rows:
        if r["se"] is None or tau2 <= 0:
            r["est"], r["p_pos"] = M, None
        else:
            prec = 1.0 / r["se"] ** 2 + 1.0 / tau2
            r["est"] = (r["mean"] / r["se"] ** 2 + M / tau2) / prec
            r["p_pos"] = _phi(r["est"] * math.sqrt(prec))  # chans att undergruppen är bättre än fold
        r["exempt"] = r["se"] is not None and r["est"] >= 0
    return {"rows": rows, "tau": math.sqrt(tau2), "mean": M}


def refine(rules: list, pre) -> list:
    """Lägg till undantag i reglerna om starthandsklasser. Regler där alla undergrupper blir undantag tas bort."""
    if pre is None or pre.ft is None or not len(pre):
        return rules
    from .practice import first_rows, rule_mask
    H = pre.ft.H
    codes = struct_codes(H["feats"][pre.hidx])
    first = first_rows(pre)
    played = ~np.isnan(pre.delta)
    out = []
    for r in rules:
        r.pop("except", None)
        r.pop("sub", None)
        if r["type"] not in RULE_TYPES:
            out.append(r)
            continue
        m = rule_mask({**r, "except": None}, pre) & first & played
        if m.sum() < 2 * MIN_OWN:
            out.append(r)
            continue
        s = shrink(pre.delta[m], pre.clu[m], codes[m])
        rows = [x for x in s["rows"] if x["n"]]
        exc = [x["name"] for x in rows if x["exempt"]]
        r["sub"] = [{k: x[k] for k in ("name", "n", "mean", "est", "p_pos", "exempt")} for x in rows]
        r["sub_tau"] = s["tau"]
        if exc:
            keep = [x for x in rows if not x["exempt"]]
            if not keep:
                continue  # inget kvar att folda
            r["except"] = exc
            r["cost_all"] = r.get("cost")
            r["cost"] = sum(x["n"] * x["est"] for x in keep) / sum(x["n"] for x in keep)
            short = exc[0] if len(exc) == 1 else f"{len(exc)} undantag"
            r["title"] = f"{r['title']} – utom {short}"
            r["why"] = (r.get("why", "") + f" Undantag (din data visar inte att de förlorar mot fold): {', '.join(exc)}. "
                        f"Kostnaden per brott är omräknad utan dem: {r['cost']:+.2f} bb.").strip()
        out.append(r)
    return out
