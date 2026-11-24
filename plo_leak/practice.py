"""Följ upp och träna: gör analysens säkra slutsatser till regler du kan följa.

Reglerna bygger bara på det programmet bekräftat (samma stränga krav som i rapporten):
* "För brett" i range-gränserna  -> spela bara händer inom gränsen i den situationen.
* "Folda" i öppningsguiden        -> öppna inte den kombinationen av nöt-egenskaper.
* Rundowns som förlorar klart     -> spela inte rena rundowns med de lägsta korten.

Reglerna tas fram när hela databasen analyseras och sparas, så att uppföljningen och
träningen fungerar även när du bara analyserar de senaste händerna.
"""
from __future__ import annotations

import json
import os
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from .cards import NUT_LABELS, card_str, nut_combo_label, nut_qualities
from .ranges import hand_features
from .rundowns import FIRST_SPOTS, GROUPS, group_of, rundown_low

SPOT_TEXT = {"rfi": "öppna bara", "bb_mot_hojning": "försvara mot öppning bara med",
             "sb_mot_hojning": "spela mot öppning bara med", "mot_hojning": "spela mot öppning bara med",
             "mot_3bet_ip": "fortsätt mot 3-bet (i position) bara med", "mot_3bet_oop": "fortsätt mot 3-bet (ur position) bara med"}
COMBO_TEXT = {"ingen": "händer utan nöt-egenskaper"}


def rules_path(variant: str | None = None) -> Path:
    """En regelfil per variant (PLO4/PLO5/PLO6) – reglerna gäller bara den variant de togs fram för."""
    d = Path(os.environ.get("PLO_LEAK_CACHE", Path.home() / ".plo_leak_cache"))
    d.mkdir(parents=True, exist_ok=True)
    if variant not in (None, "PLO4", "PLO5", "PLO6"):
        variant = None  # bara kända varianter blir filnamn
    return d / (f"regler_{variant}.json" if variant else "regler.json")


def rule_variants() -> list:
    d = rules_path().parent
    out = sorted(p.stem.split("_", 1)[1] for p in d.glob("regler_PLO*.json"))
    if not out and (d / "regler.json").exists():  # från version 1.24–1.26 (före regler per variant)
        out = [None]
    return out


# ---------------------------------------------------------------- skapa regler
def build_rules(ranges, guide, rundowns, st, nut_fold=None, likely=None) -> dict:
    rules = []
    for r in ranges or []:
        if r["verdict"]["kind"] != "wide" or r.get("score_thr") is None:
            continue
        rules.append({
            "id": f"cut|{r['spot']}|{r['pos']}", "type": "cutoff", "spot": r["spot"], "pos": r["pos"],
            "thr": r["score_thr"], "weights": list(r["weights"].values()), "cut_pct": r["cutoff_pct"],
            "num_cards": r.get("num_cards", 6), "cost": r["test"]["mean"],
            "title": f"{r['pos']}: {SPOT_TEXT.get(r['spot'], r['spot'])} topp {r['cutoff_pct']:.0f} %"
                     + (" – utom höga rundowns" if r["spot"] in VS3BET_SPOTS else ""),
            "why": f"Händer bortom gränsen har gett {r['test']['mean']:+.2f} bb per gång jämfört med fold, bekräftat."})
    for g in guide or []:
        for row in g["rows"]:
            if row["verdict"] != "Folda":
                continue
            combo = row["combo"]
            rules.append({
                "id": f"combo|rfi|{g['pos']}|{combo}", "type": "combo", "spot": "rfi", "pos": g["pos"], "combo": combo,
                "cost": row["mean"],
                "title": f"{g['pos']}: öppna inte {COMBO_TEXT.get(combo, ('händer med bara ' if '+' not in combo else 'händer med ') + combo)}",
                "why": f"Har gett {row['mean']:+.2f} bb per öppning jämfört med fold (säkerställt: bootstrap-test med korrigering för alla rutor i guiden)."})
    pure = (rundowns or {}).get("pure") or {}
    ans = pure.get("answer") or {}
    if ans.get("kind") == "cut":
        cut_i = GROUPS.index(ans["from"])
        bad = [r for r in pure["rows"] if GROUPS.index(r["group"]) < cut_i and r["verdict"] == "förlorar"]
        if bad:
            n = sum(r["n"] for r in bad)
            cost = sum(r["mean"] * r["n"] for r in bad) / n
            groups = [r["group"] for r in bad]
            rules.append({
                "id": "rundown", "type": "rundown", "groups": groups, "cost": cost,
                "title": f"Spela inte rena rundowns med lägsta kort {', '.join(groups)}",
                "why": f"Har gett {cost:+.2f} bb per spelad hand jämfört med fold. Gäller ditt första beslut "
                       f"preflop, när handen saknar högt par och suited ess."})
    from .nutfold import confirmed_losses
    nut_losses = confirmed_losses(nut_fold)
    # "0 nöt-egenskaper" per position täcker alla första beslut och ersätter Öppningsguidens "ingen" för samma position
    zero_pos = {c["pos"] for c in nut_losses if c["nut"].startswith("0 ")}
    rules = [r for r in rules if not (r["type"] == "combo" and r["combo"] == "ingen" and r["pos"] in zero_pos)]
    for c in nut_losses:
        rules.append({
            "id": f"nut|{c['pos']}|{c['nut']}", "type": "nut", "pos": c["pos"], "nut": c["nut"], "cost": c["mean"],
            "title": f"{c['pos']}: spela inte händer med {c['nut']}",
            "why": f"Har gett {c['mean']:+.2f} bb per spelad hand jämfört med fold ({c['n']} händer, säkerställt med "
                   f"korrigering för alla rutor i tabellen). Gäller ditt första beslut preflop."})
    # mest specifika regeln först: ett regelbrott räknas på den regel som bäst förklarar det
    rules.sort(key=lambda r: {"rundown": 0, "combo": 1, "nut": 2, "cutoff": 3}[r["type"]])
    for r in rules:
        r.setdefault("level", "bekräftad")
    # trolig förbättring (inte bevisat) läggs efter de bekräftade reglerna
    from .likely import covered
    conf = list(rules)
    rules += [dict(o["rule"]) for o in (likely or []) if not covered(o, conf)]
    # bra händer i en förlorande grupp (t.ex. trippelsuited) ska inte räknas som läckor
    from .subgroups import refine
    pre = st.decisions.pre if st is not None and getattr(st, "decisions", None) else None
    rules = refine(rules, pre)
    rules = protect_combos(rules, pre)
    # 3-bets mot en öppning (regler om vilken handling, inte om att spela handen) läggs sist
    from .threebet import threebet_rules, vs3bet_nut_rule
    rules += threebet_rules(pre)
    rules += vs3bet_nut_rule(pre)
    dropped = []
    if pre is not None and pre.ft is not None and len(pre) and rules:
        # regler vars brott inte ens är en felmarginal under noll på alla händer är brus: ta bort dem
        info = careful_costs(rules, pre, detail=True)
        keep = []
        for r, d in zip(rules, info):
            if r.get("type") != "action" and d["n"] >= 30 and d["factor"] <= 0.0:
                dropped.append({"id": r["id"], "title": r["title"], "n": d["n"], "mean": d["real"], "se": d["se"]})
            else:
                keep.append(r)
        # den försiktiga kostnaden räknas på alla händer och sparas, så att den inte ändras när du
        # bara analyserar dina senaste händer
        for r, c in zip(keep, careful_costs(keep, pre)):
            r["careful"] = float(c)
        rules = keep
    first, last = st.first_date, st.last_date
    hw = next((list(r["weights"].values()) for r in (ranges or []) if r.get("weights")), None)
    return {"dropped": dropped, "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "hands": st.hands,
            "hand_weights": hw,
            "wr_curves": {r["pos"]: r["wr_curve"] for r in (ranges or []) if r.get("spot") == "rfi" and r.get("wr_curve")},  # 2.75: handstyrka (samma vikter för alla rader) – används av träningens reglage
            "first": first.strftime("%Y-%m-%d") if first else None,
            "last": last.strftime("%Y-%m-%d") if last else None, "rules": rules}


RULES_VERSION = 10  # 9 = granskning 2.54 (korsvalidering mot 3-bet, brusfilter, holdout) · 8 = undantag kräver 100 händer · 7 = mot 3-bet: folda 0 nöt-egenskaper · 2 = bootstrap-test med korrigering för många tester, 3 = undantag för bra undergrupper, 4 = 3-bet-regler,
# 5 = krympta kostnader, skyddade lönsamma kombinationer, brusregler borttagna, 6 = höga rundowns undantas mot 3-bet


def save_rules(rules: dict, variant: str | None = None) -> None:
    rules["variant"] = variant
    rules["rules_version"] = RULES_VERSION
    try:
        rules_path(variant).write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def load_rules(variant: str | None = None) -> dict | None:
    p = rules_path(variant)
    if variant and not p.exists() and variant == "PLO6" and rules_path().exists():
        p = rules_path()  # äldre regelfil (version 1.24–1.26) gällde PLO6
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        if doc.get("rules_version") != RULES_VERSION:
            return None  # regler från en äldre, mindre sträng version används inte
        return doc
    return None


# ---------------------------------------------------------------- tillämpa regler
VS3BET_SPOTS = ("mot_3bet_oop", "mot_3bet_ip")


def high_rundown(hole) -> bool:
    """Minst 5 valörer i följd med högsta kortet knekt eller högre (t.ex. QJT98, JT987, KQJT98).

    Undantas från gränsreglerna mot 3-bet: formeln undervärderar dem där, och din data har för få
    sådana händer för att rätta det. Equity räcker inte som kontroll i PLO6 – nästan alla händer har
    44–50 % mot en 3-bet-range, även låga rundowns som förlorar på att spelas – så undantaget gäller
    bara höga rundowns, som både har equity och gör de bästa stegarna."""
    rs = sorted({c[0] for c in hole})
    best_len, best_top = 1, rs[0] if rs else 0
    run = 1
    for a, b in zip(rs, rs[1:]):
        run = run + 1 if b == a + 1 else 1
        if run >= best_len:
            best_len, best_top = run, b
    return best_len >= 5 and best_top >= 11


def _score(rule, hole) -> float:
    return float(hand_features(hole) @ np.array(rule["weights"]))


def violations(rules: list, spot: str, pos: str, hole, exempt: list | None = None) -> list:
    """Vilka regler en hand bryter mot om den spelas i situationen. Regler som handen bara slipper
    tack vare ett undantag läggs i listan exempt (om den ges)."""
    out = []
    q = None
    st_name = None
    for r in rules:
        if r.get("except"):
            hit = violations([{**r, "except": None}], spot, pos, hole)
            if hit:
                if st_name is None:
                    from .subgroups import struct_of
                    st_name = struct_of(hole)
                if st_name in r["except"]:
                    if exempt is not None:
                        exempt.append({"title": r["title"], "name": st_name, "level": r.get("level", "bekräftad")})
                    continue
                out.append(r)
            continue
        if r.get("except_combo"):
            q = q or nut_qualities(hole)
            if nut_combo_label(q) in r["except_combo"]:
                if exempt is not None and violations([{**r, "except_combo": None}], spot, pos, hole):
                    exempt.append({"title": r["title"], "name": nut_combo_label(q), "level": r.get("level", "bekräftad")})
                continue
        if r["type"] == "cutoff":
            if r["spot"] == spot and r["pos"] == pos and len(hole) == r.get("num_cards", len(hole)) \
                    and _score(r, hole) < r["thr"]:
                if spot in VS3BET_SPOTS and high_rundown(hole):
                    if exempt is not None:
                        exempt.append({"title": r["title"], "name": "hög rundown", "level": r.get("level", "bekräftad")})
                    continue
                out.append(r)
        elif r["type"] == "combo":
            if r["spot"] == spot and r["pos"] == pos:
                q = q or nut_qualities(hole)
                if nut_combo_label(q) == r["combo"]:
                    out.append(r)
        elif r["type"] == "nut" and spot in (r.get("spots") or FIRST_SPOTS) and pos in (r.get("positions") or [r["pos"]]):
            q = q or nut_qualities(hole)
            k = sum(bool(x) for x in q[:3])
            if NUT_LABELS.get(k) == r["nut"]:
                out.append(r)
        elif r["type"] == "rundown" and spot in FIRST_SPOTS:
            q = q or nut_qualities(hole)
            low = rundown_low(hole)
            if low is not None and not (q[0] or q[1]) and group_of(low) in r["groups"]:
                out.append(r)
    return out


def first_rows(pre) -> np.ndarray:
    """Första raden per (hand, situation) – ett beslut räknas en gång."""
    m = np.zeros(len(pre), bool)
    if len(pre):
        key = pre.hidx.astype(np.int64) * 64 + pre.spot
        _, first = np.unique(key, return_index=True)
        m[first] = True
    return m


def rule_mask(r: dict, pre, cache: dict | None = None) -> np.ndarray:
    """Preflop-rader som regeln gäller (de raderna ska foldas), med regelns undantag borträknade."""
    n = len(pre)
    if not n or pre.ft is None:
        return np.zeros(n, bool)
    cache = {} if cache is None else cache
    H = pre.ft.H
    hx = pre.hidx
    if r["type"] == "cutoff":
        m = pre.is_spot(r["spot"]) & (pre.pos == pre.ft.code("pos", r["pos"]))
        m &= H["nh"][hx] == r.get("num_cards", 6)
        if m.any():
            if "feats" not in cache:
                from .ranges import pre_features
                cache["feats"] = pre_features(type("D", (), {"pre": pre})())
            sc = cache["feats"][m] @ np.array(r["weights"])
            hit = np.zeros(n, bool)
            hit[np.flatnonzero(m)[sc < r["thr"]]] = True
            if r["spot"] in VS3BET_SPOTS:  # höga rundowns undantas mot 3-bet (se high_rundown)
                for j in np.flatnonzero(hit):
                    if high_rundown(pre.hole(int(j))):
                        hit[j] = False
            m = hit
    elif r["type"] == "combo":
        m = pre.is_spot(r["spot"]) & (pre.pos == pre.ft.code("pos", r["pos"]))
        bits = H["hp"][hx].astype(np.int64) * 4 + H["sa"][hx] * 2 + H["rd"][hx]
        want = [b for b in range(8) if nut_combo_label((bool(b & 4), bool(b & 2), bool(b & 1))) == r["combo"]]
        m &= np.isin(bits, want)
    elif r["type"] == "nut":
        code = pre.ft.codes("nut").get(r["nut"])
        pc = [pre.ft.codes("pos")[p] for p in (r.get("positions") or [r["pos"]]) if p in pre.ft.codes("pos")]
        m = pre.is_spot(*(r.get("spots") or FIRST_SPOTS)) & np.isin(pre.pos, pc)
        m &= (H["nut"][hx] == code) if code is not None else False
    elif r["type"] == "rundown":
        low = H["rdlow"][hx]
        grp_ok = np.array([lw >= 0 and group_of(int(lw)) in r["groups"] for lw in range(-1, 15)])
        m = pre.is_spot(*FIRST_SPOTS) & ~(H["hp"][hx] | H["sa"][hx]) & grp_ok[low.astype(int) + 1]
    elif r["type"] == "action":
        from .threebet import action_mask
        return action_mask(r, pre)
    else:
        return np.zeros(n, bool)
    if r.get("except_combo"):
        bits = H["hp"][hx].astype(np.int64) * 4 + H["sa"][hx] * 2 + H["rd"][hx]
        ex = [b for b in range(8) if nut_combo_label((bool(b & 4), bool(b & 2), bool(b & 1))) in r["except_combo"]]
        m = m & ~np.isin(bits, ex)
    if r.get("except"):
        from .subgroups import STRUCT, struct_codes
        if "struct" not in cache:
            cache["struct"] = struct_codes(H["feats"][hx])
        ex = [STRUCT.index(e) for e in r["except"] if e in STRUCT]
        m = m & ~np.isin(cache["struct"], ex)
    return m


def broke_mask(rules: list, pre, vi) -> np.ndarray:
    """Per preflop-rad: bröt du mot regeln vi pekar på? För de flesta regler = du spelade handen (regeln
    säger folda). För regler om handling (typ "action") = du valde handlingen regeln säger att du inte ska
    välja (t.ex. 3-bet i stället för syn)."""
    out = ~np.isnan(pre.delta) if len(pre) else np.zeros(0, bool)
    act = [i for i, r in enumerate(rules) if r.get("type") == "action"]
    if act and len(pre) and pre.ft is not None:
        out = out.copy()
        for i in act:
            mi = vi == i
            out[mi] = pre.kind[mi] == pre.ft.code("kind", rules[i].get("bad_kind", "raise"))
    return out


def careful_costs(rules: list, pre, vi=None, detail: bool = False):
    """Försiktig kostnad per brott för varje regel.

    1. Regelns kostnad (uppmätt i den halva av spelpassen som inte valde ut regeln) eller snittet för alla
       dina brott mot den i hela urvalet – det som är minst negativt.
    2. Krympt mot noll efter hur säkert snittet är: faktor = max(0, 1 − 1/z²), där z = snittet delat med
       felmarginalen (per spelpass). Ett brott som bara är en felmarginal under noll (z = −1) kostar 0;
       vid z = −2 räknas 75 %, vid z = −3 89 %. Annars hamnar regler med många brott men osäker kostnad
       högst i fokuskön bara för att de bryts ofta.
    Regler som jämför två handlingar (cmp = "action") har redan en försiktig kostnad och behåller den."""
    from .fatigue import _cluster_mean_se
    cost = np.array([float(r.get("cost") or 0.0) for r in rules] or [0.0])
    info = [{"n": 0, "real": None, "se": None, "factor": 1.0} for _ in rules]
    if not rules or pre is None or pre.ft is None or not len(pre):
        return info if detail else cost
    vi = violation_index(rules, pre) if vi is None else vi
    m = first_rows(pre) & (vi >= 0) & broke_mask(rules, pre, vi) & ~np.isnan(pre.delta)
    out = cost.copy()
    for i, r in enumerate(rules):
        if r.get("cmp", "fold") != "fold":
            continue
        if "careful" in r and not detail:
            out[i] = float(r["careful"])
            continue
        mi = m & (vi == i)
        n = int(mi.sum())
        info[i]["n"] = n
        if n < 30:
            continue
        real, se = _cluster_mean_se(pre.delta[mi], pre.clu[mi])
        info[i].update(real=real, se=se)
        if np.isfinite(real) and real >= 0:
            # brotten har gått plus (eller noll) mot fold: regeln kostar inget och ska bort som brus
            info[i]["factor"] = 0.0
            out[i] = 0.0
            continue
        c = min(max(cost[i], real), 0.0) if cost[i] < 0 else cost[i]
        if c < 0 and np.isfinite(se) and se > 0:
            z = real / se
            f = max(0.0, 1.0 - 1.0 / (z * z)) if z < 0 else 0.0
            info[i]["factor"] = f
            c *= f
        out[i] = c
    return info if detail else out


def protect_combos(rules: list, pre) -> list:
    """Lönsamma händer i en gränsregel ska inte foldas: för gränsregler ("spela bara topp X %") prövas dina
    brott per kombination av nöt-egenskaper (högt par, suited ess, rundown). En kombination som gått bättre
    än fold även med felmarginalen (95 %, per spelpass, minst 150 händer) undantas från regeln."""
    if pre is None or pre.ft is None or not len(pre):
        return rules
    from .fatigue import _cluster_mean_se
    H = pre.ft.H
    first = first_rows(pre)
    played = ~np.isnan(pre.delta)
    bits = H["hp"][pre.hidx].astype(np.int64) * 4 + H["sa"][pre.hidx] * 2 + H["rd"][pre.hidx]
    out = []
    for r in rules:
        if r.get("type") != "cutoff":
            out.append(r)
            continue
        m = rule_mask(r, pre) & first & played
        ex = []
        for b in range(8):
            mb = m & (bits == b)
            if mb.sum() < 150:
                continue
            mean, se = _cluster_mean_se(pre.delta[mb], pre.clu[mb])
            if np.isfinite(se) and mean - 1.96 * se > 0:
                ex.append(nut_combo_label((bool(b & 4), bool(b & 2), bool(b & 1))))
        if ex:
            r = {**r, "except_combo": ex, "title": r["title"] + " – utom " + ", ".join(ex)}
        out.append(r)
    return out


def violation_index(rules: list, pre) -> np.ndarray:
    """För varje preflop-rad: index för första regeln den bryter mot (-1 = ingen). Vektoriserat."""
    n = len(pre)
    out = np.full(n, -1, dtype=np.int32)
    if not n or pre.ft is None:
        return out
    cache: dict = {}
    for ri, r in enumerate(rules):
        m = rule_mask(r, pre, cache)
        out[(out < 0) & m] = ri
    return out


_REPLAYS: dict = {}  # uppspelningar räknas en gång per hand och process


def get_replays(st, hids, hero: str) -> dict:
    """Uppspelningsdata (steg, kort, equity) för händerna, med minnescache."""
    from .replayer import replay_steps
    out = {}
    for hid in hids:
        key = (hid, hero)
        rp = _REPLAYS.get(key)
        if rp is None:
            h = st.hands_by_id.get(hid)
            if h is None:
                continue
            rp = replay_steps(h, hero)
            if len(_REPLAYS) > 400:
                _REPLAYS.clear()
            _REPLAYS[key] = rp
        out[hid] = rp
    return out


def follow_up(st, rules_doc: dict | None, hero: str, replays: bool = True) -> dict:
    """Uppföljning per vecka och lista över avvikelser i det analyserade urvalet (vektoriserat)."""
    if not rules_doc or not rules_doc.get("rules"):
        return {}
    from .facts import dt_of
    rules = rules_doc["rules"]
    pre = st.decisions.pre
    vi = violation_index(rules, pre)
    # bara första raden per (hand, situation)
    key = pre.hidx.astype(np.int64) * 64 + pre.spot
    _, first = np.unique(key, return_index=True)
    firstm = np.zeros(len(pre), bool)
    firstm[first] = True
    sel = np.flatnonzero(firstm & (vi >= 0))
    H = pre.ft.H if pre.ft is not None else None
    r_of = vi[sel].astype(np.int64)
    delta = pre.delta[sel] if len(sel) else np.zeros(0)
    played = broke_mask(rules, pre, vi)[sel] if len(sel) else np.zeros(0, bool)
    cost = np.array([r["cost"] or 0.0 for r in rules], dtype=float)
    # regler som jämför två handlingar: resultatet mot fold säger inget, använd regelns kostnad
    vs_act = np.array([r.get("cmp", "fold") != "fold" for r in rules], bool)
    if len(sel):
        delta = np.where(vs_act[r_of], cost[r_of], np.nan_to_num(delta))
    cost = np.array([r["cost"] or 0.0 for r in rules], dtype=float)
    # vecka per beslut (ISO-vecka räknas en gång per dag)
    days = (H["ts"][pre.hidx[sel]] // 86400) if len(sel) else np.zeros(0, np.int64)
    udays, dinv = np.unique(days, return_inverse=True)
    wk_of_day = []
    for d in udays.tolist():
        wk = dt_of(d * 86400).isocalendar()
        wk_of_day.append(f"{wk[0]}-v{wk[1]:02d}")
    wkeys = sorted(set(wk_of_day))
    widx = np.array([wkeys.index(w) for w in wk_of_day], dtype=np.int64)[dinv] if len(sel) else np.zeros(0, np.int64)

    def agg(groups, n):
        return {"opps": np.bincount(groups, minlength=n).astype(int),
                "dev": np.bincount(groups[played], minlength=n).astype(int),
                "actual": np.bincount(groups[played], weights=delta[played], minlength=n),
                "expected": np.bincount(groups[played], weights=cost[r_of[played]], minlength=n)}

    W = agg(widx, len(wkeys))
    P = agg(r_of, len(rules))

    def row(A, i):
        o, d = int(A["opps"][i]), int(A["dev"][i])
        return {"opps": o, "dev": d, "actual": float(A["actual"][i]), "expected": float(A["expected"][i]),
                "rate": 100.0 * d / o if o else 0.0}

    week_rows = [{"week": w, **row(W, i)} for i, w in enumerate(wkeys)]
    rule_rows = [{"title": r["title"], "level": r.get("level", "bekräftad"), **row(P, i)} for i, r in enumerate(rules)]
    tot = {k: float(sum(w[k] for w in week_rows)) if k in ("actual", "expected") else int(sum(w[k] for w in week_rows))
           for k in ("opps", "dev", "actual", "expected")}
    tot["rate"] = 100.0 * tot["dev"] / tot["opps"] if tot["opps"] else 0.0
    dev_rows = sel[played]

    def dev(j):
        hx = int(pre.hidx[j])
        return {"id": H["id"][hx], "date": dt_of(H["ts"][hx]).strftime("%Y-%m-%d %H:%M"),
                "pos": pre.label("pos", pre.pos[j]), "spot": pre.label("spot", pre.spot[j]),
                "kind": pre.label("kind", pre.kind[j]), "delta": float(pre.delta[j]),
                "rule": rules[int(vi[j])]["title"], "hole": sorted(pre.hole(j), key=lambda c: (-c[0], c[1]))}

    costly = [dev(j) for j in dev_rows[np.argsort(pre.delta[dev_rows], kind="stable")[:10]]] if len(dev_rows) else []
    latest = [dev(j) for j in dev_rows[::-1][:10]] if len(dev_rows) else []
    show = {d["id"] for d in costly + latest}
    replays = get_replays(st, show, hero) if replays else {}
    return {"rules": rules, "meta": {k: rules_doc.get(k) for k in ("created", "hands", "first", "last")},
            "weeks": week_rows, "per_rule": rule_rows, "total": tot, "costly": costly, "latest": latest,
            "replays": replays,
            "dev_rows": np.unique(pre.hidx[dev_rows]) if len(dev_rows) else np.zeros(0, np.int64)}


# ---------------------------------------------------------------- handuppspelning
STREET_NAMES = {"preflop": "Preflop", "flop": "Flop", "turn": "Turn", "river": "River"}
KIND_TEXT = {"fold": "foldar", "check": "checkar", "call": "synar", "bet": "bettar", "raise": "höjer till",
             "post_sb": "lägger SB", "post_bb": "lägger BB", "post_straddle": "straddlar", "post_dead": "lägger"}


def replay(h, hero: str) -> dict:
    bb = h.bb or 1.0
    name = lambda p: "Du" if p == hero else (h.positions.get(p) or "?")  # noqa: E731
    streets = []
    board_n = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
    for s_ in ("preflop", "flop", "turn", "river"):
        acts = [a for a in h.actions if a.street == s_ and not a.kind.startswith("post")]
        if not acts and (s_ == "preflop" or len(h.board) < board_n[s_]):
            continue
        lines = []
        for a in acts:
            amt = a.to if a.kind == "raise" else a.added
            txt = f"{name(a.player)} {KIND_TEXT.get(a.kind, a.kind)}"
            if a.kind in ("call", "bet", "raise") and amt:
                txt += f" {amt / bb:.1f} bb"
            if a.allin:
                txt += " (all-in)"
            lines.append({"hero": a.player == hero, "text": txt})
        streets.append({"name": STREET_NAMES[s_], "board": h.board[:board_n[s_]] if s_ != "preflop" else [],
                        "actions": lines})
    shown = {name(p): c for p, c in h.hole.items() if p != hero and c}
    return {"pos": h.positions.get(hero, ""), "hole": sorted(h.hole.get(hero) or [], key=lambda c: (-c[0], c[1])), "streets": streets, "shown": shown,
            "net": h.net_bb(hero), "pot": h.pot_size() / bb, "stake": f"${h.sb:g}/${h.bb:g}",
            "date": h.date.strftime("%Y-%m-%d %H:%M")}


# ---------------------------------------------------------------- träning
DECK = [(r, s) for r in range(2, 15) for s in "hdcs"]


SCEN_TEXT = {"rfi": "öppna (foldat till dig)", "bb_mot_hojning": "BB mot en öppning", "sb_mot_hojning": "SB mot en öppning",
             "mot_hojning": "mot en öppning (cold call / 3-bet)", "mot_3bet_ip": "mot en 3-bet i position",
             "mot_3bet_oop": "mot en 3-bet ur position", "efter_limp": "efter limp"}
POS_SORT = ["UTG", "LJ", "HJ", "CO", "BTN", "SB", "BB"]
BLIND_SPOT = {"SB": "sb_mot_hojning", "BB": "bb_mot_hojning"}


def trainer_scenarios(rules_doc) -> list:
    """Situationer att träna: (situation, position) för varje regel som säger något om en starthand.
    Gränser ("spela bara topp X %") ger sin egen situation; regler om nöt-egenskaper och kombinationer
    tränas i öppningen (utanför blindarna) respektive mot en öppning (i blindarna)."""
    slider = [{"key": f"pct|{p}", "spot": "pct", "pos": p, "label": f"📏 {p} – öppna topp X % (du väljer med reglaget)"}
              for p in SLIDER_POS]
    if not rules_doc:
        return slider
    out = set()
    for r in rules_doc["rules"]:
        if r["type"] in ("cutoff", "combo"):
            out.add((r["spot"], r["pos"]))
        elif r["type"] == "nut" and not r.get("spots"):  # regler mot 3-bet tränas inte i öppningen
            for p in (r.get("positions") or [r["pos"]]):
                out.add((BLIND_SPOT.get(p, "rfi"), p))
    order = {k: i for i, k in enumerate(SCEN_TEXT)}
    res = [{"key": f"{sp}|{p}", "spot": sp, "pos": p, "label": f"{p} – {SCEN_TEXT.get(sp, sp)}"}
           for sp, p in sorted(out, key=lambda x: (POS_SORT.index(x[1]) if x[1] in POS_SORT else 9, order.get(x[0], 9)))]
    # 3-bet-beslut mot en öppning (3-betta, syna eller folda), när det finns regler om 3-bets
    if any(r.get("type") == "action" for r in rules_doc["rules"]):
        res = [{"key": f"3bet|{p}", "spot": "3bet", "pos": p, "label": f"🎯 {p} mot en öppning: 3-betta, syna eller folda?"}
               for p in THREEBET_POS] + res
    k = sum(1 for x in res if x["spot"] == "3bet")  # 3-bet-träningen (största läckan) först, sedan reglaget
    return res[:k] + slider + res[k:]


THREEBET_POS = ("BB", "SB", "BTN", "CO")
ACT_WORD = {"raise": "3-betta", "call": "syna", "fold": "folda"}


def trainer_hand3(rules_doc, pos: str, seed: int | None = None) -> dict | None:
    """En hand mot en öppning med facit för 3-betta / syna / folda enligt dina regler.
    En tredjedel högt par + suited ess, en tredjedel utan suited ess, en tredjedel suited ess utan högt par."""
    rules = rules_doc["rules"]
    act = {r.get("cond"): r for r in rules if r.get("type") == "action"}
    if not act or pos not in THREEBET_POS:
        return None
    spot = {"BB": "bb_mot_hojning", "SB": "sb_mot_hojning"}.get(pos, "mot_hojning")
    n = {"PLO4": 4, "PLO5": 5}.get(rules_doc.get("variant") or "", 6)
    rnd = random.Random(seed)
    want = rnd.choice(["hp_sa", "no_sa", "sa"])
    hole = None
    for _ in range(5000):
        cand = rnd.sample(DECK, n)
        hp, sa, _rd = nut_qualities(cand)
        kind = "hp_sa" if hp and sa else ("sa" if sa else "no_sa")
        if kind == want:
            hole = cand
            break
    hole = hole or cand
    hp, sa, _rd = nut_qualities(hole)
    folds = [r for r in violations([r for r in rules if r.get("type") != "action"], spot, pos, hole)]
    reasons, note = [], ""
    if hp and sa and "hp_sa" in act:
        ok, reasons = ["raise"], [act["hp_sa"]]
    elif folds:
        ok, reasons = ["fold"], folds
    elif not sa and "no_sa" in act:
        ok, reasons = ["call", "fold"], [act["no_sa"]]
        note = "Syna eller folda – båda räknas som rätt. Bara 3-bet är fel."
    else:
        ok = ["raise", "call"]
        note = "Suited ess utan högt par: 3-betta eller syna – båda räknas som rätt."
    order = sorted(hole, key=lambda c: (-c[0], c[1]))
    return {"mode": "3bet", "pos": pos, "spot": "3bet", "situation": "någon har öppnat före dig",
            "cards": [[c[0], c[1]] for c in order], "text": " ".join(card_str(c) for c in order),
            "ok": ok, "answer": ok[0], "best": " eller ".join(ACT_WORD[a] for a in ok), "note": note,
            "nut": nut_combo_label(nut_qualities(hole)), "pct": None, "cut_pct": None, "exempt": [],
            "reasons": [{"title": r["title"], "why": r.get("why", ""), "level": r.get("level", "bekräftad")} for r in reasons]}


def trainer_positions(rules_doc) -> list:
    """Bakåtkompatibelt: positioner med en öppningsgräns."""
    if not rules_doc:
        return []
    return sorted({r["pos"] for r in rules_doc["rules"] if r["type"] == "cutoff" and r["spot"] == "rfi"})


def _percentile(rule, score, rnd) -> float:
    """Andel slumpade händer som är bättre än denna (0 = bäst). Beräknas en gång per regel."""
    key = (rule["id"], tuple(rule["weights"]), rule.get("num_cards", 6))
    if key not in _PCT_CACHE:
        r2 = random.Random(7)
        n = rule.get("num_cards", 6)
        _PCT_CACHE[key] = np.sort([_score(rule, r2.sample(DECK, n)) for _ in range(20000)])
    arr = _PCT_CACHE[key]
    return 100.0 * (1.0 - np.searchsorted(arr, score) / len(arr))


_PCT_CACHE: dict = {}


# 2.75: reglaget – "öppna topp X %" där X väljs av dig. Handstyrkan är samma poäng som gränsreglerna använder.
DEFAULT_HAND_WEIGHTS = [-0.296, 0.702, 0.708, 2.414, 0.012, 0.72, 0.658, -1.011, -1.212, 0.356, -0.45, 0.281]
SLIDER_POS = ("HJ", "CO", "BTN", "SB")
SLIDER_DEFAULT = {"HJ": 20, "CO": 25, "BTN": 30, "SB": 20}


def hand_weights(rules_doc) -> list:
    w = (rules_doc or {}).get("hand_weights")
    if not w:
        w = next((r["weights"] for r in (rules_doc or {}).get("rules", []) if r.get("type") == "cutoff" and r.get("weights")), None)
    return list(w or DEFAULT_HAND_WEIGHTS)


def slider_winrate(rules_doc, pos: str, cut: float) -> dict | None:
    """Förväntat resultat mot fold vid öppning av topp `cut` % i positionen (från hela databasens analys)."""
    c = ((rules_doc or {}).get("wr_curves") or {}).get(pos)
    if not c:
        return None
    pts = c["points"]
    x = int(round(cut))
    p = next((q for q in pts if q[0] == x), None)
    base = {k: c[k] for k in ("peak_pct", "peak_bb100", "peak_ci", "max_pct", "now_bb100", "now_pct", "share_of_hands")}
    base["solid_max_pct"] = c.get("solid_max_pct", c["max_pct"])
    base["plateau"] = c.get("plateau")
    if p is None:
        return {**base, "bb100": None, "ci": None, "solid": False, "no_data": True}
    return {**base, "bb100": p[1], "ci": p[2], "solid": p[3], "no_data": False,
            "bb100_total": round(p[1] * c["share_of_hands"], 2)}


def trainer_hand_pct(rules_doc, pos: str, cut: float, seed: int | None = None) -> dict | None:
    """Reglaget bestämmer facit: öppna om handen är inom topp `cut` %, annars folda.
    Dina regler visas bara som extra information (de ändrar inte facit). Hälften av händerna nära gränsen."""
    if pos not in SLIDER_POS:
        return None
    cut = max(0.0, min(100.0, float(cut)))
    n = {"PLO4": 4, "PLO5": 5}.get((rules_doc or {}).get("variant") or "", 6)
    pseudo = {"id": "slider", "weights": hand_weights(rules_doc), "num_cards": n}
    rnd = random.Random(seed)
    near = rnd.random() < 0.5
    want_in = rnd.random() < 0.5
    hole = pct = None
    for _ in range(3000):
        cand = rnd.sample(DECK, n)
        p_ = _percentile(pseudo, _score(pseudo, cand), rnd)
        if near and abs(p_ - cut) > 8:
            continue
        if not near and (p_ <= cut) != want_in and 0 < cut < 100:
            continue
        hole, pct = cand, p_
        break
    if hole is None:
        hole, pct = cand, _percentile(pseudo, _score(pseudo, cand), rnd)
    vs = [r for r in violations((rules_doc or {}).get("rules", []), "rfi", pos, hole) if r["type"] != "cutoff"] if rules_doc else []
    order = sorted(hole, key=lambda c: (-c[0], c[1]))
    return {"mode": "pct", "pos": pos, "spot": "pct", "exempt": [], "situation": SCEN_TEXT["rfi"],
            "cards": [[c[0], c[1]] for c in order], "text": " ".join(card_str(c) for c in order),
            "answer": "open" if pct <= cut else "fold", "pct": round(pct, 1), "cut_pct": round(cut, 1),
            "nut": nut_combo_label(nut_qualities(hole)), "reasons": [],
            "wr": slider_winrate(rules_doc, pos, cut),
            "rule_notes": [{"title": r["title"], "why": r.get("why", ""), "level": r.get("level", "bekräftad")} for r in vs]}


def trainer_hand(rules_doc, pos: str, seed: int | None = None, spot: str = "rfi", cut: float | None = None) -> dict | None:
    """En slumpad hand i situationen, med facit enligt dina regler (bekräftade och troliga).
    Hälften av händerna väljs så att de bryter mot en regel och hälften så att de inte gör det;
    finns en gräns ("topp X %") väljs dessutom hälften nära gränsen, där det är svårast."""
    if spot == "pct":
        return trainer_hand_pct(rules_doc, pos, SLIDER_DEFAULT.get(pos, 30) if cut is None else cut, seed)
    rules = rules_doc["rules"]
    if spot == "3bet":
        return trainer_hand3(rules_doc, pos, seed)
    if not any(x["spot"] == spot and x["pos"] == pos for x in trainer_scenarios(rules_doc)):
        return None
    cut = next((r for r in rules if r["type"] == "cutoff" and r["spot"] == spot and r["pos"] == pos), None)
    n = (cut or {}).get("num_cards") or {"PLO4": 4, "PLO5": 5}.get(rules_doc.get("variant") or "", 6)
    rnd = random.Random(seed)
    want_fold = rnd.random() < 0.5
    near = cut is not None and rnd.random() < 0.5

    def verdict(h, exempt=None):
        pct = _percentile(cut, _score(cut, h), rnd) if cut else None
        vs = ([cut] if cut and pct > cut["cut_pct"] else []) + \
             [r for r in violations(rules, spot, pos, h, exempt) if r["type"] != "cutoff"]
        return pct, vs

    hole = None
    for _ in range(3000):
        cand = rnd.sample(DECK, n)
        p_, v_ = verdict(cand)
        if near and abs(p_ - cut["cut_pct"]) > 12:
            continue
        if bool(v_) != want_fold:
            continue
        hole, pct, vs = cand, p_, v_
        break
    if hole is None:
        hole = cand
        pct, vs = verdict(hole)
    exempt: list = []
    verdict(hole, exempt)
    order = sorted(hole, key=lambda c: (-c[0], c[1]))
    return {"pos": pos, "spot": spot, "exempt": exempt, "situation": SCEN_TEXT.get(spot, spot),
            "cards": [[c[0], c[1]] for c in order], "text": " ".join(card_str(c) for c in order),
            # fold = en regel säger folda; open = inom din bekräftade/troliga gräns; free = ingen regel säger något
            "answer": "fold" if vs else ("open" if cut else "free"), "pct": round(pct, 1) if pct is not None else None,
            "cut_pct": round(cut["cut_pct"], 1) if cut else None,
            "nut": nut_combo_label(nut_qualities(hole)),
            "reasons": [{"title": r["title"], "why": r["why"], "level": r.get("level", "bekräftad")} for r in vs]}
