"""Sessionsfil till Claude: en session sammanfattad + de största potterna med fakta per beslut.

Filen är vanlig text (markdown) och liten, så den går att ladda upp i chatten även från mobilen.
Programmet räknar fakta (pott, SPR, pottodds, handstyrka, drag, equity vid all-in, motståndarens
visade kort). Bedömningen ur ett GTO-perspektiv görs av Claude i chatten.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

TOP = 10

PROMPT = """# Till Claude
Det här är en sessionsfil från PLO-läckfinnaren. Gör så här:
1. Ge en kort sammanfattning av sessionen (3–5 punkter): vad gick bra, vad kostade, följde jag reglerna?
2. Gå igenom de största potterna en i taget, gata för gata, ur ett GTO-perspektiv: motståndarens
   troliga range, mina blockers, om storleken var rätt och vad ett bättre beslut hade varit. Räkna med GG:s rake.
   Skilj på misstag och otur (all-in EV).
3. Avsluta med 2–3 saker att ta med till nästa session.
Kort text, tydliga instruktioner. Vänta på mina frågor mellan potterna om jag vill bolla en hand.
"""


def _f(x, d=1):
    try:
        return f"{float(x):+.{d}f}"
    except (TypeError, ValueError):
        return "–"


def _usd(x) -> str:
    x = float(x)
    return ("+" if x > 0 else ("−" if x < 0 else "")) + f"${abs(x):,.2f}".replace(",", " ")


def _cards(cs) -> str:
    from .cards import card_str
    return " ".join(card_str(c)[:-1] + SUIT4.get(c[1], c[1]) for c in sorted(cs or [], key=lambda c: (-c[0], c[1])))


# 2.72: fyrfärgslek i alla handexempel – spader svart, hjärter röd, ruter blå, klöver grön (Andreas 2026-11-14)
SUIT4 = {"s": "♠️", "h": "♥️", "d": "🔷", "c": "☘️"}


def _solver_entry(SF, h, hero, hid, t, kind):
    """Solverraden för heros t:e preflopbeslut i handen (2.78.1: även svar på 3-bet, kallsyn, limp, 4-bet)."""
    from .solvergroups import NODES, ALL_NODES, extra_decisions
    E = (SF.get("ids") or {}).get(str(hid)) or {}
    if not E:
        return None
    want = {"fold": 0, "call": 1, "raise": 2, "check": 0}.get(kind)
    if t == 0:
        for nd in NODES:
            if nd in E and E[nd].get("act") == want:
                return E[nd]
    try:
        for idx, act, _inv, o in extra_decisions(h, hero):
            nd = ALL_NODES[idx]
            if o == t and nd in E and act == want:
                return E[nd]
    except Exception:
        return None
    return None


def _hand_text(h) -> str:
    if getattr(h, "raw", ""):
        return h.raw.strip()
    try:
        from .hhwrite import to_gg_text
        return to_gg_text(h).strip()
    except Exception:
        return "(handhistoriken kunde inte återskapas)"


def session_rows(st, sess: dict) -> np.ndarray:
    """Sessionens händer (index i faktatabellen) i tidsordning."""
    H = st.ft.H
    if sess.get("_rows") is not None:  # 2.77.6: flera valda sessioner tillsammans
        r = np.asarray(sess["_rows"], dtype=np.int64)
        return r[np.argsort(H["ts"][r], kind="stable")]
    rows = np.asarray(st.rows, dtype=np.int64)
    ts = H["ts"][rows]
    r = rows[(ts >= sess["t0"]) & (ts <= sess["t1"])]
    return r[np.argsort(H["ts"][r], kind="stable")]


def top_pots(H, r: np.ndarray, n: int | None = None) -> np.ndarray:
    """De största potterna för dig: där mest stod på spel (störst vinst eller förlust), sedan pottens
    storlek. Samma ordning i sessionsfilen och på sessionssidan – "pott 3" är samma hand på båda."""
    return r[np.lexsort((-H["pot"][r], -np.abs(H["net"][r])))][:(n or TOP)]


def _rule_flags(st, rules: list):
    """(pre, vi, fr): fr markerar preflop-rader som verkligen bröt mot regeln vi pekar på."""
    from .practice import broke_mask, first_rows, violation_index
    pre = st.decisions.pre if getattr(st, "decisions", None) else None
    vi = violation_index(rules, pre) if rules and pre is not None and pre.ft is not None and len(pre) else None
    fr = None
    if vi is not None:
        fr = first_rows(pre) & broke_mask(rules, pre, vi)  # syn är inget brott mot "3-betta inte …"
    return pre, vi, fr


def session_hands(st, sess: dict, rules_doc: dict | None = None) -> list:
    """Alla händer i sessionen för tabellen på sessionssidan. "nr" = pottens nummer i sessionsfilen."""
    from .facts import decode_cards, dt_of
    ft = st.ft
    H = ft.H
    r = session_rows(st, sess)
    if not len(r):
        return []
    nr = {int(hx): i for i, hx in enumerate(top_pots(H, r), 1)}
    rules = (rules_doc or {}).get("rules") or []
    pre, vi, fr = _rule_flags(st, rules)
    broke = {}
    if vi is not None:
        for j in np.flatnonzero(fr & (vi >= 0) & ~np.isnan(pre.delta)):
            broke.setdefault(int(pre.hidx[j]), rules[int(vi[j])]["title"])
    out = []
    for hx in r:
        hx = int(hx)
        ai = int(H["ai_st"][hx])
        out.append({"nr": nr.get(hx), "id": str(H["id"][hx]), "ts": int(H["ts"][hx]),
                    "time": dt_of(int(H["ts"][hx])).strftime("%H:%M"),
                    "pos": ft.label("pos", int(H["pos"][hx])), "stake": ft.label("stake", int(H["stake"][hx])),
                    "hole": sorted(decode_cards(H["hole"][hx]), key=lambda c: (-c[0], c[1])),
                    "pot": float(H["pot"][hx]), "net": float(H["net"][hx]), "ev": float(H["ev"][hx]),
                    "luck": float(H["net"][hx] - H["ev"][hx]), "allin": ai >= 0,
                    "vpip": bool(H["vpip"][hx]), "sd": bool(H["sd"][hx]), "rule": broke.get(hx, "")})
    return out


def _focus_lines(st, r, sess) -> list:
    """Fokuspunkterna i passet: regelbrotten tillsammans och river-bluffen (luft heads-up, ingen bet framför) mot målet."""
    out = ["## Fokuspunkterna i passet"]
    pr = sess.get("per_rule") or []
    if pr:
        out.append(f"- Preflop-regler: {sum(x['dev'] for x in pr)} brott av {sum(x['opps'] for x in pr)} tillfällen, "
                   f"kostnad {sum(x['cost'] for x in pr):+.1f} bb")
    # 2.77.2: den gamla river-bluff-fokusen (var tredje gång) är ersatt av river-bluff-test v2 nedan
    try:
        from types import SimpleNamespace
        from .riverbluff import bluff_test_v2
        B = bluff_test_v2(SimpleNamespace(ft=st.ft, rows=r, hero=getattr(st, "hero", "Hero"), hands_by_id=getattr(st, "hands_by_id", None)), since_ts=0)
        if B and B.get("spots"):
            out.append(f"- 🎲 River-bluff-test v2 (river ♥️/🔷 = betta ¾ pott, ♠️/☘️ = checka): {B['spots']} lägen i passet, "
                       f"bettade {B.get('bets', 0)}, följde slumpregeln {B.get('comply', 0):.0f} %")
    except Exception:
        pass
    return out + [""] if len(out) > 1 else []


def _build(st, sess: dict, hero: str, rules_doc: dict | None = None, hours: list | None = None,
          version: str = "", coach: dict | None = None, facit=None) -> str:
    from .facts import dt_of
    from .postflop_rows import HEADER, rows_for_hand
    ft = st.ft
    H = ft.H
    r = session_rows(st, sess)
    n = len(r)
    out = [PROMPT, f"# Session {sess['start']}–{sess['end']}",
           f"Skapad {datetime.now():%Y-%m-%d %H:%M} · PLO-läckfinnaren {version} · bb = big blinds · "
           f"all-in EV = resultat där all-in räknas som equity (tar bort tur vid all-in; GG:s EV Cashout ingår inte i EV men i resultatet).", ""]
    if not n:
        return "\n".join(out + ["Inga händer i sessionen."])
    stakes = {}
    for c in H["stake"][r]:
        k = ft.label("stake", int(c))
        stakes[k] = stakes.get(k, 0) + 1
    net, ev, rake = (float(H[c][r].sum()) for c in ("net", "ev", "rake"))
    vp = 100.0 * float(H["vpip"][r].mean())
    out += ["## Sammanfattning",
            f"- Händer: {n} · {sess['minutes']} min · nivå: " + ", ".join(f"${k.replace('/', '/$')} ({v})" for k, v in stakes.items()),
            f"- Resultat: {net:+.1f} bb ({_usd(H['money'][r].sum())}) · all-in EV {ev:+.1f} bb ({_usd(H['ev_m'][r].sum())}, "
            f"{100 * ev / n:+.1f} bb/100) · rake {rake:.1f} bb ({_usd(-H['rake_m'][r].sum())})",
            _rb_line(ft, r, ev, float(H["ev_m"][r].sum()), n),
            "- Dollar per nivå: " + ", ".join(f"${k.replace('/', '/$')}: {_usd(H['money'][r][H['stake'][r] == ft.code('stake', k)].sum())}"
                                              for k in stakes),
            f"- VPIP: {vp:.0f} %",
            "- Vila/tid: " + (" · ".join(sess.get("rest_tags") or []) + (" · " if sess.get("rest_tags") else "") + sess["gap_txt"]
                             if sess.get("gap_txt") else "–") + " (morgon/utvilad är en hypotes att följa upp, inte bevisad)",
            f"- Regelföljning: {sess['follow']:.0f} % ({sess['dev']} brott av {sess['opps']} tillfällen)" if sess.get("follow") is not None else "- Regelföljning: –",
            f"- Programmets bedömning: {sess['verdict']['text']}", ""]
    SF = None
    if facit is not None:  # 2.77 (punkt 6, Andreas godkände 2026-11-18): solverfacit i sessionsfilen
        try:
            from .solverfacit import long_session_flag, session_errors
            if sess.get("_parts"):
                SF = {"n": 0, "fel": 0, "tvek": 0, "hands": 0, "ids": {}}
                for a_, b_ in sess["_parts"]:
                    x_ = session_errors(st, facit, int(a_), int(b_))
                    for k_ in ("n", "fel", "tvek"):
                        SF[k_] += x_[k_]
                    SF["hands"] += x_.get("hands", 0) or 0
                    SF["ids"].update(x_["ids"])
                SF["per100"] = 100.0 * SF["fel"] / SF["hands"] if SF["hands"] else None
            else:
                SF = session_errors(st, facit, int(sess["t0"]), int(sess["t1"]))
            out[-2:-1] = [f"- Preflop mot solvern: {SF['fel']} klara fel ({(SF['per100'] or 0):.1f} per 100 händer) · "
                          f"{SF['tvek']} tveksamma · av {SF['n']} beslut i solverlägena (klart fel = solvern gör handlingen < 1 %)"]
            L = None if sess.get("_parts") else long_session_flag(st, facit, int(sess["t0"]), int(sess["t1"]))
            if L:
                txt = f"- Långt pass ({L['hours']:.1f} h): all-in EV {L['ev_bb']:+.0f} bb"
                if L.get("early") is not None and L.get("late") is not None:
                    txt += f" · klara fel {L['early']:.1f} → {L['late']:.1f} per 100 händer (första 2 h → efter 4 h)"
                txt += " → ⚠ varning" if (L["warn"] or L.get("worse")) else " → ingen varning"
                out.insert(len(out) - 1, txt)
        except Exception:
            SF = None
    out += _focus_lines(st, r, sess)
    try:
        from .guidelines import PRIO
        out += ["## Prio-listan (gäller alla pass)"] + [f"{i}. {t} – {d}" for i, (_ic, t, d) in enumerate(PRIO, 1)] + [""]
    except Exception:
        pass
    if hours:
        out += ["## Timme för timme", "| Timme | Händer | VPIP | Mot ditt snitt | Regelbrott | Kostnad |", "|---|---|---|---|---|---|"]
        out += [f"| {x['label']} | {x['hands']} | {x['vpip']:.0f} % | {x['vdev']:+.1f} | {x['brk']} | {x['cost']:+.1f} bb |" for x in hours]
        out.append("")
    try:
        from .fatigue import session_stop
        S = session_stop(st, rules_doc, sess["t0"], sess["t1"])
    except Exception:
        S = None
    if S:
        out.append(f"## Paus och bankrulleskydd (−{S['stop_bb']:g} bb, 15 min paus efter förlorad pott > {S['big_loss_bb']:g} bb; sluta efter {S['stop_h']:g} h – försäkring, inte bevisad EV-effekt)")
        if S.get("big_losses"):
            out.append(f"- Förlorade potter > {S['big_loss_bb']:g} bb: {S['big_losses']} · paus tagen efter {S['pauses_taken']} "
                       "(ungefärligt – bara handens starttid finns)" + (" ✅" if S['pauses_taken'] == S['big_losses'] else " ⚠"))
        if S["kept"]:
            out.append("- Passet nådde aldrig gränsen ✅")
        else:
            b, a = S["before"], S["after"]
            if S.get("n_sessions", 1) > 1:   # 2.87 (R5-02): räknat per pass
                out.append(f"- Gränsen nåddes i {S['sessions_over']} av {S['n_sessions']} pass; därefter totalt "
                           f"{a['hands']} händer till (räknat per pass)" + (" ⛔" if a["hands"] > 30 else " ✅"))
            else:
                out.append(f"- Gränsen ({S['why']}) nåddes efter {S['at_min'] // 60} h {S['at_min'] % 60} min; "
                           f"därefter {a['hands']} händer till" + (" ⛔" if a["hands"] > 30 else " ✅"))
            if a["hands"]:
                out.append(f"- Före gränsen: VPIP {b['vpip']:.0f} %, {b['brk100']:.1f} regelbrott/100, all-in EV {b['ev']:+.1f} bb · "
                           f"efter: VPIP {a['vpip']:.0f} %, {a['brk100']:.1f} regelbrott/100, all-in EV {a['ev']:+.1f} bb")
        out.append("")
    if sess.get("per_rule"):
        out += ["## Regelbrott per regel", "| Regel | Tillfällen | Brott | Kostnad |", "|---|---|---|---|"]
        out += [f"| {x['title']} | {x['opps']} | {x['dev']} | {x['cost']:+.1f} bb |" for x in sess["per_rule"]]
        out.append("")
    top = top_pots(H, r, sess.get("_top"))
    MIS = []
    rules = (rules_doc or {}).get("rules") or []
    pre, vi, fr = _rule_flags(st, rules)
    out += [f"## De {len(top)} största potterna för dig (störst vinst eller förlust)", ""]
    for i, hx in enumerate(top, 1):
        hid = str(H["id"][hx])
        h = st.hands_by_id.get(hid)
        when = dt_of(int(H["ts"][hx])).strftime("%H:%M")
        pos = ft.label("pos", int(H["pos"][hx]))
        out.append(f"### Pott {i}: {hid} · {when} · {pos} · pott {H['pot'][hx]:.0f} bb · resultat {H['net'][hx]:+.1f} bb "
                   f"({_usd(H['money'][hx])}) (all-in EV {H['ev'][hx]:+.1f})")
        if h is None:
            out += ["(handen finns inte i databasen)", ""]
            continue
        hole = h.hole.get(hero) or []
        out.append(f"- Dina kort: {_cards(hole)} · bord: {_cards(h.board) if h.board else '–'} · ${h.sb:g}/${h.bb:g}")
        ai = int(H["ai_st"][hx])
        if ai >= 0:
            out.append(f"- All-in på {['preflop', 'flop', 'turn', 'river'][ai]} med {100 * float(H['ai_eq'][hx]):.0f} % equity")
        shown = {p: c for p, c in (h.shown or {}).items() if p != hero and c}
        if shown:
            out.append("- Motståndare visade: " + "; ".join(f"{h.positions.get(p, '?')} {_cards(c)}" for p, c in shown.items()))
        # preflop-beslut med regel
        if pre is not None and len(pre):
            pm = np.flatnonzero(pre.hidx == hx)
            for j in pm:
                kind = pre.label("kind", int(pre.kind[j]))
                spot = pre.label("spot", int(pre.spot[j]))
                rule = rules[int(vi[j])]["title"] if vi is not None and vi[j] >= 0 and fr[j] else ""
                from .guidelines import preflop_note
                try:
                    others = [v for k, v in (h.stacks or {}).items() if k != hero]
                    depth = min(h.stacks[hero], max(others)) / h.bb if others and hero in h.stacks else None
                except Exception:
                    depth = None
                try:
                    stake_l = st.ft.label("stake", int(H["stake"][hx]))
                except Exception:
                    stake_l = ""
                note = preflop_note(spot, kind, hole, depth, pre.label("pos", int(pre.pos[j])), stake_l)
                if spot == "bb_mot_hojning":
                    ncall, seen_raise = 0, False
                    for a_ in h.actions:
                        if a_.street != "preflop" or a_.inferred or a_.kind.startswith("post"):
                            continue
                        if a_.player == hero:
                            break
                        if a_.kind == "raise":
                            seen_raise = True
                        elif a_.kind == "call" and seen_raise:
                            ncall += 1
                    spot = f"{spot} ({'bara öppnaren i potten' if ncall == 0 else f'{ncall} synare före dig'})"
                    if kind == "call" and ncall > 0 and note:
                        note = note.replace("syna bara mot SB-öppning (heads-up), annars folda", "andra har redan synat – folda")
                sline = ""
                e_ = _solver_entry(SF, h, hero, hid, list(pm).index(j), kind) if SF else None
                if e_:
                    sline = (f" · 🧮 solvern ({e_['node']}): fold {e_['sol'][0]:.0f} / syn {e_['sol'][1]:.0f} / höj {e_['sol'][2]:.0f} % → "
                             + {"fel": "❌ klart fel", "tveksamt": "⚠ tveksamt", "ok": "✅ ok"}[e_["v"]])
                out.append(f"- Preflop: {spot} → {kind}" + sline + (f" · mot fold {pre.delta[j]:+.1f} bb" if pre.delta[j] == pre.delta[j] else "")
                           + (f" · ⚠ regel: {rule}" if rule and kind != "fold" else "") + (f" · {note}" if note else ""))
        prow = rows_for_hand(h, hero, float(H["ev"][hx]))
        try:  # 2.77 (punkt 7): återkommande misstag
            from .misstag import postflop as _mpf, preflop as _mpre
            mis = _mpre(h, hero) + (_mpf(h, hero, prow, {k: HEADER.index(k) for k in HEADER}) if prow else [])
            for m_ in mis:
                out.append(("- ❌ Misstag: " if m_["kind"] == "fel" else "- 🔎 Granska: ") + m_["text"])
                MIS.append((i, m_))
        except Exception:
            pass
        if prow:
            idx = {k: HEADER.index(k) for k in HEADER}
            out += ["", "| Gata | Spelare | Pos | Pott | SPR | Mötte | Gjorde | Hand | Färgdrag | Stegouts | Slår dig | Härifrån |",
                    "|---|---|---|---|---|---|---|---|---|---|---|---|"]  # Slår dig = 6-kortshänder
            for x in prow:
                facing = x[idx["facing"]]
                if facing != "ingen" and x[idx["facing_size_pct"]] != "":
                    fp = float(x[idx['facing_pct']]) if x[idx['facing_pct']] != "" else None
                    need = f", krav {100 * fp / (100 + fp):.0f} %" if fp is not None else ""
                    ai = " all-in" if x[idx['facing_allin']] == 1 else ""
                    facing = f"{facing}{ai} {x[idx['facing_size_pct']]:.0f} % ({x[idx['to_call_bb']]:.1f} bb{need})"
                did = x[idx["action"]] + (f" {x[idx['size_pct']]:.0f} %" if x[idx["size_pct"]] != "" else "")
                bf = x[idx["made_frac"]] if x[idx["made_frac"]] != "" else x[idx["beat_frac"]]
                # 2.81: på river visas strikt bättre, och delning separat
                tie_txt = ""
                if x[idx["street"]] == "river" and "beat_strict" in idx and x[idx["beat_strict"]] != "":
                    bf = x[idx["beat_strict"]]
                    tie_txt = f" (+{100 * x[idx['tie_frac']]:.0f} % delar)" if x[idx["tie_frac"]] not in ("", 0, 0.0) else ""
                out.append(f"| {x[idx['street']]} | {x[idx['players']]} | {'IP' if x[idx['ip']] else 'OOP'} | {x[idx['pot_bb']]:.1f} | "
                           f"{x[idx['spr']]} | {facing} | {did} | {x[idx['hand']]} | {x[idx['flush_draw']] or '–'} | "
                           f"{x[idx['straight_outs']] if x[idx['straight_outs']] != '' else '–'} | "
                           f"{f'{100 * bf:.1f} %' if bf != '' else '–'}{tie_txt} | {_f(x[idx['from_here_bb']])} |")
            from .guidelines import postflop_note
            notes = []
            for x in prow:
                nt = postflop_note(dict(zip(HEADER, x)))
                if nt and nt not in notes:
                    notes.append(f"{x[idx['street']]}: {nt}")
            if notes:
                out += [""] + [f"- {nt} (riktlinje, inte regel)" for nt in notes]
        ce = ((coach or {}).get("decisions") or {}).get(hid)
        if ce:
            from .rivercoach import line_text
            out += ["", "- " + line_text(ce)]
        out += ["", "<details><summary>Handhistorik</summary>", "", "```", _hand_text(h), "```", "</details>", ""]
    if MIS:
        out += ["## Återkommande misstag bland potterna", *[f"- Pott {i}: {m_['text']} ({'misstag' if m_['kind'] == 'fel' else 'granska'})" for i, m_ in MIS], ""]
    out += ["---", "Förklaring: \"Slår dig\" = andel av slumpade motståndarhänder (lika många kort som du, t.ex. 6 i PLO6, dina kort borttagna ur leken) som slår din hand på det bord som syns just då – på flop och turn utan kommande kort (0 % = nöten). Det är INTE motståndarens range – mot den som synat eller bettat är andelen oftast högre. "
            "\"Härifrån\" = handens resultat räknat från beslutet (all-in EV); mot en bet är det exakt skillnaden mot fold. "
            "Pottodds = att syna i % av potten inklusive betten. "
            "River-coach = programmets river-modell: vinstchans mot poolens visade händer i samma linje och EV per alternativ "
            "med rake (en uppskattning mot poolen, inte en solver)."]
    return "\n".join(out)


MAX_MULTI = 500   # 2.77.6: valfritt antal sessioner
MAX_DETAIL = 5    # fler än så: sammanställning + de 20 största potterna totalt

PROMPT_MULTI = """# Till Claude
Det här är en fil med {n} sessioner från PLO-läckfinnaren. Gör så här:
1. Ge först en kort sammanfattning av alla sessionerna tillsammans (3–5 punkter): vad gick bra, vad kostade,
   följde jag reglerna, och skiljer sig sessionerna åt (längd, nivå, VPIP, regelbrott)?
2. Gå sedan igenom de största potterna i varje session, gata för gata, ur ett GTO-perspektiv: motståndarens
   troliga range, mina blockers, om storleken var rätt och vad ett bättre beslut hade varit. Räkna med GG:s rake.
   Skilj på misstag och otur (all-in EV). Ange session och pott-nummer, t.ex. "session 2, pott 3".
3. Avsluta med 2–3 saker att ta med till nästa session.
Kort text, tydliga instruktioner. Vänta på mina frågor mellan potterna om jag vill bolla en hand.
"""


def _build_multi(st, sessions: list, hero: str, rules_doc: dict | None = None, hours_list: list | None = None,
                version: str = "", coach: dict | None = None, facit=None) -> str:
    """1–5 sessioner i en fil: en gemensam instruktion, en sammanställning och sedan varje session för sig
    (samma innehåll som en enskild sessionsfil)."""
    if len(sessions) == 1:
        return _build(st, sessions[0], hero, rules_doc, (hours_list or [None])[0], version, coach, facit)
    H = st.ft.H
    tot = {"hands": 0, "min": 0, "net": 0.0, "ev": 0.0, "money": 0.0, "ev_m": 0.0, "rake_m": 0.0, "dev": 0, "opps": 0}
    lines = []
    for i, s in enumerate(sessions, 1):
        r = session_rows(st, s)
        n = len(r)
        money, ev_m, rake_m = (float(H[c][r].sum()) for c in ("money", "ev_m", "rake_m"))
        ev = float(H["ev"][r].sum())
        tot["hands"] += n
        tot["min"] += int(s.get("minutes") or 0)
        tot["net"] += float(H["net"][r].sum())
        tot["ev"] += ev
        tot["money"] += money
        tot["ev_m"] += ev_m
        tot["rake_m"] += rake_m
        tot["dev"] += int(s.get("dev") or 0)
        tot["opps"] += int(s.get("opps") or 0)
        vp = 100.0 * float(H["vpip"][r].mean()) if n else 0.0
        lines.append(f"| {i} | {s['start']}–{s['end']} | {n} | {s.get('minutes', 0)} min | {_usd(money)} | {_usd(ev_m)} | "
                     f"{(100 * ev / n if n else 0):+.1f} | {vp:.0f} % | "
                     + (f"{s['follow']:.0f} %" if s.get("follow") is not None else "–") + " |")
    n = tot["hands"]
    out = [PROMPT_MULTI.format(n=len(sessions)),
           f"# {len(sessions)} sessioner {sessions[0]['start']} – {sessions[-1]['start']}",
           f"Skapad {datetime.now():%Y-%m-%d %H:%M} · PLO-läckfinnaren {version}", "",
           "## Alla sessioner tillsammans",
           f"- Händer: {n} · {tot['min']} min",
           f"- Resultat: {tot['net']:+.1f} bb ({_usd(tot['money'])}) · all-in EV {tot['ev']:+.1f} bb ({_usd(tot['ev_m'])}, "
           f"{(100 * tot['ev'] / n if n else 0):+.1f} bb/100) · rake {_usd(-tot['rake_m'])}",
           _rb_line(st.ft, np.concatenate([session_rows(st, s_) for s_ in sessions]), tot["ev"], tot["ev_m"], n),
           f"- Regelföljning: {100 - 100 * tot['dev'] / tot['opps']:.0f} % ({tot['dev']} brott av {tot['opps']} tillfällen)"
           if tot["opps"] else "- Regelföljning: –", "",
           "| Session | Tid | Händer | Längd | Resultat | All-in EV | EV bb/100 | VPIP | Regelföljning |",
           "|---|---|---|---|---|---|---|---|---|", *lines, ""]
    if len(sessions) > MAX_DETAIL:  # 2.77.6: många sessioner – en gemensam del med de 20 största potterna totalt
        rows_all = np.concatenate([session_rows(st, s) for s in sessions])
        comb = {"start": sessions[0]["start"], "end": sessions[-1]["end"], "minutes": tot["min"], "t0": sessions[0]["t0"],
                "t1": sessions[-1]["t1"], "_rows": rows_all, "_parts": [(s["t0"], s["t1"]) for s in sessions], "_top": 20,
                "follow": (100 - 100 * tot["dev"] / tot["opps"]) if tot["opps"] else None, "dev": tot["dev"], "opps": tot["opps"],
                "verdict": {"text": f"{len(sessions)} sessioner tillsammans"}, "gap_txt": "", "rest_tags": [], "per_rule": []}
        text = _build(st, comb, hero, rules_doc, None, version, coach, facit)
        if text.startswith(PROMPT):
            text = text[len(PROMPT):]
        text = text.replace(f"# Session {comb['start']}", f"# Alla {len(sessions)} sessioner: {comb['start']}", 1)
        out += ["---", "", text.strip(), ""]
        return "\n".join(out)
    for i, s in enumerate(sessions, 1):
        text = _build(st, s, hero, rules_doc, (hours_list or [None] * len(sessions))[i - 1], version, coach, facit)
        if text.startswith(PROMPT):
            text = text[len(PROMPT):]
        text = text.replace(f"# Session {s['start']}", f"# Session {i}: {s['start']}", 1)
        out += ["---", "", text.strip(), ""]
    return "\n".join(out)


def _rb_line(ft, rows, ev_bb: float, ev_m: float, n: int) -> str:
    """2.86: all-in EV inklusive rakeback (procentsatserna från Översikt)."""
    try:
        from .rbcurve import current_cfg, rb_rows
        rb, rb_m = rb_rows(ft, rows, current_cfg())
        rk = float(ft.H["rake"][rows].sum())
        pct = 100.0 * float(rb.sum()) / rk if rk > 0 else 0.0
        net_m = float(ft.H["money"][rows].sum())
        return (f"- **Verklig winrate (all-in EV inkl. rakeback): {100 * (ev_bb + float(rb.sum())) / n:+.1f} bb/100** "
                f"({ev_bb + float(rb.sum()):+.1f} bb, {_usd(ev_m + float(rb_m.sum()))})\n"
                f"- Rakeback: {100 * float(rb.sum()) / n:+.1f} bb/100 · {_usd(float(rb_m.sum()))} ({pct:.0f} % av raken, "
                f"procentsatserna från Översikt) · faktiskt resultat inkl. rakeback {_usd(net_m + float(rb_m.sum()))}\n"
                f"- Tur i all-ins: {_usd(net_m - ev_m)} (faktiskt resultat − all-in EV)")
    except Exception:
        return "- All-in EV inkl. rakeback: –"


def build(*args, **kw) -> str:
    """Sessionsfilen (markdown). 2.74: positionen HJ heter UTG."""
    from .positions import to_ui
    return to_ui(_build(*args, **kw))


def build_multi(*args, **kw) -> str:
    from .positions import to_ui
    return to_ui(_build_multi(*args, **kw))
