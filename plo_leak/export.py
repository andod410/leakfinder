"""Skapar en fil att ladda upp till Claude för vidare analys.

Filen innehåller all statistik, diagnostik och ett litet urval exempelhänder
(anonymiserade) – tillräckligt för att kontrollera att programmet läst dina
händer rätt och för att göra en djupare analys. Den är normalt några hundra kB.
"""
from __future__ import annotations

import json
import random
import re

import numpy as np
from datetime import datetime

from . import __version__
from .cards import card_str
from .leaks import Leak
from .decisions import detectable_effect, tested_overview
from .stats import HeroStats, control_numbers, stake_table

MAX_RAW = 4000  # tecken per hand


def _cards(cs) -> str:
    return " ".join(card_str(c) for c in cs or [])


def anonymize(raw: str, hand, hero: str) -> str:
    """Byt spelarnamn mot Hero / P1, P2 … (per hand)."""
    names = sorted(hand.seats, key=len, reverse=True)
    mapping = {}
    i = 0
    for n in sorted(hand.seats, key=lambda n: hand.seats[n]):
        if n == hero:
            mapping[n] = "Hero"
        else:
            i += 1
            mapping[n] = f"P{i}"
    out = raw
    for n in names:
        out = re.sub(r"(?<![\w])" + re.escape(n) + r"(?![\w])", mapping[n], out)
    return out[:MAX_RAW]


def _pool_dict(pool) -> dict | None:
    if not pool:
        return None
    def b(x):
        return {"p10": round(x.lo, 1), "p25": round(x.p25, 1), "median": round(x.median, 1),
                "p75": round(x.p75, 1), "p90": round(x.hi, 1), "players": x.n, "group": x.group}
    return {"anonymized": pool.anonymized, "min_hands": pool.min_hands, "players_total": pool.players_total, "regs": pool.regs,
            "winners": pool.winners, "group": pool.group, "hands_per_player": pool.hands_per_player,
            "ranges": {k: b(v) for k, v in pool.ranges.items()},
            "rfi": {k: b(v) for k, v in pool.rfi.items()},
            "extra": {k: b(v) for k, v in pool.extra.items()},
            "regs_list": pool.reg_rows[:60]}


def _river_dict(river) -> dict | None:
    if river is None:
        return None
    return {
        "summary": river.summary,
        "recalibration": river.pool.cal_info if river.pool else {},
        "calibration_vs_hero": river.calibration,
        "note": "Beskrivande modell. Ger inga läckor; fynd och granskningslista exporteras inte "
                "eftersom de inte kan kontrolleras mot verkliga utfall.",
    }


def _leak_dict(l):
    return {"key": l.key, "title": l.title, "value": l.value, "target": l.target, "source": l.source,
            "severity_bb100": round(l.severity, 2),
            "severity_bb100_conservative": round(l.severity_low, 2) if l.severity_low is not None else None, "level": l.level, "opps": l.opps,
            "confidence": l.confidence, "spot_note": l.spot_note, "what": l.what}


def build_export(st: HeroStats, hero: str, profile: str, leaks: list[Leak], anon: bool = True, pool=None,
                 strict: bool = True, river=None, likely=None, top3=None, ranges=None, fu=None, results=None) -> dict:
    R = results or {}
    def stat_dict(s):
        return {"hits": s.hits, "opps": s.opps, "pct": round(s.pct, 2) if s.pct is not None else None,
                "net_bb_when_hit": round(s.net_hit, 1), "net_bb_all": round(s.net_all, 1)}

    def raw_of(hid):
        h = st.hands_by_id.get(hid)
        if not h:
            return None
        return anonymize(h.raw, h, hero) if anon else h.raw[:MAX_RAW]

    # urval av händer: varje syfte för sig + några slumpvisa + de dyraste
    samples = {k: [raw_of(i) for i in ids] for k, ids in st.samples.items()}
    H, rows = st.ft.H, st.rows
    ids = list(H["id"][rows])
    rnd = random.Random(42)
    samples["random"] = [raw_of(i) for i in rnd.sample(ids, min(10, len(ids)))]
    worst = np.argsort(H["net"][rows], kind="stable")[:8]
    samples["biggest_losses"] = [raw_of(ids[i]) for i in worst]
    for lk in leaks:
        samples[f"leak:{lk.key}"] = [raw_of(hid) for hid, _ in lk.examples[:3]]
    for lk in (likely or []):
        samples[f"likely:{lk.key}"] = [raw_of(hid) for hid, _ in lk.examples[:3]]

    rd = []
    for e in sorted(st.reverse_dominated, key=lambda e: e["net"])[:40]:
        rd.append({"id": e["id"], "net_bb": round(e["net"], 1), "pot_bb": round(e["pot"], 1),
                   "hero": _cards(e["hero_cards"]), "villain": _cards(e["villain_cards"]),
                   "board": _cards(e["board"]), "hero_hand": e["hero_hand"], "villain_hand": e["villain_hand"],
                   "beaten_by_pct": round(e["beats_pct"], 2) if e["beats_pct"] is not None else None,
                   "risk_pct": round(e["risk_pct"], 1) if e["risk_pct"] is not None else None, "kind": e["kind"]})
    rd_summary = {}
    for kind in ("cooler", "gray", "weak"):
        es = [e for e in st.reverse_dominated if e["kind"] == kind]
        rd_summary[kind] = {"hands": len(es), "net_bb": round(sum(e["net"] for e in es), 1)}

    t = st.tilt or {}
    return {
        "format": "plo-leak-finder-export",
        "version": __version__,
        "method_versions": {"facts": __import__("plo_leak.facts", fromlist=["FACTS_VERSION"]).FACTS_VERSION,
                            "calculations": __import__("plo_leak.db", fromlist=["CALC_VERSION"]).CALC_VERSION,
                            "rules": __import__("plo_leak.practice", fromlist=["RULES_VERSION"]).RULES_VERSION},
        "method_notes": ["All-in EV är inte en kontrafaktisk värdering av alla beslut.",
                         "River-coachens modellråd är hypoteser från selekterade showdownhänder.",
                         "Historiska riktlinjer räknas inte automatiskt om för ett nytt urval."],
        "generated": datetime.now().isoformat(timespec="seconds"),
        "profile": profile,
        "hero_name_in_file": "Hero" if anon else hero,
        "summary": {
            "hands": st.hands, "net_bb": round(st.net_bb, 1), "bb_per_100": round(st.bb100, 2),
            "net_money": round(st.net_money, 2), "rake_paid_bb_approx": round(st.rake_paid_bb, 1),
            "rake_paid_money": round(st.rake_paid_money, 2),
            "rake_bb_per_100": round(100 * st.rake_paid_bb / st.hands, 2) if st.hands else None,
            "allin_ev_bb": round(st.ev_net_bb, 1),
            "allin_ev_money": round(st.ev_net_money, 2), "allin_ev_bb_per_100": round(st.ev_bb100, 2),
            "ev_diff_money_ev_minus_actual": round(st.ev_net_money - st.net_money, 2),
            "allin_ev_bb_per_100_before_rake": round(100 * (st.ev_net_bb + st.ev_rake_bb) / st.hands, 2) if st.hands else None,
            "bb_per_100_before_rake": round(100 * (st.net_bb + st.rake_paid_bb) / st.hands, 2) if st.hands else None,
            "corrupt_hands_fixed": int(H["corrupt"][rows].sum()),
            "first": st.first_date.isoformat() if st.first_date else None,
            "last": st.last_date.isoformat() if st.last_date else None,
            "stakes_posted_blinds": dict(st.stakes), "games": dict(st.games),
            "players_per_hand": {str(k): v for k, v in sorted(st.players.items())},
            "postflop_aggression_pct": round(st.agg_freq, 2) if st.agg_freq is not None else None,
        },
        "diagnostics": {
            **{k: v for k, v in st.diag.items()},
            "header_examples": st.header_examples,
        },
        "allin_by_street": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in st.allin.items()},
        "by_stake": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in st.by_stake.items()},
        "stake_table": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in stake_table(st)],
        "control_numbers": dict(control_numbers(st)),
        "stats": {k: stat_dict(v) for k, v in sorted(st.s.items())},
        "rfi_by_position": {k: stat_dict(v) for k, v in st.rfi_by_pos.items()},
        "by_position": {k: {"hands": b.hands, "vpip": b.vpip, "net_bb": round(b.net, 1),
                            "bb_per_100": round(b.bb100, 2)} for k, b in st.by_pos.items()},
        "starting_hands": {k: {"dealt": b.hands, "played": b.vpip, "net_bb_played": round(b.net_played, 1),
                               "bb_per_hand_played": round(b.per_played, 3), "net_bb_all": round(b.net, 1)}
                           for k, b in st.by_bucket.items()},
        "nut_qualities": {k: {"dealt": b.hands, "played": b.vpip, "net_bb_played": round(b.net_played, 1),
                              "bb_per_hand_played": round(b.per_played, 3)} for k, b in sorted(st.by_nut.items())},
        "nut_quality_combos": {k: {"dealt": b.hands, "played": b.vpip, "net_bb_played": round(b.net_played, 1),
                                   "bb_per_hand_played": round(b.per_played, 3)} for k, b in st.by_nut_combo.items()},
        "nut_qualities_by_position": {f"{k[0]}|{k[1]}": {"dealt": b.hands, "played": b.vpip,
                                                         "net_bb_played": round(b.net_played, 1)}
                                      for k, b in st.by_nut_pos.items()},
        "starting_hands_ep_open": {k: stat_dict(v) for k, v in st.by_bucket_ep.items()},
        "tilt": {"triggers": t.get("triggers"), "after": stat_dict(t["after"]) if t else None,
                 "normal": stat_dict(t["normal"]) if t else None},
        "same_category_showdown_losses": {"summary": rd_summary, "worst": rd},
        "mode": "strict" if strict else "hypotheses",
        "top3": [_leak_dict(l) for l in (top3 or [])],
        "likely_leaks": [_leak_dict(l) for l in (likely or [])],
        "river_model": _river_dict(river),
        "opening_guide": R["guide"] if "guide" in R else __import__("plo_leak.ranges", fromlist=["opening_guide"]).opening_guide(st.decisions),
        "rundown_simulation": __import__("plo_leak.sim", fromlist=["load_cached"]).load_cached(),
        "starting_hands_vs_fold": R.get("nut_fold"),
        "position_leaks": R.get("pos_leaks"),
        "hypotheses_2026_11_15": R.get("hypotheses"),
        "pot_size": R.get("potsize"),
        "hourly": R.get("hourly"),
        "rule_exceptions": _rule_exceptions(),
        "likely_improvements": [{k: v for k, v in o.items() if k != "rule"} for o in (R.get("likely") or [])],
        "rundowns": R["rundowns"] if "rundowns" in R else __import__("plo_leak.rundowns", fromlist=["rundown_table"]).rundown_table(st),
        "turn_calls": R["turn_tbl"] if "turn_tbl" in R else __import__("plo_leak.summary", fromlist=["turn_call_table"]).turn_call_table(st.decisions),
        "river_calls": R["river_tbl"] if "river_tbl" in R else __import__("plo_leak.summary", fromlist=["river_call_table"]).river_call_table(st.decisions),
        "range_cutoffs": [{k: v for k, v in r.items() if k != "curve"} for r in (ranges or [])],
        "follow_up": ({"rules": [{k: v for k, v in r.items() if k != "weights"} for r in fu["rules"]],
                       "rules_from": fu["meta"], "source": fu.get("source"), "weeks": fu["weeks"],
                       "per_rule": fu["per_rule"], "total": fu["total"]} if fu else None),
        "decision_tests": {"tests": R["leaks"]["tests"] if R.get("leaks") else st.decisions.tests,
                           "candidates_from_half_A": R["leaks"]["candidates"] if R.get("leaks") else getattr(st.decisions, "candidates", None), "engine": "upptäck i halva A, bekräfta i halva B (kluster = spelpass: alla bord, nytt pass efter 30 min paus)",
                           "detectable_loss_bb_per_decision": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}
                                                               for r in (R["power"]["raw"] if R.get("power") else detectable_effect(st.decisions))],
                           "weakest_60": (R["tested"]["raw"] if R.get("tested") else tested_overview(st.decisions))[:60],
                           "strongest_20": (R["tested"]["raw"] if R.get("tested") else tested_overview(st.decisions))[-20:]},
        "pool_benchmarks": _pool_dict(pool),
        "leaks": [{"key": l.key, "title": l.title, "value": l.value, "target": l.target, "source": l.source,
                   "severity": round(l.severity, 2), "level": l.level, "opps": l.opps,
                   "confidence": l.confidence, "spot_note": l.spot_note} for l in leaks],
        "sample_hands": samples,
    }


def export_json(st: HeroStats, hero: str, profile: str, leaks: list[Leak], anon: bool = True, pool=None,
                strict: bool = True, river=None, likely=None, top3=None, ranges=None, fu=None, results=None,
                extra: dict | None = None) -> str:
    d = build_export(st, hero, profile, leaks, anon, pool, strict, river, likely, top3, ranges, fu, results)
    d.update(extra or {})
    from .positions import to_ui
    return to_ui(json.dumps(d, ensure_ascii=False, indent=1, default=_json_default))  # 2.74: HJ visas som UTG


def _json_default(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, tuple):
        return list(o)
    return str(o)


def _rule_exceptions() -> dict:
    """Sparade regler per variant med undergrupper och undantag (bra händer som inte räknas som läckor)."""
    from .practice import load_rules, rule_variants
    out = {}
    for v in rule_variants():
        doc = load_rules(v) or {}
        out[v or "?"] = [{k: r.get(k) for k in ("title", "level", "cost", "cost_all", "except", "sub")}
                         for r in doc.get("rules", []) if r.get("sub")]
    return out
