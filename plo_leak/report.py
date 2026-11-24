"""Bygger en självständig HTML-rapport av analysen."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

import base64

from . import __version__
from .cards import RANKS
from .export import export_json
from .decisions import SPOT_NAMES, ACTION_VERB, detectable_effect, tested_overview
from .leaks import PROFILES, STRICT_RULES_TEXT, detect_profile, find_leaks, find_proven, stat_table, top_three
from .parser import Hand
from .stats import POSITIONS, analyze, control_numbers, money_summary, stake_table

SUIT_SYM = {"h": ("♥", "h"), "d": ("♦", "d"), "c": ("♣", "c"), "s": ("♠", "s")}


def _cards(cards) -> Markup:
    out = []
    for r, s in cards or []:
        sym, cls = SUIT_SYM[s]
        out.append(f'<span class="card {cls}">{RANKS[r - 2]}{sym}</span>')
    return Markup("".join(out))


def _pct(v) -> str:
    return "–" if v is None else f"{v:.1f}%"


def _signed(v, digits=1) -> str:
    return f"{v:+.{digits}f}"


def _num_label(v: float, money: bool = False) -> str:
    sign = "−" if v < 0 else ""
    return (sign + ("$" if money else "") + f"{abs(v):,.0f}").replace(",", " ")


CHART_SERIES = (  # nyckel, etikett, färg (css-variabel), streckad, visas från början
    ("net", "Faktiskt resultat", "--s1", False, True),
    ("ev", "All-in EV", "--s2", False, True),
    ("sd", "Med showdown", "--s4", False, True),
    ("nsd", "Utan showdown", "--s5", False, True),
    ("rake", "Betald rake", "--s3", True, True),
    ("net_rb", "Faktiskt resultat inkl. rakeback", "--s7", False, True),  # 2.88
    ("ev_rb", "All-in EV inkl. rakeback", "--s6", False, True),  # 2.86: sessionsgraferna
)


def apply_rb(ch: dict, net_rb, ev_rb, on: bool) -> dict:
    """2.88: vinstkurvan jämför alltid lika med lika.
    Rakeback PÅ: "Faktiskt resultat inkl. rakeback" och "All-in EV inkl. rakeback" visas, linjerna utan
    rakeback är avslagna från början (kan slås på). Rakeback AV: inga rakeback-linjer alls."""
    if not ch or not ch.get("x"):
        return ch
    nd = 2 if ch.get("unit") == "$" else 1
    base = [x for x in ch["s"] if x["k"] not in ("net_rb", "ev_rb")]
    if not on or net_rb is None or ev_rb is None or len(net_rb) != ch.get("n") or len(ev_rb) != ch.get("n"):
        return {**ch, "s": base, "rb_on": False}
    s = [{**x, "on": False} if x["k"] in ("net", "ev", "sd", "nsd") else x for x in base]
    s.append({"k": "net_rb", "label": "Faktiskt resultat inkl. rakeback", "color": "--s7", "dash": False, "on": True,
              "v": [round(float(net_rb[i - 1]), nd) for i in ch["x"]]})
    s.append({"k": "ev_rb", "label": "All-in EV inkl. rakeback", "color": "--s6", "dash": False, "on": True,
              "v": [round(float(ev_rb[i - 1]), nd) for i in ch["x"]]})
    return {**ch, "s": s, "rb_on": True}


def _chart(series: dict, money: bool = False, max_points: int = 900, ts=None) -> dict:
    """Data för vinstkurvan. Grafen ritas i webbläsaren så att linjer kan slås av och på,
    och axlarna anpassas till det som visas. series: nyckel -> kumulativ serie (lika långa)."""
    base = series.get("net")
    if base is None or len(base) == 0:
        return {}
    n = len(base)
    step = max(1, -(-n // max_points))
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    nd = 2 if money else 1
    out = []
    for key, label, color, dash, on in CHART_SERIES:
        v = series.get(key)
        if v is None or len(v) != n:
            continue
        if key == "rake" and not v[-1] > 0:
            continue
        out.append({"k": key, "label": label, "color": color, "dash": dash, "on": on,
                    "v": [round(float(v[i]), nd) for i in idx]})
    res = {"n": n, "x": [i + 1 for i in idx], "unit": "$" if money else "bb", "s": out}
    ev = series.get("ev")
    if ev is not None and len(ev) == n:   # 2.88: tur i all-ins = faktiskt resultat − all-in EV (samma med och utan rakeback)
        res["luck"] = round(float(base[-1]) - float(ev[-1]), nd)
    if ts is not None and len(ts) == n:  # 2.77.6: datum och tid i grafens hover
        from .facts import dt_of
        res["d"] = [dt_of(int(ts[i])).strftime("%Y-%m-%d %H:%M") for i in idx]
    return res


def _chart_ts(st):
    """Handtider i samma ordning som de kumulativa serierna (urvalets rader)."""
    try:
        return st.ft.H["ts"][st.rows]
    except Exception:
        return None


def _big_hands(st, hero: str, n: int = 10) -> dict:
    """Urvalets största förluster och vinster (i bb) med uppspelning."""
    import numpy as np
    from .facts import decode_cards, dt_of
    from .practice import get_replays
    ft, rows = getattr(st, "ft", None), getattr(st, "rows", None)
    if ft is None or rows is None or not len(rows):
        return {}
    H = ft.H
    net = H["net"][rows]
    o = np.argsort(net, kind="stable")
    pick = {"losses": rows[o[:n]], "wins": rows[o[::-1][:n]]}
    out = {}
    for k, idx in pick.items():
        out[k] = [{"id": H["id"][j], "date": dt_of(H["ts"][j]).strftime("%Y-%m-%d %H:%M"),
                   "pos": ft.label("pos", int(H["pos"][j])),
                   "hole": sorted(decode_cards(H["hole"][j]), key=lambda c: (-c[0], c[1])),
                   "net": float(H["net"][j]), "pot": float(H["pot"][j])} for j in idx
                  if (H["net"][j] < 0 if k == "losses" else H["net"][j] > 0)]
    out["replays"] = get_replays(st, [d["id"] for k in ("losses", "wins") for d in out[k]], hero)
    return out


_ENV = None


def _template(name: str = "report.html"):
    """Mallarna kompileras en gång per process."""
    global _ENV
    if _ENV is None:
        _ENV = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                           autoescape=select_autoescape(["html"]), auto_reload=False)
        _ENV.filters.update(cards=_cards, pct=_pct, signed=_signed)
    return _ENV.get_template(name)


CHOICE_NAMES = {"fold": "fold", "call": "syn", "raise": "raise", "check": "check"}


def _choice(c: str) -> str:
    return CHOICE_NAMES.get(c, "bet " + c.split(" (")[0])


def build_report(*args, **kw) -> str:
    """Hela rapporten som en självständig HTML-sida (kommandoraden och exportfilen)."""
    from .positions import to_ui
    return to_ui(_template().render(**build_context(*args, **kw)))  # 2.74: HJ visas som UTG


def render_page(page: str, C: dict, **extra) -> str:
    """En sida i programmets gränssnitt (webben), byggd av samma innehåll som rapporten."""
    from .positions import to_ui
    return to_ui(_template("app.html").render(page=page, **C, **extra))


def build_context(hands: list[Hand], hero: str = "Hero", profile: str | None = None, st=None, pool=None,
                  strict: bool = True, river=None, sim=None, imports=None, db_info=None,
                  rules_mode: str = "load", game_rows=None, filters=None, mixed: bool = False,
                  cache_key: str | None = None, cache_dir=None, progress=None, collect: dict | None = None,
                  live: bool = False, model_key: str | None = None, model_st_fn=None, quick_info=None,
                  skip_models: bool = False) -> dict:
    """mixed=True: flera varianter tillsammans – bara resultatdelen visas, eftersom läckor,
    gränser och öppningsguide bara är meningsfulla inom en variant.
    Analyserna körs via registret i analyses.py (med sparade resultat när cache_key anges).
    live=True: för programmets gränssnitt – uppspelningar hämtas när de behövs i stället för att bäddas in."""
    from .analyses import Ctx, run
    st = st or analyze(hands, hero)
    profile = profile or detect_profile(st)
    if mixed:
        strict = True
    ctx = Ctx(st=st, hero=hero, strict=strict, mixed=mixed, pool=pool, river=river, profile=profile,
              cache_key=cache_key, cache_dir=cache_dir, model_key=model_key, model_st_fn=model_st_fn,
              skip_models=skip_models)
    R = run(ctx, progress)
    leaks = [] if mixed else R["leaks"]["leaks"]
    likely = []
    top3 = top_three(leaks) if strict else leaks[:3]
    table = stat_table(st, profile, pool)

    # positionstabell
    pos_rows = []
    for p in POSITIONS:
        b = st.by_pos.get(p)
        if not b or not b.hands:
            continue
        rfi = st.rfi_by_pos.get(p)
        pos_rows.append({"pos": p, "hands": b.hands, "vpip": 100.0 * b.vpip / b.hands,
                         "rfi": rfi.pct if rfi else None, "bb100": b.bb100, "net": b.net})
    stake_rows = stake_table(st)
    def _brow(name, b):
        return {"name": name, "hands": b.hands, "vpip": 100.0 * b.vpip / b.hands if b.hands else 0.0,
                "played": b.vpip, "per_played": b.per_played, "net_played": b.net_played}
    nut_rows = [_brow(k, st.by_nut[k]) for k in sorted(st.by_nut) if st.by_nut[k].hands]
    combo_order = ["ingen", "högt par", "suited ess", "rundown", "högt par + suited ess", "högt par + rundown",
                   "suited ess + rundown", "högt par + suited ess + rundown"]
    nut_combo_rows = [_brow(k, st.by_nut_combo[k]) for k in combo_order if st.by_nut_combo.get(k) and st.by_nut_combo[k].hands]
    nut_pos = {}
    for (lab, p_), b in st.by_nut_pos.items():
        if b.hands:
            nut_pos.setdefault(lab, {})[p_] = {"vpip": 100.0 * b.vpip / b.hands, "per": b.per_played, "played": b.vpip}
    nut_positions = [p_ for p_ in POSITIONS if any(p_ in v for v in nut_pos.values())]
    bucket_rows = sorted(
        ({"name": k, "hands": b.hands, "vpip": 100.0 * b.vpip / b.hands, "bb100": b.bb100, "net": b.net,
          "played": b.vpip, "per_played": b.per_played, "net_played": b.net_played}
         for k, b in st.by_bucket.items() if b.hands),
        key=lambda r: r["per_played"])

    # andra-bästa-förluster: visa de dyraste med slagbar hand, sammanfatta coolers
    rd = sorted((e for e in st.reverse_dominated if e["kind"] == "weak"), key=lambda e: e["net"])[:15]
    rd_summary = {}
    for kind, label in (("cooler", "Cooler (du hade nöten eller nästan, under 1 % slog dig)"),
                        ("gray", "Gränsfall (1–2 % slog dig)"),
                        ("weak", "Slagbar hand (minst 2 % slog dig)")):
        es = [e for e in st.reverse_dominated if e["kind"] == kind]
        rd_summary[kind] = {"label": label, "n": len(es), "net": sum(e["net"] for e in es)}

    queue = []
    from .summary import key_points
    ranges, guide, river_tbl, turn_tbl, rundowns = R["ranges"], R["guide"], R["river_tbl"], R["turn_tbl"], R["rundowns"]
    nut_fold = R.get("nut_fold") or {}
    if sim is None:
        from .sim import load_cached
        sim = load_cached()
    from .practice import build_rules, follow_up, load_rules, save_rules
    improve = R.get("likely") or []
    variant = max(st.games.items(), key=lambda kv: kv[1])[0].replace("-", "") if st.games else None
    own_rules = None
    if strict and not mixed:
        if rules_mode == "save":
            own_rules = build_rules(ranges, guide, rundowns, st, nut_fold, improve)
        else:
            # filtrerad vy (datum, senaste N, nivå …): visa de sparade reglerna från hela databasen – att bygga om
            # dem på ett delurval ger motsägelser (t.ex. bekräftade regler listade som borttagna)
            own_rules = load_rules(variant) or build_rules(ranges, guide, rundowns, st, nut_fold, improve)
    if own_rules and rules_mode == "save":
        # test på nya händer: regler letas i de äldre händerna och mäts på de nyare
        from .holdout import validate
        if progress:
            progress("Testar reglerna på nya händer")
        try:
            own_rules = validate(own_rules, st, hero, cache_key, cache_dir)
        except Exception:
            import traceback
            traceback.print_exc()
            own_rules = {**own_rules, "rules": [{**r, "level": "trolig", "careful": 0.0,
                         "holdout": {"verdict": "valideringsfel", "found_old": False, "n_new": 0,
                                     "mean_new": None, "se_new": None}} for r in own_rules.get("rules", [])]}
    forward = fz_doc = None
    if own_rules and rules_mode == "save" and strict and not mixed:
        # 2.71: framåttest – regler frysta 2026-11-13, mäts bara på händer spelade efter frysdatum
        try:
            from .forward import forward_test, frozen_rules
            if progress:
                progress("Framåttest av frysta regler")
            fz = frozen_rules(st, hero, cache_dir, variant)
            forward = forward_test(st, fz) if fz else None
            fz_doc = fz
            if forward:
                own_rules = {**own_rules, "forward": forward}
        except Exception:
            import traceback
            traceback.print_exc()
    if own_rules and rules_mode == "save":
        # 2.73: "bekräftad" kan bara komma från framåttestet – och bara för exakt den frysta definitionen.
        own_rules = {**own_rules, "rules": _forward_levels(own_rules.get("rules", []), forward, fz_doc)}
    conf_rules = [r for r in (own_rules or {}).get('rules', []) if r.get('level') != 'trolig']
    from .likely import covered
    improve = [o for o in improve if not covered(o, conf_rules)]
    gone = {d.get("id") for d in (own_rules or {}).get("dropped", [])}
    improve = [o for o in improve if o["rule"]["id"] not in gone]  # brus på alla händer visas inte som förbättring
    rules_src = "saved"
    if rules_mode == "save" and own_rules:
        save_rules(own_rules, variant)
        rules_doc = own_rules
    else:
        rules_doc = load_rules(variant)
        if rules_doc is None:
            rules_doc, rules_src = own_rules, "sample"
    fu = None if mixed else follow_up(st, rules_doc, hero, replays=not live)
    from .focus import focus_list
    focus = [] if mixed or not strict else focus_list(st, rules_doc)
    from .fatigue import fatigue_table
    fatigue = {} if mixed else fatigue_table(st, rules_doc, _session_limit())
    try:
        from .fatigue import down_table
        down = {} if mixed else down_table(st, rules_doc)
    except Exception:
        down = {}
    from .stakecheck import stake_check
    stakes_chk = {} if mixed else stake_check(st, rules_doc)
    if focus is not None and not mixed and strict:
        focus = add_session_focus(focus, st, rules_doc, fatigue, stakes_chk)
    if fu:
        fu["source"] = rules_src
    from .sessions import session_table
    sessions = {} if mixed else session_table(st, rules_doc)
    from .blocks import block_table
    blocks = {} if mixed else block_table(st, rules_doc)
    from .timeofday import when_table
    when = {} if mixed else when_table(st)
    from .aggr import aggression
    try:
        aggr = {} if mixed else aggression(st)
    except Exception:
        aggr = {}
    tested = R["tested"]["rows"] if R["tested"] else []

    example_ids = ({hid for lk in leaks + likely for hid, _ in lk.examples} | {e["id"] for e in rd}
                   | {q["id"] for q in queue})
    raw = {hid: st.hands_by_id[hid].raw for hid in example_ids if hid in st.hands_by_id}
    hero_cards = {hid: st.hands_by_id[hid].hole.get(hero) for hid in example_ids if hid in st.hands_by_id}
    hero_pos = {hid: st.hands_by_id[hid].positions.get(hero, "") for hid in example_ids if hid in st.hands_by_id}

    tilt = st.tilt
    export_b64 = base64.b64encode(export_json(st, hero, profile, leaks, pool=pool, strict=strict, river=river, likely=likely, top3=top3, ranges=ranges, fu=fu, results=R, extra=_extra_export(sessions, focus, fatigue, stakes_chk, blocks)).encode("utf-8")).decode("ascii")
    big_hands = {} if live else _big_hands(st, hero)
    if collect is not None:
        collect.update(st=st, results=R, leaks=leaks, top3=top3, ranges=ranges, profile=profile,
                       export_json=base64.b64decode(export_b64).decode("utf-8"), timings=ctx.timings)
    stakes = ", ".join(f"${k}" for k, _ in sorted(st.stakes.items(), key=lambda kv: -kv[1]))
    from .guidelines import GUIDELINES
    try:
        from .riverbluff import bluff_test_v2
        bluff = {} if mixed else bluff_test_v2(st)  # 2.77: v1 ogiltigt och visas inte
    except Exception:
        bluff = {}
    return dict(quick_info=quick_info, bluff=bluff, betsize=R.get("betsize") or {}, pf_forward=R.get("pf_forward") or {}, hypotheses=R.get("hypotheses") or {}, 
        guidelines=[g for g in GUIDELINES if g.get("verified")], prio=__import__("plo_leak.guidelines", fromlist=["PRIO"]).PRIO, forward=forward, st=st, hero=hero, leaks=leaks, top=top3, likely=likely, table=table, pos_rows=pos_rows,
        bucket_rows=bucket_rows, stake_rows=stake_rows, nut_rows=nut_rows, nut_combo_rows=nut_combo_rows,
        nut_pos=[{"label": k, "cells": [nut_pos[k].get(p_) for p_ in nut_positions]} for k in sorted(nut_pos)],
        nut_positions=nut_positions,
        allin_rows=[{"street": k, **v} for k, v in sorted(st.allin.items(), key=lambda kv: ["preflop", "flop", "turn"].index(kv[0]))], rd=rd, rd_summary=rd_summary, raw=raw, hero_cards=hero_cards, hero_pos=hero_pos,
        chart=_chart({"net": st.cumulative, "ev": st.cumulative_ev, "rake": st.cumulative_rake,
                      "sd": getattr(st, "cumulative_sd", None), "nsd": getattr(st, "cumulative_nsd", None)}, ts=_chart_ts(st)),
        chart_money=_chart({"net": st.cumulative_money, "ev": st.cumulative_ev_money, "rake": st.cumulative_rake_money,
                            "sd": getattr(st, "cumulative_sd_money", None), "nsd": getattr(st, "cumulative_nsd_money", None)},
                           money=True, ts=_chart_ts(st)), control=control_numbers(st), pool=pool, profile=PROFILES[profile], stakes=stakes, tilt=tilt,
        money=money_summary(st), ranges=ranges, guide=guide, river_tbl=river_tbl, river_bluff=R.get("river_bluff") or {}, river_guide=R.get("river_guide") or {}, river_coach=R.get("river_coach") or {}, postflop_leaks=_postflop_leaks(R, {f.get("gid") for f in (focus or []) if f.get("gid")}) + _when_leak(when), when=when, aggr=aggr, turn_tbl=turn_tbl, rundowns=rundowns, sim=sim,
        imports=imports or [], db_info=db_info, fu=fu, big_hands=big_hands, game_rows=game_rows or [], filters=filters, mixed=mixed,
        main_game=max(st.games.items(), key=lambda kv: kv[1])[0].replace("-", "") if st.games else "",
        points=key_points(st, money_summary(st), stake_rows, [] if mixed else nut_rows, guide, river_tbl, leaks, turn_tbl,
                          nut_fold={} if mixed else nut_fold,
                          confirmed=conf_rules, likely=improve, pots=R.get('potsize'), hourly=R.get('hourly')) + _fatigue_point(fatigue) + _stake_point(stakes_chk) if strict else [],
        focus_all=focus, pots=R.get('potsize') or {}, hourly=R.get('hourly') or {}, confirmed_rules=conf_rules, improve=improve, sessions=sessions, fatigue=fatigue, down=down, stake_check=stakes_chk, blocks=blocks, threebet=_threebet(st, mixed), dropped_rules=(own_rules or {}).get('dropped', []), holdout=(rules_doc or {}).get('holdout'), holdout_rules=[r for r in (rules_doc or {}).get('rules', []) if r.get('holdout')], rule_subs=_display_subgroups((own_rules or {}).get('rules', [])), pos_leaks={} if mixed else (R.get('pos_leaks') or {}), nut_fold=nut_fold, nut_fold_by={r['name']: r for r in nut_fold.get('rows', [])},
        strict=strict, strict_text=STRICT_RULES_TEXT, live_replay=live, tests=R["leaks"]["tests"],
        candidates=R["leaks"]["candidates"],
        power=R["power"]["rows"] if R["power"] else [],
        river=river, queue=queue, freq=[], tested=tested[:60],
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"), version=__version__, export_b64=export_b64,
        export_name=f"plo_analys_till_claude_{datetime.now():%Y%m%d_%H%M}.json",
    )



def _extra_export(sessions, focus, fatigue=None, stakes=None, blocks=None) -> dict:
    """Sessioner, tid i sessionen, nivåer och fokuslistan i analysfilen till Claude."""
    from .sessions import export_sessions
    fl = [{k: v for k, v in f.items() if k != "dev_rows"} for f in (focus or [])]
    return {"sessions": export_sessions(sessions), "focus_queue": fl, "time_in_session": fatigue or {},
            "stake_check": stakes or {}, "development_blocks": _blocks_export(blocks)}


def _when_leak(W) -> list:
    if W and W.get("significant") and W.get("value100", 0) >= 0.1:
        return [{"do": f"Spela {W['best']} – din bästa tid", "per100": float(W["value100"]), "link": "tider"}]
    return []


def _postflop_leaks(R, tracked=()) -> list:
    """River-läckor som inte är regler (mätta, men inte följda vecka för vecka) – för läckkartan på Översikt."""
    out = []
    g = R.get("river_guide") or {}
    if g.get("sizes") and g.get("val100", 0) >= 0.1 and any(z["fold_pct"] >= 15 for z in g["sizes"]):
        out.append({"do": "River mot bet: syna starka händer – se gränsen", "per100": float(g["val100"])})
    # Riktlinjerna från postflop-analysen (uppskattad vinst, följs inte vecka för vecka). River-bluffen ingår där
    # (#1), så den äldre mätningen av samma läcka visas inte separat. Riktlinjer som följs som fokuspunkter
    # (tracked, se pffocus.py) visas där i stället, med kostnad räknad på dina senaste händer.
    from .guidelines import GUIDELINES
    for x in GUIDELINES:
        if x.get("per100", 0) >= 0.1 and x.get("verified") and x["id"] not in tracked:
            # 2.81: kostnaden är en tidigare uppskattning (fast värde i guidelines.py), inte mätt på ditt aktuella urval –
            # märks så, och visas inte alls när urvalet saknar underlag
            if not R:
                continue
            out.append({"do": x["title"], "title": x["title"], "per100": float(x["per100"]),
                        "link": "postflop" if x.get("area") == "postflop" else "preflop", "guide": True,
                        "rank": x.get("rank"), "level": x.get("level", ""), "gain": x.get("gain", ""),
                        "estimate": "tidigare uppskattning (ursprung: postflop-analysen 2026-11, inte mätt på ditt urval)"})
    return out


def _threebet(st, mixed):
    if mixed or st is None or not getattr(st, "decisions", None):
        return {}
    from .threebet import analyze
    return analyze(st.decisions.pre)


def _blocks_export(blocks):
    from .blocks import export_blocks
    return export_blocks(blocks or {})


def _session_limit():
    """Den sessionsgräns (timmar) du valt under Sessioner, annars None (= rekommenderad)."""
    try:
        from .db import default_path
        from .watch import load_settings
        v = load_settings(type("D", (), {"path": default_path()})()).get("sess_limit_h")
        return float(v) if v else None
    except Exception:
        return None


def add_session_focus(focus, st, rules_doc, fatigue, stakes=None):
    """Lägg sessionslängden och nivåvalet i fokuskön (om de är tydliga läckor) och sortera om."""
    from .fatigue import focus_item
    from .focus import DONE_MIN, DONE_WEEKS, RECENT
    from .stakecheck import focus_item as stake_item
    from .pffocus import focus_items as pf_items
    focus = [f for f in focus if f.get("kind") not in ("session", "stake", "pf")]
    # 2.77 (Andreas 2026-11-18): stoppregeln 2 h räknas inte längre som läcka – ersatt av 4 h-flaggan per pass
    for it in (stake_item(st, stakes, RECENT, DONE_WEEKS, DONE_MIN),):
        if it:
            focus.append(it)
    try:  # 2.77.2: fokusen "river-bluff var tredje gång" (pf_river_bluff) är dold – ersatt av test v2
        from .guidelines import HIDDEN_277
        focus += [x for x in pf_items(st, RECENT, DONE_WEEKS) if x.get("gid") not in HIDDEN_277]
    except Exception:
        pass
    focus.sort(key=lambda x: (x["done"], -x["per100"]))
    return focus


def _stake_point(S) -> list:
    """Punkt till "Det viktigaste" om du gått tydligt sämre på en nivå."""
    if not S or not S.get("worse") or not S.get("best"):
        return []
    b = S["best"]
    txt = "; ".join(f"${x['stake'].replace('/', '/$')} ${x['usd_h']:+.0f}/h · {x['ev100']:+.1f} bb/100 ({x['hands']:,} händer, VPIP {x['vpip']:.0f} %)"
                    for x in S["worse"]).replace(",", " ")
    return [{"tone": "bad", "title": "Nivå",
             "text": (f"Du har tjänat tydligt mindre per timme på andra nivåer: {txt} – mot ${b['stake'].replace('/', '/$')} "
                      f"${b['usd_h']:+.0f}/h · {b['ev100']:+.1f} bb/100 (VPIP {b['vpip']:.0f} %), all-in EV efter rake, rakeback ej "
                      f"inräknad. Skillnaden i dollar per timme håller även med felmarginalen (villkorad på din takt i händer per timme).")}]


def _fatigue_point(F) -> list:
    """Punkt till "Det viktigaste" om du spelar tydligt sämre i långa sessioner."""
    if not F or not F.get("significant") or not F.get("limit_h"):
        return []
    from .fatigue import hours_text
    h = hours_text(F["limit_h"])
    late = [x for x in F["rows"][1:] if x.get("worse")]
    d = max((x.get("vdiff") or 0) for x in late) if late else 0
    save = F.get("save100") or 0
    return [{"tone": "bad", "title": "Långa sessioner",
             "text": (f"Efter {hours_text(F['recommended_h'])} i samma session spelar du upp till {d:.0f} procentenheter fler "
                      f"händer än du brukar i samma läge och bryter oftare mot dina regler. {F['late_share']:.0f} % av dina "
                      f"händer spelas efter {h}. En paus på minst 30 minuter efter {h} är värd ca "
                      f"{save:.1f} bb/100. Se Sessioner → Tid i sessionen.")}]


def _display_subgroups(rules):
    """Display-only adapter; raw means are identified explicitly, never fabricated as shrinkage."""
    out = []
    for r in rules:
        if not r.get("sub"):
            continue
        rr = dict(r)
        rr["sub"] = []
        for x in r["sub"]:
            if x.get("est") is None and x.get("mean") is None:
                continue
            y = dict(x)
            if y.get("est") is None:
                y["est"] = y.get("mean")
            y.setdefault("p_pos", None)
            y.setdefault("exempt", y.get("name") in (r.get("except") or []))
            y["estimate_kind"] = "skattat" if "est" in x else "rått snitt"
            rr["sub"].append(y)
        if rr["sub"]:
            out.append(rr)
    return out


def _forward_levels(rules, forward, frozen):
    """Sätter regelnivån efter framåttestet (2.73): "bekräftad" bara när den frysta regeln med samma id har utfallet
    "håller" OCH dagens regel har exakt samma definition som den frysta. Allt annat är "trolig"."""
    from .holdout import _definition
    verdict = {r.get("id"): r.get("verdict") for r in (forward or {}).get("rules", [])}
    fdef = {}
    for r in (frozen or {}).get("rules", []):
        try:
            fdef[r.get("id")] = _definition(r)
        except Exception:
            pass
    # 2.81: en hand räknas mot första matchande regel – regeln täcker samma händer bara om samma regler ligger före den
    def _defs(lst):
        out_ = []
        for x in lst:
            try:
                out_.append(_definition(x))
            except Exception:
                out_.append(None)
        return out_
    f_list = (frozen or {}).get("rules", [])
    f_defs, t_defs = _defs(f_list), _defs(rules)
    f_before = {x.get("id"): set(f_defs[:i]) for i, x in enumerate(f_list)}
    out = []
    for i, r in enumerate(rules):
        same = False
        try:
            same = fdef.get(r.get("id")) == _definition(r)
        except Exception:
            pass
        same_cover = same and f_before.get(r.get("id")) == set(t_defs[:i])
        ok = verdict.get(r.get("id")) == "håller" and same and same_cover
        out.append({**r, "level": "bekräftad" if ok else "trolig",
                    "forward_verdict": verdict.get(r.get("id")), "forward_same_definition": bool(same),
                    "forward_same_coverage": bool(same_cover)})
    return out
