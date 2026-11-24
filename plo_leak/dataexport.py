"""Djupanalys till Claude: hela urvalet som tabeller (CSV) i en zip-fil.

Analysfilen (JSON) innehåller sammanställningar. Den här filen innehåller raderna bakom dem, så att
Claude kan räkna fram nya saker som programmet inte visar: en rad per hand, per preflop-beslut, per
syn mot turn-bet och per beslut mot river-bet, plus sessionerna och dina regler. Inga spelarnamn
finns med (bara dina egna kort och resultat), bara GG:s hand-id så att en hand går att hitta igen.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime

import numpy as np

README = """PLO-läckfinnaren – djupanalys till Claude
==========================================
Urval: {sel}
Skapad: {created} · version {version}
Inga spelarnamn finns med. bb = big blinds. "vs_fold_bb" = resultat (all-in EV, efter rake) jämfört med att
folda i just det beslutet; tomt = du foldade.

hands.csv – en rad per hand
  hand_id, time, session (nr i tidsordning), stake, cards (4/5/6), players, table (vanligt/rush), straddle (1 = någon
  straddlade; sådana händer finns inte i solvern – från 2.83), pos (UTG, CO, BTN, SB,
  BB – 5-max; UTG hette HJ i exporter före 2.74),
  hole, nut_n (antal nöt-egenskaper), nut (vilka), struct (undergrupp: trippelsuited …), start_bucket,
  net_bb, ev_bb (all-in EV; GG:s EV Cashout ingår inte i ev men i net/money), money, ev_money, rake_bb, pot_bb, vpip, allin_street, allin_eq,
  showdown, won, fold_street, final_hand (handens slutliga styrka om bordet gick ut),
  last_aggressor (hero/annan/ingen), put_in_calls_bb, put_in_bets_bb, hands_per_hour_now (dina händer per timme
  runt handen, ±15 min – mått på hur många bord du spelade)
preflop.csv – en rad per preflop-beslut
  hand_id, spot (situation), pos, action, vs_fold_bb, first (1 = första beslutet i situationen),
  rule (regeln beslutet bröt mot, om du spelade handen; tomt = ingen), rule_level
turn_calls.csv – syner mot en bet på turn: hand_id, strength, vs_fold_bb, river (vad som hände sedan)
river.csv – beslut mot en bet på river: hand_id, bet_size, strength, action, vs_fold_bb
postflop.csv – en rad per beslut du tog på flop, turn och river:
  hand_id, street, players (kvar i handen), ip (1 = sist att agera), pfa (1 = du höjde sist preflop),
  pot_bb (potten när gatan började), spr (effektiv stack / pott), facing (ingen/bet/raise), facing_pct
  (att syna delat med potten INKLUSIVE betten, i %: en pottstor bet ger 50; det du behöver vinna = x/(100+x),
  33 % mot en pottstor bet), action (check/bet/call/raise/fold), size_pct (din bet/höjning i % av potten),
  hand (din bästa hand just då), flush_draw (ja/nöt), board_paired, board_suits, prev_aggressor (vem som
  bettade/höjde sist på förra gatan), order (ditt 1:a, 2:a … beslut på gatan), hero_in_bb (det du lagt i
  potten före beslutet), to_call_bb, from_here_bb (handens resultat räknat från beslutet: all-in EV + det du
  redan lagt i; att folda ger 0, så mot en bet är from_here_bb exakt skillnaden mot fold), villain_hand
  (bästa hand en motståndare visade upp vid showdown, på hela bordet; tomt = ingen visade), villain_better
  (1 = den slog din hand, 0 = du hade bäst), facing_size_pct (betten/höjningen du mötte i % av potten före
  den; en pottstor bet = 100), beat_frac (bara river: andel slumpade motståndarhänder med lika många kort som du
  (6 i PLO6, dina kort borttagna ur leken) som slår din hand på bordet, lika räknas som halv (2.81: se beat_strict
  = strikt bättre och tie_frac = delar, sist i raden) – jämförbar mellan bord;
  INTE motståndarens range, mot den som synat eller bettat är andelen oftast högre), straight_outs (flop/turn: kort kvar som ger
  dig en stege, 0 = inget stegdrag eller redan stege), pot_type (limp / enkel höjning / 3-bet / 4-bet+), hero_pos,
  facing_allin (1 = betten/höjningen du möter är all-in, så du kan bara syna eller folda; tomt = du mötte ingen bet),
  hero_allin (1 = ditt beslut satte dig all-in), eff_stack_bb (effektiv stack i bb just före beslutet: det minsta av
  ditt och den största motståndarens kvarvarande), made_frac (handstyrka just nu på alla gator: andel slumpade
  motståndarhänder som slår din hand på det bord som syns – på river samma som beat_frac; jämför lika starka händer
  på flop/turn med den, inte bara med handkategorin), from_here_pot (from_here_bb delat med potten vid beslutet –
  jämför handlingar i potter av olika storlek med den, inte med bb), board (bordskorten vid beslutet, t.ex. "Ks 8d 3c 2h"),
  board_type (floppens struktur: parat / monotont / högt torrt / högt sammanhängande / lågt sammanhängande / mellan/övrigt),
  set_rank (topp / mellan / botten när du har set på oparat bord, annars tomt), pot_at_decision_bb, pot_after_call_bb,
  spr_after_call, draw_outs, nut_outs, raw_amount_bb (råbelopp för syn/bet), effective_risk_bb (det som faktiskt kan
  synas/förloras), uncalled_return_bb (= unmatched_bb, behålls för äldre skript), effective_bet_pct, draw_calc_status,
  unmatched_bb (2.73: den del av råbeloppet som inte kan matchas – vid syn det du mötte utöver din stack, vid bet det
  motståndaren inte kan syna; INTE en bokförd återbetalning – kan delvis ligga i en sidopott mellan andra),
  hand_returned_bb (faktisk återbetalning i handen enligt originaltexten "Uncalled bet … returned", tomt om texten saknas),
  hand_returned_to_hero (1 = återbetalningen gick till dig). raw_amount_bb är vid syn det belopp du MÖTTE, vid bet det
  du SATSADE. pot_at_decision_bb/pot_after_call_bb gäller i beslutsögonblicket – senare syner av andra ingår inte
  (slutpotten finns i hands.csv pot_bb). Se METOD_{version}.txt.
  OBS 2.71: to_call_bb, facing_pct och facing_size_pct räknas nu på EFFEKTIVT belopp (högst din stack).
night_hands.csv – (bara om du kört 🌙 Nattberäkningen) en rad per postflop-beslut: hand_id, street, order, nut_outs
  (kort som ger dig nöten utan att para bordet, varje kort en gång), nut2_outs (näst bästa), pair_outs (kort som parar
  bordet), eq_pool (din equity mot poolens visade händer på samma gata, Monte Carlo), range_id (vilken range-version).
night2_hands.csv – (bara efter 🌙 nattberäkning v2) en rad per heads-up-beslut: eq_v2 (din equity mot rangen från poolens
  frekvenser per linje, Monte Carlo till medelfel ≤ 0,5 pe), se_v2, luck_bb_hand (turjustering för hela handen: pott ×
  equityändring vid nya kort). HYPOTES – används bara om night2_acceptans.json visar status "godkänd".
preflop_context.csv – en rad per hand: opener_pos, opener_id (anonymt id, "hero" = du), open_size_bb, limpers,
  callers_before_hero, threebettor_pos, players_to_flop, pot_type, hero_opened.
opponents.csv – en rad per motståndare och hand: hand_id, opp_id (anonymt id – samma spelare får samma id i alla
  dina exporter, men namnet går inte att få fram), pos, vpip, pfr, to_flop, showed. Med den går det att räkna
  motståndarnas VPIP/PFR och se hur du går mot tighta och lösa spelare.
stakes.csv – resultat per nivå (all-in EV per 100 händer med felmarginal, VPIP)
sessions.csv – en rad per session (ny session efter mer än 30 min paus)
hourly_summary.csv – timlön exakt som appen räknar: total, per nivå (timmar överlappar – summera inte), vecka, session
METOD_{version}.txt – begrepp, estimand, klustring och vad som INTE får tolkas som bevis
rules.json – dina sparade regler med undantag och undergrupper

Stora tabeller är uppdelade i delar på högst 20 MB (t.ex. hands_del1.csv, hands_del2.csv), så att varje fil går
att ladda upp i chatten. Varje del har samma rubrikrad; ladda upp alla delar.
"""


PART_MAX = 20_000_000  # byte: större tabeller delas upp (uppladdning i chatten tillåter högst 30 MB per fil)


def split_csv(name: str, data: bytes, limit: int | None = None) -> dict:
    """Dela en CSV-fil i delar under limit byte. Varje del börjar med rubrikraden.
    hands.csv -> hands_del1.csv, hands_del2.csv …"""
    limit = limit or PART_MAX
    if len(data) <= limit:
        return {name: data}
    head, _, body = data.partition(b"\n")
    head += b"\n"
    parts, cur, size = [], [], len(head)
    for line in body.splitlines(keepends=True):
        if cur and size + len(line) > limit:
            parts.append(head + b"".join(cur))
            cur, size = [], len(head)
        cur.append(line)
        size += len(line)
    if cur:
        parts.append(head + b"".join(cur))
    stem = name[:-4] if name.endswith(".csv") else name
    return {f"{stem}_del{i}.csv": p for i, p in enumerate(parts, 1)}


def _ui_json(obj, **kw):
    from .positions import to_ui
    return to_ui(json.dumps(obj, **kw))


def _csv(rows, header) -> bytes:
    from .positions import to_ui
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows([[to_ui(c) for c in r] for r in rows])  # 2.74: positionen HJ heter UTG i exporten
    return buf.getvalue().encode("utf-8")


def _f(x, d=3):
    return "" if x is None or x != x else round(float(x), d)


def build_zip(st, rules_doc, sel_text: str = "", version: str = "", db=None, hero: str | None = None,
              progress=None, extra_files: dict | None = None) -> bytes:
    from .cards import CATEGORY_NAMES, card_str
    from .facts import decode_cards, dt_of
    from .practice import broke_mask, first_rows, violation_index
    from .sessions import session_bounds, session_table
    from .subgroups import STRUCT, struct_codes
    ft = st.ft
    H = ft.H
    r = np.asarray(st.rows, dtype=np.int64)
    r = r[np.argsort(H["ts"][r], kind="stable")]
    ts = H["ts"][r]
    starts = session_bounds(ts)
    sess_no = np.zeros(ft.n, np.int64)
    sess_no[r] = np.repeat(np.arange(1, len(starts) + 1), np.diff(np.r_[starts, len(r)]))
    struct = struct_codes(H["feats"][r]) if len(r) else np.zeros(0, np.int8)
    st_names = {"preflop": "preflop", 0: "preflop", 1: "flop", 2: "turn", 3: "river"}
    la = {0: "ingen", 1: "hero", 2: "annan"}
    hph_now = (np.searchsorted(ts, ts + 900, side="right") - np.searchsorted(ts, ts - 900, side="left")) * 2 if len(ts) else ts
    rows = []
    for k, j in enumerate(r.tolist()):
        hole = decode_cards(H["hole"][j])
        q = [n for n, v in zip(("högt par", "suited ess", "rundown"), (H["hp"][j], H["sa"][j], H["rd"][j])) if v]
        cat = int(H["cat"][j])
        ai = int(H["ai_st"][j])
        fs = int(H["fold_st"][j])
        rows.append([
            str(H["id"][j]), dt_of(int(H["ts"][j])).strftime("%Y-%m-%d %H:%M:%S"), int(sess_no[j]),
            ft.label("stake", int(H["stake"][j])), int(H["nh"][j]), int(H["nplay"][j]),
            "rush" if H["ttype"][j] else "vanligt", int(bool(H["strad"][j])) if "strad" in H else "",
            ft.label("pos", int(H["pos"][j])),
            " ".join(card_str(c) for c in sorted(hole, key=lambda c: (-c[0], c[1]))),
            len(q), "+".join(q) or "ingen", STRUCT[int(struct[k])],
            ft.label("bucket", int(H["bucket"][j])) if H["bucket"][j] >= 0 else "",
            _f(H["net"][j]), _f(H["ev"][j]), _f(H["money"][j], 2), _f(H["ev_m"][j], 2), _f(H["rake"][j]),
            _f(H["pot"][j], 2), int(bool(H["vpip"][j])), st_names.get(ai, "") if ai >= 0 else "",
            _f(H["ai_eq"][j]) if ai >= 0 else "", int(bool(H["sd"][j])), int(bool(H["won"][j])),
            st_names.get(fs, "") if fs >= 0 else "", CATEGORY_NAMES.get(cat, "") if cat >= 0 else "",
            la.get(int(H["la"][j]), ""), _f(H["ic"][j], 2), _f(H["ia"][j], 2), int(hph_now[k])])
    files = {"hands.csv": _csv(rows, [
        "hand_id", "time", "session", "stake", "cards", "players", "table", "straddle", "pos", "hole", "nut_n", "nut", "struct",
        "start_bucket", "net_bb", "ev_bb", "money", "ev_money", "rake_bb", "pot_bb", "vpip", "allin_street",
        "allin_eq", "showdown", "won", "fold_street", "final_hand", "last_aggressor", "put_in_calls_bb",
        "put_in_bets_bb", "hands_per_hour_now"])}
    # preflop-beslut med regelbrott
    pre = st.decisions.pre
    rules = (rules_doc or {}).get("rules") or []
    if pre.ft is not None and len(pre):
        vi = violation_index(rules, pre) if rules else np.full(len(pre), -1)
        first = first_rows(pre)
        played = broke_mask(rules, pre, vi) if rules else ~np.isnan(pre.delta)
        prow = []
        order = np.argsort(H["ts"][pre.hidx], kind="stable")
        for j in order.tolist():
            v = int(vi[j])
            hit = v >= 0 and first[j] and played[j]
            prow.append([str(H["id"][pre.hidx[j]]), pre.label("spot", pre.spot[j]), pre.label("pos", pre.pos[j]),
                         pre.label("kind", pre.kind[j]), _f(pre.delta[j]), int(first[j]),
                         rules[v]["title"] if hit else "", rules[v].get("level", "bekräftad") if hit else ""])
        files["preflop.csv"] = _csv(prow, ["hand_id", "spot", "pos", "action", "vs_fold_bb", "first", "rule", "rule_level"])
    mask = np.zeros(ft.n, bool)
    mask[r] = True
    T = ft.t.get("trn")
    if T is not None and len(T["hidx"]):
        m = np.flatnonzero(ft.subset_mask(mask, "trn"))
        files["turn_calls.csv"] = _csv(
            [[str(H["id"][T["hidx"][i]]), ft.label("tstr", int(T["str"][i])), _f(T["delta"][i]),
              ft.label("path", int(T["path"][i]))] for i in m], ["hand_id", "strength", "vs_fold_bb", "river"])
    R = ft.t.get("riv")
    if R is not None and len(R["hidx"]):
        m = np.flatnonzero(ft.subset_mask(mask, "riv"))
        files["river.csv"] = _csv(
            [[str(H["id"][R["hidx"][i]]), ft.label("size", int(R["size"][i])), ft.label("rstr", int(R["str"][i])),
              ft.label("kind", int(R["kind"][i])), _f(R["delta"][i])] for i in m],
            ["hand_id", "bet_size", "strength", "action", "vs_fold_bb"])
    T = session_table(st, rules_doc, limit=None)
    srows = [[n + 1, s["start"], s["end"], s["minutes"], s["hands"], _f(s["net"]), _f(s["ev"]), _f(s["money"], 2),
              _f(s["ev_money"], 2), s["opps"], s["dev"], _f(s["follow"], 1), _f(s["base_follow"], 1),
              _f(s["exp_cost"], 2), s["verdict"]["text"]]
             for n, s in enumerate((T or {}).get("sessions", [])[::-1])]
    if db is not None and hero:
        from .postflop_rows import CTX_HEADER, HEADER, OPP_HEADER, iter_all
        ids = [str(x) for x in H["id"][r]]
        ev_of = dict(zip(ids, (float(x) for x in H["ev"][r])))
        post, ctx, opp = [], [], []
        dest = {"post": post, "ctx": ctx, "opp": opp}
        for kind, row in iter_all(db, ids, hero, progress, ev_of, salt=_salt()):
            dest[kind].append(row)
        files["postflop.csv"] = _csv(post, HEADER)
        files["preflop_context.csv"] = _csv(ctx, CTX_HEADER)
        files["opponents.csv"] = _csv(opp, OPP_HEADER)
        try:
            from .night import NIGHT_HEADER, export_rows
            nrows = export_rows(db, ids)
            if nrows:
                files["night_hands.csv"] = _csv(nrows, NIGHT_HEADER)
        except Exception:
            pass
        try:
            from .night2 import NIGHT2_HEADER, export_rows as export2, meta_get
            n2 = export2(db, ids)
            if n2:
                files["night2_hands.csv"] = _csv(n2, NIGHT2_HEADER)
            acc = meta_get(db.con, "acceptance")
            if acc:
                files["night2_acceptans.json"] = _ui_json(acc, ensure_ascii=False, indent=1, default=str).encode("utf-8")
        except Exception:
            pass
    try:
        from .hourly import HOURLY_HEADER, hourly_summary_rows
        hrows = hourly_summary_rows(st)
        if hrows:
            files["hourly_summary.csv"] = _csv(hrows, HOURLY_HEADER)
    except Exception:
        pass
    from . import __version__ as _ver  # 2.83: filnamn och rubrik följer programversionen
    files[f"METOD_{_ver}.txt"] = METOD.encode("utf-8")
    files.update(extra_files or {})
    files["sessions.csv"] = _csv(srows, ["session", "start", "end", "minutes", "hands", "net_bb", "ev_bb", "money",
                                         "ev_money", "rule_opps", "rule_breaks", "follow_pct", "follow_pct_before",
                                         "expected_cost_bb", "verdict"])
    files["rules.json"] = _ui_json({k: v for k, v in (rules_doc or {}).items()}, ensure_ascii=False,
                                     indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)).encode("utf-8")
    files["LÄS_MIG.txt"] = README.format(sel=sel_text or "hela urvalet", created=datetime.now().strftime("%Y-%m-%d %H:%M"),
                                         version=version).encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in files.items():
            for n2, d2 in (split_csv(name, data) if name.endswith(".csv") else {name: data}).items():
                z.writestr(n2, d2)
    return out.getvalue()


METOD = """Version 2.83 – metod och begrepp (maskinläsbar sammanfattning)
ESTIMAND: net = faktiskt utfall; ev = all-in-justerat utfall (bara modellerbara all-ins ersätts); vs_fold_bb/from_here_bb =
  observerat utfall i den spelade handen relativt fold – INTE kontrafaktiskt beslut-EV. AI-förslag är hypoteser.
KLUSTRING: postflop.csv har flera beslut per hand (beroende utfall). Klustra standardfel på hand_id; för slutsatser som
  ska gälla framåt, klustra på session. Rapportera antal beslut, unika händer och sessioner separat.
PRIS (2.71): to_call_bb = effektiv syn (högst Heros kvarvarande stack). raw_amount_bb = råbelopp (syn eller bet),
  effective_risk_bb = det som faktiskt kan förloras/synas, unmatched_bb (= uncalled_return_bb) = det som inte kan matchas –
  inte bokförd återbetalning; hand_returned_bb = faktisk återbetalning i handen (originaltexten).
  pot_at_decision_bb/pot_after_call_bb/facing_pct/facing_size_pct räknas på den pott Hero kan vinna.
  effective_bet_pct = Heros bet/höjning i % av potten räknat på effektiv risk; size_pct = råstorlek.
  pot_bb/spr = gatans start (kompatibilitet). spr_after_call = beslutstid.
OUTS: draw_outs = unika kort som ger stege/färg nästa gata; nut_outs = kort där ingen möjlig motståndarhand slår dig
  på nästa gata. Inte equity mot en range. draw_calc_status: computed / zero_outs / no_qualifying_draw /
  made_hand_not_evaluated / river / light_export / not_computed. Tomt outsfält är aldrig samma sak som noll.
POSITION: players = kvar i potten inkl. all-in; ip = sist bland dem som kan agera.
TIMLÖN: hourly_summary.csv = samma beräkning som appens Timlön-vy. Nivåtimmar överlappar i pass med flera nivåer
  (mixed_stakes=1, rad 'overlap') och får inte summeras. Rakeback ingår inte (rakeback=exkluderad).
REGLER: riktlinjer är frysta 2026-11-13. Bara händer efter frysdatum räknas som oberoende test (framåttest i rules.json /
  appen). Allt före frysdatum är historiskt underlag, inte bekräftelse.
RIVER-COACH: hypotes från selekterade showdownhänder, inte strategifacit. Bets räknas på effektiv risk.
NATT V2 (2.73, modellversion 3): range = band i poolens frekvenser per linje (gata × mötte × IP/OOP × nivå, fryst på händer
  före 2026-11-13, hopslagning vid < 300 beslut), kedjat gata för gata; λ (0–0,5) låst på all-ins före frysdatum – en
  modellparameter, inte poolens uppmätta bluffandel. Preflop antas slumpade händer. Monte Carlo-felet är inte modellfelet.
  Acceptansplan 2.73/2026-11-14 (ersätter 2.72 efter extern granskning; två pass efter frysdatum hade då setts): avläsning
  bara vid 20, 40 och 80 spelpass efter frysdatum (de första K passen), kritiskt värde justerat för tre avläsningar.
  Krav: (1) lägre MSE än v1 OCH prognos − faktisk all-in-equity inom ±5 pe med intervall; (2) lägre Brier än poolens
  totala fold-andel OCH prognos − faktisk inom ±10 pe (prövar linjefrekvenserna, inte hela rangemodellen);
  (3) ekvivalenstest: turmedel inom ±0,05 bb/hand, OCH minst 20 % lägre varians än all-in EV. Första avgörandet är slutligt.
  eq_pool (v1) är INTE en försiktig skattning mot all-in: i lägen där du möter all-in med drag låg den ~9 pe över faktisk
  all-in-equity (2026-11-14, 820 händer).
RIVER-BLUFF-TEST (2.73): randomiserat med sekundvisaren (jämn = pott, udda = check) från 2026-11-14 (handtid). Fold-andelen
  räknas bara på pott-bets (effektiv storlek ≥ 85 %); jämförelsen är pott-bet mot check. Avläsning bara vid 300 och 500
  lägen; grönt slutbesked kräver ≥ 60 lägen per arm, bet-andel 35–65 %, ≥ 20 pass och skattad skillnad. Stopp vid fold < 62 %
  vid en avläsning, eller när som helst om hela 95 %-intervallet ligger under 51 % (säkerhetsstopp).
POSTFLOP-FRAMÅTTEST: riktlinje = situation + rekommenderad handling, mätt bara efter frysdatum; definitionerna låsta
  2026-11-14 (fingeravtryck i appen och morgonrapporten). Jämförelsen följde/följde inte är observationell (du väljer
  själv) – "håller framåt" är riktning, inte kausalt bevis. Minimiantal räknas på beslut med känt utfall (2.73).
NIVÅER (2.73): "bekräftad" = den frysta regeln håller i framåttestet OCH dagens regel har samma definition. Allt annat är
  "trolig" eller hypotes. Postflop-fokus (river-bluffen) är en hypotes med uppskattad kostnad, inte bekräftad.
  #5 (drag mot all-in): en fold markeras bara för granskning – inget syn-råd och ingen kostnad.
POSITIONER (2.74): GG PLO6 är 5-max: UTG (första efter BB), CO, BTN, SB, BB. Internt och i de frysta reglerna heter
  UTG fortfarande HJ (så att framåttestets definitioner inte ändras) – i alla filer och på skärmen står UTG.
HYPOTESER (2.75): H1 BTN öppna bara topp 30 %, H2 SB/BB folda 0 nöt mot öppning i stället för syn, H3 rundown utan suited ess
  syna i stället för 3-bet. Frysta 2026-11-15 (fingeravtryck e4e93fbb9face71d), mäts bara efter det datumet, mot fold; aldrig
  regelbrott. H1:s handstyrka = frysta vikter, percentil mot slumpade händer.
WINRATE-KURVA (2.75): förväntat resultat mot fold vid "öppna topp X %" = summan av 5 %-bandens medel × bandets andel. Band där
  spelaren öppnat < 50 % av händerna är urvalspåverkade (för höga) och ingår inte när toppen söks.
RUNDOWN: fyra valörer inom fem steg, högst en lucka, alla ≥ 5 (t.ex. 9-8-7-6 eller 9-8-7-5).
TID (2.73): frysdatum och teststart räknas i handtid (samma som hands.csv time), inte i datorns tidszon.
SOLVER (2.76/2.81): jämförelsen mot en preflopsolver visas i programmet (Solver-sidan, dold när GG körs). Solverns
  frekvenser ingår aldrig i den här exportens tabeller eller i delning. Sessionsfilen (session.md) innehåller däremot
  solverns frekvens per preflopbeslut och "klara fel" (Andreas val 2026-11-18).
SVANSVAKT: "osäkert (svansvakt)" = intervallet under noll men färre än 5 resultat över +10 bb – försiktighetsregel.
BETSTORLEK: bsz = första bet per gata, effektiv storlek; break-even = b/(b+1−rake) gäller en REN bluff (0 equity vid syn,
  checkens värde 0, ingen fortsatt action); mot en check med värde C krävs fold > (B+C)/(P−F+B). Poolens fold-andel är
  inte fold-andelen mot just dina bluffar. Rake 5 % med tak skattat ur händerna (ingen verifierad avgiftstabell).
RIVER-COACH: bets värderas som bet/fold (alltid fold mot check-raise) – undervärderar bets med mycket starka händer.
"""
from . import __version__ as _V  # noqa: E402 – 2.84: rubriken följer alltid programversionen
METOD = METOD.replace("Version 2.83", "Version " + _V, 1)



def _salt() -> str:
    """Slumpat salt för motståndarnas anonyma id, sparat så att samma motståndare får samma id i alla exporter."""
    import os
    import secrets
    from pathlib import Path
    d = Path(os.environ.get("PLO_LEAK_CACHE", Path.home() / ".plo_leak_cache"))
    p = d / "anon_salt.txt"
    try:
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
        d.mkdir(parents=True, exist_ok=True)
        s = secrets.token_hex(16)
        p.write_text(s, encoding="utf-8")
        return s
    except OSError:
        return "plo"


def stakes_csv(S) -> bytes:
    rows = [[x["stake"], x["hands"], _f(x["ev100"], 2), _f(x["se100"], 2), _f(x.get("raw100", x["ev100"]), 2), _f(x["vpip"], 1),
             _f(x["rake100"], 2), x.get("verdict", "")] for x in (S or {}).get("rows", [])]
    return _csv(rows, ["stake", "hands", "ev_bb100_utan_regelbrott", "se_bb100", "ev_bb100", "vpip_pct", "rake_bb100", "verdict"])
