from pathlib import Path

from plo_leak.cards import best_omaha, classify_start, nut_rank, parse_cards
from plo_leak.parser import load_paths
from plo_leak.stats import analyze

HERE = Path(__file__).parent


def test_parser_amounts_and_positions():
    hands = load_paths([HERE / "sample_gg.txt"])
    assert len(hands) == 2
    h = hands[0]
    assert h.positions["Hero"] == "HJ" and h.positions["9z9z9z"] == "BB"
    assert round(h.invested["Hero"], 2) == 50.0
    assert round(h.net("Hero"), 2) == 50.95
    assert h.went_to_showdown()
    h2 = hands[1]
    assert round(h2.net("Hero"), 2) == -0.5
    assert round(h2.net("f9e8d7"), 2) == 1.25  # 1.75 vunnet - 0.5 investerat (2 returnerades)


def test_omaha_must_use_two_hole_cards():
    # fyra hjärter på bordet + ett hjärter på handen ger INTE färg i Omaha
    hole = parse_cards("Ah Kd Qc Js")
    board = parse_cards("2h 5h 8h Th 3c")
    assert best_omaha(hole, board)[0] != 5


def test_nut_rank():
    board = parse_cards("Kh 7h 2c 9s 3h")
    assert nut_rank(parse_cards("Ah Kd Js Th"), board)[0] == 0  # nötfärg
    assert nut_rank(parse_cards("Qh Jh 5c 5d"), board)[0] > 0


def test_plo6_classification():
    assert classify_start(parse_cards("As Ks Qd Jd Th 9h"))["bucket"] == "Suited ess + rundown"
    assert classify_start(parse_cards("9c 8c 7c 6c 5d 4h"))["weak"]
    assert classify_start(parse_cards("Kd Qs 8c 5h 3d 2c"))["weak"]


def test_stats_on_sample():
    st = analyze(load_paths([HERE / "sample_gg.txt"]))
    assert st.hands == 2
    assert st.s["vpip"].hits == 2
    assert st.s["open_limp"].hits == 1
    assert st.s["fold_to_3bet"].opps == 1 and st.s["fold_to_3bet"].hits == 0


def test_drivehud_export_without_extension():
    from plo_leak.parser import detect_hero, filter_variant
    hands = load_paths([HERE / "sample_gg.txt", HERE / "drivehud_export"])  # hittar även dh_exported_file_0 utan filändelse
    assert len(hands) == 3
    plo6, note = filter_variant(hands)
    # två PLO4-händer och en PLO6-hand: vanligaste varianten (PLO4) väljs automatiskt
    assert len(plo6) == 2 and "PLO6: 1" in note
    only6, _ = filter_variant(hands, "PLO6")
    assert detect_hero(only6) == "Andreas_PLO"
    assert round(only6[0].net("Andreas_PLO"), 2) == 1.83


def test_missing_fold_line_is_inferred():
    # GG/DriveHUD-historik kan sakna "Hero: folds" – folden ska ändå räknas
    hands = load_paths([HERE / "extra" / "missing_fold.txt"])
    h = hands[0]
    assert h.bb == 2 and ("Hero", "preflop") in h.inferred
    assert not h.went_to_showdown()
    st = analyze(hands, "Hero")
    assert st.s["fold_to_3bet"].opps == 1 and st.s["fold_to_3bet"].hits == 1
    assert round(h.net("Hero"), 2) == -7


def test_results_can_overrule_benchmark():
    # Användarens riktiga fall: foldar sällan mot 3-bet, men att fortsätta (-1.4 bb)
    # slår att folda (-3.5 bb) med god marginal -> ska nedgraderas, inte vara "Stor läcka".
    import random
    from plo_leak.leaks import PROFILES, RULES, _rule_leak
    from plo_leak.stats import Stat

    class H:
        id = "x"
    rnd = random.Random(1)
    s = Stat(keep=False)
    for _ in range(280):
        s.add(H, True, -3.5)
    for _ in range(6700):
        s.add(H, False, rnd.gauss(-1.4, 25))
    rule = next(r for r in RULES if r["stat"] == "fold_to_3bet")
    lk = _rule_leak(rule, s, PROFILES["PLO6"])
    assert lk is not None and "troligen INTE en läcka" in lk.spot_note and lk.level != "Stor"


def test_real_gg_plo6_hands_balance():
    # 95 anonymiserade riktiga GG PLO6-händer (straddles, EV cashout, run it twice,
    # korrupta blindbelopp). Insatt = vunnet + avgifter + cashout-premie i varje hand.
    import re
    hands = load_paths([HERE / "real" / "gg_plo6_samples.txt"])
    assert len(hands) == 95
    for h in hands:
        cash = sum(float(x) for x in re.findall(r": Pays Cashout Risk \(\$([\d.]+)\)", h.raw))
        diff = sum(h.invested.values()) - sum(h.collected.values()) - h.rake - cash
        assert abs(diff) < 0.02, (h.id, diff)
        assert not h.inferred, h.id
        assert h.bb in (1.0, 2.0)


def test_call_3bet_oop_not_flagged_when_results_dont_support_it():
    # Andreas fall: syn OOP -3.11 bb/hand (2070 ggr) mot fold -3.5 bb -> inte belagt, ska nedgraderas
    import random
    from plo_leak.leaks import PROFILES, RULES, _rule_leak
    from plo_leak.stats import Stat

    class H:
        id = "x"
    rnd = random.Random(2)
    call, fold = Stat(keep=False), Stat(keep=False)
    for _ in range(2070):
        call.add(H, True, rnd.gauss(-3.11, 45))
    for _ in range(425):
        call.add(H, False, 0)
    for _ in range(300):
        fold.add(H, True, -3.5)
    rule = next(r for r in RULES if r["stat"] == "call_3bet_oop")
    lk = _rule_leak(rule, call, PROFILES["PLO6"], {"fold_3bet_oop": fold})
    assert lk is not None and "belägger inte" in lk.spot_note and lk.level == "Liten"


def test_allin_ev_real_hand_and_side_pots():
    from plo_leak.ev import _pots, allin_ev, equities
    from plo_leak.cards import parse_cards
    hands = {h.id: h for h in load_paths([HERE / "real" / "gg_plo6_samples.txt"])}
    ev, eq, street = allin_ev(hands["OM89856699"], "Hero")
    assert street == "flop" and 0.30 < eq < 0.40  # made straight vs two pair + massor av outs
    # sidopotter: A all-in 10, B och C 30 vardera, D foldade efter 5
    pots = _pots({"A": 10, "B": 30, "C": 30, "D": 5}, {"A", "B", "C"})
    assert pots[0] == (35, ["A", "B", "C"]) or sorted(pots[0][1]) == ["A", "B", "C"]
    assert abs(sum(p[0] for p in pots) - 75) < 1e-9
    # identiska händer i olika färger på ett bord utan färgmöjlighet -> 50/50
    e = equities({"a": parse_cards("Ah Kh Qd Jd Tc 9c"), "b": parse_cards("As Ks Qc Jc Th 9h")},
                 parse_cards("2d 3s 7h 8c"))
    assert abs(e["a"] - 0.5) < 1e-9


def test_strict_engine_only_reports_proven_losses():
    from plo_leak.decisions import Decisions, Group, proven_leaks
    import random
    rnd = random.Random(5)
    d = Decisions()
    # klar förlust jämfört med fold: ska rapporteras
    for i in range(400):
        d.groups[("rfi", "HJ", "Svag struktur", "raise")].add(rnd.gauss(-2.0, 8), f"a{i}")
    # liten/osäker förlust: ska INTE rapporteras
    for i in range(400):
        d.groups[("rfi", "CO", "Suited ess", "raise")].add(rnd.gauss(-0.2, 8), f"b{i}")
    # för litet urval: ska INTE rapporteras
    for i in range(60):
        d.groups[("rfi", "BTN", "Svag struktur", "raise")].add(-5.0 + rnd.gauss(0, 1), f"c{i}")
    out = proven_leaks(d, 100000)
    keys = {(x["pos"], x["bucket"]) for x in out}
    assert ("HJ", "Svag struktur") in keys
    assert ("CO", "Suited ess") not in keys and ("BTN", "Svag struktur") not in keys
    assert all(x["p_b"] <= 0.05 and x["mean"] <= -0.3 for x in out)


def test_board_table_matches_exact_reference():
    import random
    from plo_leak.board import BoardTable
    from plo_leak.cards import SUITS, nut_rank
    deck = [(r, s) for r in range(2, 15) for s in SUITS]
    rnd = random.Random(9)
    for _ in range(25):
        rnd.shuffle(deck)
        board, hole = deck[:5], deck[5:11]
        beats, total = nut_rank(hole, board)
        assert abs(BoardTable(board).beat_frac(hole) - beats / total) < 1e-12


def test_river_extract_real_hand():
    from plo_leak.river import extract
    hands = {h.id: h for h in load_paths([HERE / "real" / "gg_plo6_samples.txt"])}
    s = extract(hands["OM89894742"], "Hero")
    assert s["kind"] == "bet" and s["role"] == "ip_bet" and s["bettor"] == "Hero"
    # 2.71: betten räknas på effektiv risk (motståndaren hade bara 64,5 bb kvar), råbeloppet sparas separat
    assert abs(s["pot"] - 72) < 1e-9 and abs(s["bet"] - 64.5) < 1e-9 and abs(s["raw_bet"] - 72) < 1e-9 and s["response"] == "fold"
    assert s["line"] == "motståndaren"  # motståndaren bettade turn


def test_river_model_end_to_end_on_synthetic_pool(tmp_path):
    import sys
    sys.path.insert(0, str(HERE.parent / "tools"))
    from generate_sample import Table
    from plo_leak.parser import parse_text
    from plo_leak.river import analyze_river
    t = Table(3)
    hands = parse_text("\n\n\n".join(t.play() for _ in range(12000)))
    r = analyze_river(hands, "Hero", len(hands))
    assert r.summary["hero_decisions"] > 300
    cal = r.calibration["syn mot river-bet"]
    assert cal["n"] > 100 and abs(cal["pred"] - cal["actual"]) < 0.06  # modellen ska stämma i snitt


def test_river_spot_knows_low_spr_in_4bet_pot():
    # Andreas exempelhand: 4-bet-pott, 157 kvar bakom i en pott på 270 -> låg SPR.
    # Utan SPR trodde modellen att poolen foldar lika ofta som i små pottar.
    from plo_leak.river import extract
    h = load_paths([HERE / "real" / "user_hand_4bet_pot.txt"])[0]
    s = extract(h, "Hero")
    assert s["kind"] == "checkthrough" and s["hero_role"] == "ip"
    assert abs(s["pot"] - 270) < 1e-9 and abs(s["eff"] - 157.36) < 0.01
    assert s["spr"].startswith("låg")


# ---------------------------------------------------------------- v1.3: regressionstester för granskningens fynd
def _hh(body: str, header="Poker Hand #T{n}: PLO-6 ($0.5/$1) - 2026/09/26 09:00:52", n=1):
    from plo_leak.parser import parse_hand
    return parse_hand(header.format(n=n) + "\n" + body.strip())


SEATS5 = """Table 'T' 5-max Seat #2 is the button
Seat 1: A ($100 in chips)
Seat 2: B ($100 in chips)
Seat 3: C ($100 in chips)
Seat 4: Hero ($100 in chips)
Seat 5: E ($100 in chips)
"""


def test_p1_p2_cashout_not_counted_as_pot_or_win():
    from plo_leak.ev import allin_ev
    h = _hh(SEATS5 + """C: posts small blind $0.5
Hero: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
E: folds
A: folds
B: folds
C: raises $99.5 to $100 and is all-in
Hero: calls $99 and is all-in
Hero: Pays Cashout Risk ($10)
C: shows [7s 6s 5d 4d 9h 8h]
*** FLOP *** [2s 3s Td]
*** TURN *** [2s 3s Td] [Jc]
*** RIVER *** [2s 3s Td Jc] [Qs]
*** SHOWDOWN ***
C collected $197 from pot
Hero: Receives Cashout ($60)
*** SUMMARY ***
Total pot $200 | Rake $3 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
""")
    assert h.contrib("Hero") == 100 and h.collected.get("Hero", 0) == 0
    assert abs(h.net("Hero") - (60 - 110)) < 1e-9
    ev, eq, street = allin_ev(h, "Hero", samples=400)
    assert street == "preflop"
    # EV mäts mot det hero lagt i potten (100), inte inklusive premien (110)
    assert abs(ev - (eq * 197 - 100)) < 1e-6


def test_p6_short_allin_sb_does_not_set_stakes():
    h = _hh("""Table 'T' 5-max Seat #2 is the button
Seat 1: A ($100 in chips)
Seat 2: B ($100 in chips)
Seat 3: C ($0.2 in chips)
Seat 4: Hero ($100 in chips)
Seat 5: E ($100 in chips)
C: posts small blind $0.2 and is all-in
Hero: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
E: folds
A: folds
B: folds
*** SUMMARY ***
""")
    assert h.bb == 1.0 and not h.corrupt
    assert h.invested["Hero"] == 1.0


def test_p8_no_sb_label_without_sb_post():
    h = _hh(SEATS5 + """Hero: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
E: folds
A: folds
B: folds
C: folds
*** SUMMARY ***
""")
    assert "SB" not in h.positions.values()
    assert h.positions["Hero"] == "BB"


def test_p5_straddle_option_check_is_not_an_open():
    from plo_leak.stats import analyze
    h = _hh(SEATS5 + """C: posts small blind $0.5
Hero: posts big blind $1
E: straddle $2
*** HOLE CARDS ***
Dealt to E [As Ad Kh Kd 2c 3c]
A: calls $2
B: folds
C: folds
Hero: folds
E: checks
*** FLOP *** [2s 3s Td]
E: checks
A: checks
*** TURN *** [2s 3s Td] [Jc]
E: checks
A: checks
*** RIVER *** [2s 3s Td Jc] [Qs]
E: checks
A: checks
*** SUMMARY ***
""")
    st = analyze([h], "E")
    assert st.s["rfi"].opps == 0 and st.s["overlimp"].opps == 0
    assert sum(g.n for k, g in st.decisions.groups.items() if k[0] in ("rfi", "efter_limp")) == 0


def test_p9_short_allin_raise_is_not_a_3bet():
    from plo_leak.stats import analyze
    h = _hh("""Table 'T' 5-max Seat #2 is the button
Seat 1: A ($100 in chips)
Seat 2: B ($3.5 in chips)
Seat 3: C ($100 in chips)
Seat 4: Hero ($100 in chips)
Seat 5: E ($100 in chips)
C: posts small blind $0.5
Hero: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
E: folds
A: raises $2 to $3
B: raises $0.5 to $3.5 and is all-in
C: folds
Hero: calls $2.5
A: calls $0.5
*** FLOP *** [2s 3s Td]
Hero: checks
A: checks
*** TURN *** [2s 3s Td] [Jc]
Hero: checks
A: checks
*** RIVER *** [2s 3s Td Jc] [Qs]
Hero: checks
A: checks
*** SUMMARY ***
""")
    st = analyze([h], "Hero")
    assert st.s["cold_call_3bet"].opps == 0
    assert st.s["bb_defend"].opps == 1
    assert any(k[0] == "bb_mot_hojning" for k in st.decisions.groups)


def test_p4_facing_raise_after_own_bet_is_not_facing_a_bet():
    from plo_leak.stats import analyze
    h = _hh(SEATS5 + """C: posts small blind $0.5
Hero: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
E: folds
A: folds
B: raises $2 to $3
C: folds
Hero: calls $2
*** FLOP *** [2s 3s Td]
Hero: checks
B: checks
*** TURN *** [2s 3s Td] [Jc]
Hero: bets $4
B: raises $12 to $16
Hero: folds
*** SUMMARY ***
""")
    st = analyze([h], "Hero")
    assert st.s["fold_turn_bet"].opps == 0
    assert not any(k[0] == "turn_mot_bet" for k in st.decisions.groups)
    assert st.decisions.folds.get(("turn_mot_bet", "alla", "alla"), 0) == 0 and \
        not any(k[0] == "turn_mot_bet" for k in st.decisions.folds)


def test_p7_allin_ev_uses_heros_allin_street():
    from plo_leak.ev import allin_ev
    h = _hh("""Table 'T' 5-max Seat #2 is the button
Seat 1: A ($200 in chips)
Seat 2: B ($200 in chips)
Seat 3: C ($200 in chips)
Seat 4: Hero ($20 in chips)
Seat 5: E ($100 in chips)
C: posts small blind $0.5
Hero: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
E: folds
A: raises $2 to $3
B: calls $3
C: folds
Hero: raises $17 to $20 and is all-in
A: calls $17
B: calls $17
*** FLOP *** [2s 3s Td]
A: bets $30
B: calls $30
*** TURN *** [2s 3s Td] [Jc]
A: checks
B: checks
*** RIVER *** [2s 3s Td Jc] [Qs]
A: checks
B: checks
A: shows [7s 6s 5d 4d 9h 8h]
B: shows [7c 6c 5h 4h 9d 8d]
*** SHOWDOWN ***
*** SUMMARY ***
""")
    r = allin_ev(h, "Hero", samples=300)
    assert r is not None and r[2] == "preflop"


def test_null_data_gives_no_confirmed_leaks():
    """Ingen läcka finns (snedfördelade resultat med medel 0): motorn ska vara tyst nästan alltid."""
    import numpy as np
    from plo_leak.decisions import Decisions, proven_leaks
    rng = np.random.default_rng(3)
    false_runs = 0
    for run in range(20):
        d = Decisions()
        for gi in range(40):
            n = int(rng.integers(150, 1500))
            # högerskev: ofta små förluster, ibland stora vinster – medel exakt 0
            x = np.where(rng.random(n) < 0.1, rng.exponential(18, n), -rng.exponential(2, n))
            x = x - (0.1 * 18 - 0.9 * 2)
            for i, v in enumerate(x):
                d.groups[("rfi", f"P{gi % 5}", f"B{gi}", "raise")].add(float(v), f"r{run}g{gi}h{i}")
        false_runs += bool(proven_leaks(d, 100000))
    assert false_runs <= 2, false_runs


def test_all_blinds_allin_and_broken_header_does_not_crash():
    h = _hh("""Table 'T' 5-max Seat #1 is the button
Seat 1: P1 ($100 in chips)
Seat 2: P2 ($0.4 in chips)
Seat 3: Hero ($0.8 in chips)
P2: posts small blind $0.4 and is all-in
Hero: posts big blind $0.8 and is all-in
*** HOLE CARDS ***
Dealt to Hero [Ah Kh Qd Jd 9c 8c]
P1: calls $1
*** FLOP *** [2h 5h 9d]
*** TURN *** [2h 5h 9d] [Kc]
*** RIVER *** [2h 5h 9d Kc] [3s]
*** SHOWDOWN ***
Hero collected $2 from pot
*** SUMMARY ***
Total pot $2 | Rake $0 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
""", header="Poker Hand #HC10: PLO-6 ($1/$0) - 2026/06/01 13:01:00")
    assert h is None or h.bb > 0


def test_short_allin_in_straddled_pot_is_not_a_raise_level():
    from plo_leak.decisions import full_raise_flags
    h = _hh("""Table 'T' 5-max Seat #5 is the button
Seat 1: P1 ($100 in chips)
Seat 2: P2 ($100 in chips)
Seat 3: P3 ($100 in chips)
Seat 4: Hero ($100 in chips)
Seat 5: P4 ($6 in chips)
P2: posts small blind $0.5
P3: posts big blind $1
P3: straddle $2
Hero: straddle $4
*** HOLE CARDS ***
Dealt to Hero [Ah Kh Qd Jd 9c 8c]
P4: raises $2 to $6 and is all-in
P1: raises $14 to $20
P2: folds
P3: folds
Hero: folds
*** SUMMARY ***
""")
    flags = [full_raise_flags(h)[id(a)] for a in h.actions if a.kind == "raise"]
    assert flags == [False, True]


def test_raise_after_own_bet_goes_to_mot_raise_spot():
    from plo_leak.stats import analyze
    h = _hh(SEATS5 + """C: posts small blind $0.5
Hero: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
E: folds
A: folds
B: raises $2 to $3
C: folds
Hero: calls $2
*** FLOP *** [2s 3s Td]
Hero: bets $4
B: raises $12 to $16
Hero: calls $12
*** TURN *** [2s 3s Td] [Jc]
Hero: checks
B: checks
*** RIVER *** [2s 3s Td Jc] [Qs]
Hero: checks
B: checks
*** SUMMARY ***
""")
    st = analyze([h], "Hero")
    spots = {k[0] for k in st.decisions.groups}
    assert "flop_mot_raise" in spots and "flop_mot_bet" not in spots


def test_database_adds_only_new_hands_and_caches_results():
    import os
    import tempfile
    from plo_leak.db import HandDB, set_active
    from plo_leak.stats import analyze
    here = os.path.dirname(__file__)
    with tempfile.TemporaryDirectory() as td:
        db = HandDB(os.path.join(td, "t.db"))
        r1 = db.add_paths([os.path.join(here, "real")])
        assert r1["hands_new"] > 50
        n = db.count()
        r2 = db.add_paths([os.path.join(here, "real")])
        assert r2["hands_new"] == 0 and r2["files_skipped"] == r2["files"]
        assert db.count() == n
        hands = db.load()
        set_active(db.calc_cache())
        a = analyze(hands, "Hero")
        db.save_calc()
        set_active(db.calc_cache())
        b = analyze(db.load(), "Hero")
        set_active(None)
        assert abs(a.ev_net_bb - b.ev_net_bb) < 1e-9 and a.hands == b.hands
        assert len(db.load(date_from="2026-09-01")) < n
        db.close()


def test_latest_hands_picks_most_recent_by_time():
    import os
    from plo_leak.parser import load_paths, latest_hands
    hs = load_paths([os.path.join(os.path.dirname(__file__), "real")], use_cache=False)
    last = latest_hands(hs, "Hero", 10)
    mine = sorted((h for h in hs if "Hero" in h.seats), key=lambda h: (h.date, h.id))
    assert len(last) == 10 and [h.id for h in last] == [h.id for h in mine[-10:]]
    assert latest_hands(hs, "Hero", 0) is hs


def test_practice_rules_and_trainer():
    from plo_leak.cards import parse_cards
    from plo_leak.practice import trainer_hand, violations
    from plo_leak.ranges import FEATURE_NAMES
    w = [0.0] * len(FEATURE_NAMES)
    w[0] = 1.0  # bara högt par räknas
    rules = [
        {"id": "rundown", "type": "rundown", "groups": ["A–3", "4"], "cost": -3.0, "title": "r", "why": ""},
        {"id": "combo", "type": "combo", "spot": "rfi", "pos": "HJ", "combo": "ingen", "cost": -2.0, "title": "c", "why": ""},
        {"id": "cut", "type": "cutoff", "spot": "rfi", "pos": "CO", "thr": 0.5, "weights": w, "cut_pct": 30.0,
         "num_cards": 6, "cost": -1.0, "title": "k", "why": ""},
    ]
    low_rd = parse_cards("2c 3d 4h 5s 9c 9d")  # ren rundown A–5-området, lägsta kort 2
    assert [r["id"] for r in violations(rules, "rfi", "BTN", low_rd)] == ["rundown"]
    assert [r["id"] for r in violations(rules, "rfi", "HJ", parse_cards("2c 7d 9h Js Kc 3d"))] == ["combo"]
    assert violations(rules, "rfi", "CO", parse_cards("Ah Ad Kc 9s 7c 2d")) == []
    assert [r["id"] for r in violations(rules, "rfi", "CO", parse_cards("2h 7d Kc 9s 4c 3d"))] == ["cut"]
    h = trainer_hand({"rules": rules}, "CO", seed=1)
    assert h and h["answer"] in ("open", "fold") and len(h["cards"]) == 6
    assert (h["answer"] == "fold") == bool(h["reasons"])
    assert trainer_hand({"rules": rules}, "BTN") is None


def test_replayer_steps():
    from pathlib import Path
    from plo_leak.parser import detect_hero, load_paths
    from plo_leak.replayer import replay_steps
    hs = load_paths([Path(__file__).parent / "real" / "gg_plo6_samples.txt"])
    hero = detect_hero(hs)
    for h in hs[:15]:
        r = replay_steps(h, hero, samples=200)
        assert r["steps"] and r["steps"][-1].get("final")
        assert abs(r["steps"][-1]["pot"] - h.pot_size() / h.bb) < 0.11
        for s in r["steps"]:
            if s["eq"]:
                # bara händer med kända kort räknas – de delar hela potten mellan sig
                assert s["eq"]["unknown"] is None and len(s["eq"]["by"]) >= 2
                assert all(r["players"][int(i)]["cards"] and not s["seats"][int(i)]["folded"] for i in s["eq"]["by"])
                assert abs(sum(s["eq"]["by"].values()) - 100) < 0.6


# ---------------------------------------------------------------- version 2: faktaskiktet och motorerna
def _real_hands():
    from pathlib import Path
    from plo_leak.parser import detect_hero, load_paths
    hs = load_paths([Path(__file__).parent / "real"])
    return hs, detect_hero(hs)


def test_facts_equal_legacy():
    """Faktavägen ska ge exakt samma statistik som den ursprungliga genomgången."""
    import math
    from plo_leak.stats import analyze, analyze_legacy
    hs, hero = _real_hands()
    a, b = analyze(hs, hero), analyze_legacy(hs, hero)
    for f in ("hands", "net_bb", "net_money", "rake_paid_bb", "rake_paid_money", "ev_net_bb", "ev_net_money",
              "agg_actions", "pass_actions"):
        assert math.isclose(getattr(a, f), getattr(b, f), rel_tol=1e-9, abs_tol=1e-9), f
    assert dict(a.stakes) == dict(b.stakes) and dict(a.games) == dict(b.games)
    for k, y in b.s.items():
        x = a.s[k]
        assert (x.opps, x.hits) == (y.opps, y.hits), k
        assert math.isclose(x.net_all, y.net_all, abs_tol=1e-6) and math.isclose(x.sq_hit, y.sq_hit, abs_tol=1e-6), k
        assert x.worst_hits(5) == y.worst_hits(5) and x.worst_misses(5) == y.worst_misses(5), k
    assert set(a.decisions.groups) == set(b.decisions.groups)
    for k, g in b.decisions.groups.items():
        assert a.decisions.groups[k].n == g.n and math.isclose(a.decisions.groups[k].s, g.s, abs_tol=1e-9)
    # klustren skiljer sig med avsikt (spelpass i stället för bord + tre-timmarsblock)
    strip = lambda rows, i: [tuple(x for j, x in enumerate(r) if j != i) for r in rows]  # noqa: E731
    assert strip(a.decisions.pre, 5) == strip(b.decisions.pre, 5)
    assert strip(a.decisions.river, 4) == strip(b.decisions.river, 4)
    assert strip(a.decisions.turn_calls, 2) == strip(b.decisions.turn_calls, 2)
    assert sum(a.decisions.folds.values()) == sum(b.decisions.folds.values())
    assert len(a.reverse_dominated) == len(b.reverse_dominated) and dict(a.diag) == dict(b.diag)
    assert a.tilt["triggers"] == b.tilt["triggers"] and a.tilt["after"].opps == b.tilt["after"].opps
    for name in ("by_pos", "by_bucket", "by_nut", "by_nut_combo", "by_nut_pos"):
        da, db_ = getattr(a, name), getattr(b, name)
        assert set(k for k, v in da.items() if v.hands) == set(k for k, v in db_.items() if v.hands), name
        for k, v in db_.items():
            if v.hands:
                assert da[k].hands == v.hands and math.isclose(da[k].net, v.net, abs_tol=1e-9), (name, k)


def test_fact_store_incremental(tmp_path):
    """Bara nya händer får fakta; resultatet är detsamma som att räkna allt på en gång."""
    from pathlib import Path
    from plo_leak.aggregate import build_stats
    from plo_leak.db import HandDB
    from plo_leak.facts import extract
    hs, hero = _real_hands()
    real = Path(__file__).parent / "real"
    db = HandDB(tmp_path / "t.db")
    db.add_paths([real / "user_hand_4bet_pot.txt"])
    store = db.facts(hero)
    n1 = store.sync(db, workers=1)
    db.add_paths([real])
    n2 = store.sync(db, workers=1)
    assert n1 >= 1 and n2 >= 1 and store.sync(db, workers=1) == 0
    ft = store.load()
    ref = extract([h for h in hs if hero in h.seats], hero)
    assert ft.n == ref.n and list(ft.H["id"]) == list(ref.H["id"])
    a, b = build_stats(ft, None, hero), build_stats(ref, None, hero)
    assert abs(a.net_bb - b.net_bb) < 1e-9 and a.s["vpip"].hits == b.s["vpip"].hits


def test_selection_masks():
    import numpy as np
    from plo_leak.facts import extract
    from plo_leak.selection import Selection
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    assert Selection().mask(ft).sum() == ft.n
    m = Selection(latest=10).mask(ft)
    assert m.sum() == 10 and m[-10:].all()
    st0 = ft.vocab["stake"][0]
    m2 = Selection(stake=st0).mask(ft)
    assert (ft.H["stake"][m2] == 0).all() and m2.sum() > 0
    d = __import__("plo_leak.facts", fromlist=["dt_of"]).dt_of(int(ft.H["ts"][5])).strftime("%Y-%m-%d")
    m3 = Selection(date_from=d, date_to=d).mask(ft)
    assert m3.any() and np.all(ft.H["ts"][m3] >= ft.H["ts"][m3].min())


def test_fastev_matches_python():
    import random
    import numpy as np
    from plo_leak import fastev
    from plo_leak.ev import _pairs, _triples, equities_py, fast_best
    deck = [(r, s) for r in range(2, 15) for s in "cdhs"]
    rnd = random.Random(3)
    for k in (4, 5, 6):
        for nb in (3, 4, 5):
            H, B = [], []
            for _ in range(300):
                c = rnd.sample(deck, k + nb)
                H.append(c[:k]); B.append(c[k:])
            v = fastev.best_values(np.array([fastev.codes(h) for h in H]), np.array([fastev.codes(b) for b in B]))
            assert list(v) == [fast_best(_pairs(h), _triples(b)) for h, b in zip(H, B)]
    c = rnd.sample(deck, 15)
    holes = {"a": c[:6], "b": c[6:12]}
    for board in ([], c[12:15]):
        x, y = equities_py(holes, board, samples=400, seed=5), fastev.equities(holes, board, samples=400, seed=5)
        assert all(abs(x[p] - y[p]) < 1e-12 for p in x)


def test_vector_sim_helpers():
    import numpy as np
    from plo_leak import sim
    from plo_leak.cards import nut_qualities
    rng = np.random.default_rng(2)
    H = np.array([rng.permutation(52)[:6] for _ in range(500)])
    cards = [[(int(c) // 4 + 2, "cdhs"[int(c) % 4]) for c in h] for h in H]
    assert (sim._nut_any_vec(H) == np.array([any(nut_qualities(c)) for c in cards])).all()
    assert (sim._nut_high_vec(H[:, :5]) == np.array([sim._nut_straight_high(c[:5]) or 0 for c in cards])).all()
    g, acc = sim._run_chunk_vec(("8", H[:50], 1, 2, True))
    assert acc["n"] == 50 and 0 <= acc["equity"] <= 50


def test_web_job_flow(tmp_path, monkeypatch=None):
    import os
    import time
    from pathlib import Path
    os.environ["PLO_LEAK_DB"] = str(tmp_path / "w.db")
    os.environ["PLO_LEAK_CACHE"] = str(tmp_path / "c")
    import plo_leak.web as web
    web._DB = None
    c = web.app.test_client()

    def run(data):
        r = c.post("/analyze", data=data, content_type="multipart/form-data")
        jid = r.headers["Location"].rsplit("/", 1)[-1]
        for _ in range(600):
            j = c.get(f"/jobb/{jid}/status").get_json()
            if j["status"] in ("klar", "fel"):
                break
            time.sleep(0.1)
        if j["status"] == "klar":
            r = c.get(f"/jobb/{jid}/rapport")
            assert r.status_code == 302
            return "klar", r.headers["Location"]
        return j["status"], c.get(f"/jobb/{jid}/fel").get_data(as_text=True)

    # ingen analys öppen: importsidan om databasen är tom, annars startas en analys av hela databasen
    r0 = c.get("/")
    if r0.status_code == 302 and "/v/" in r0.headers["Location"]:
        pass  # en analys från ett tidigare test är redan öppen
    elif r0.status_code == 302:
        assert "/jobb/" in r0.headers["Location"]
        assert c.get("/?till=preflop").headers["Location"] == r0.headers["Location"]  # bara ett jobb åt gången
        ajid = r0.headers["Location"].rsplit("/", 1)[-1]
        for _ in range(600):
            if c.get(f"/jobb/{ajid}/status").get_json()["status"] in ("klar", "fel"):
                break
            time.sleep(0.1)
    else:
        assert r0.status_code == 200
    s, loc = run({"folder": str(Path(__file__).parent / "real")})
    assert s == "klar" and loc.endswith("/oversikt")
    vid = loc.split("/")[-2]
    for pg in web.PAGES:
        r = c.get(f"/v/{vid}/{pg}")
        txt = r.get_data(as_text=True)
        assert r.status_code == 200 and "Läckfinnaren" in txt and 'class="nav-i on"' in txt, pg
    # snabb start: den senaste analysen sparas på disk och öppnas direkt när programmet startar om
    for _ in range(100):
        if web._snap_path().exists():
            break
        time.sleep(0.05)
    assert web._snap_path().exists()
    with web._VLOCK:
        saved_views = dict(web.VIEWS)
        web.VIEWS.clear()
    web._AUTO["job"] = None
    r1 = c.get("/")
    assert r1.status_code == 302 and "/jobb/" in r1.headers["Location"]
    jid1 = r1.headers["Location"].rsplit("/", 1)[-1]
    for _ in range(200):
        if c.get(f"/jobb/{jid1}/status").get_json()["status"] in ("klar", "fel"):
            break
        time.sleep(0.05)
    loc1 = c.get(f"/jobb/{jid1}/rapport").headers["Location"]
    vid1 = loc1.split("/")[-2]
    assert vid1 != vid and c.get(f"/v/{vid1}/oversikt").status_code == 200
    assert c.get(f"/v/{vid1}/sessioner").status_code == 200
    with web._VLOCK:
        web.VIEWS.update(saved_views)
    # flera sessioner i en fil (högst 5)
    import re as _re2
    keys = _re2.findall(r'class="spick" value="(\d+)"', c.get(f"/v/{vid}/sessioner").get_data(as_text=True))
    assert keys
    assert 'data-k="evusd"' in c.get(f"/v/{vid}/sessioner").get_data(as_text=True)
    one = c.get(f"/v/{vid}/sessionsfil?s={keys[0]}")
    assert one.status_code == 200 and one.get_data(as_text=True).startswith("# Till Claude")
    if len(keys) >= 2:
        q = "&".join(f"s={k}" for k in keys[:7])
        multi = c.get(f"/v/{vid}/sessionsfil?{q}")
        mt = multi.get_data(as_text=True)
        n = min(len(keys), 7)  # 2.77.6: valfritt antal; fler än 5 ger en gemensam del
        assert multi.status_code == 200 and f"{n} sessioner" in mt and "## Alla sessioner tillsammans" in mt
        assert mt.count("# Till Claude") == 1 and (mt.count("\n# Session ") == n if n <= 5 else f"# Alla {n} sessioner" in mt)
        assert f"_{n}st.md" in multi.headers["Content-Disposition"]
    # dela som bild: siffrorna till bilden, hela urvalet och med startdatum
    jd = c.get(f"/api/dela/{vid}").get_json()
    assert jd["total"]["hands"] > 0 and jd["mode"] in ("months", "weeks") and jd["bars"]
    assert len(jd["series"]["i"]) == len(jd["series"]["m"]) and jd["series"]["i"][-1] == jd["total"]["hands"]
    assert abs(jd["series"]["e"][-1] - jd["total"]["ev_money"]) < 0.05
    jm = c.get(f"/api/dela/{vid}?fran=2026-08-01").get_json()
    assert "error" in jm or (jm["mode"] == "periods" and jm["periods"] and jm["total"]["hands"] <= jd["total"]["hands"])
    assert c.get(f"/api/dela/{vid}?fran=2099-01-01").get_json().get("error")
    ov = c.get(f"/v/{vid}/oversikt").get_data(as_text=True)
    assert 'data-unit="usd"' in ov and 'id="chart-money"' in ov  # vinstkurvan i bb eller dollar
    assert 'Topp 3 just nu' in ov and 'Om du tätar alla' not in ov  # 2.77
    sd = c.get(f"/v/{vid}/sessioner?s={keys[0]}").get_data(as_text=True)
    assert 'id="sess-chart"' in sd or "1 händer" in sd  # sessionens kurva (minst 2 händer)
    rb = c.get(f"/v/{vid}/rakeback").get_data(as_text=True)
    assert 'id="rb-out"' in rb and '"rake100"' in rb and '"hph"' in rb  # kalkylatorn får dina siffror
    j = c.get(f"/api/hander/{vid}?q=senaste&sort=date&dir=desc&size=5").get_json()
    assert j["total"] > 0 and len(j["rows"]) == min(5, j["total"])
    assert j["rows"][0]["date"] >= j["rows"][-1]["date"]
    # sessionslistan: en session kombinerad med filter, och pott-nummer som i sessionsfilen
    sp = c.get(f"/v/{vid}/sessioner").get_data(as_text=True)
    import re as _re
    t0, t1 = _re.search(r'data-t0="(\d+)" data-t1="(\d+)"', sp).groups()
    ja = c.get(f"/api/hander/{vid}?q=alla&sort=date&dir=asc&size=200&fran_ts={t0}&till_ts={t1}").get_json()
    jt = c.get(f"/api/hander/{vid}?q=top&sort=nr&dir=asc&size=200&fran_ts={t0}&till_ts={t1}").get_json()
    assert ja["total"] > 0 and 0 < jt["total"] <= 10 and jt["total"] <= ja["total"]
    assert [x["nr"] for x in jt["rows"]] == list(range(1, jt["total"] + 1))
    jl = c.get(f"/api/hander/{vid}?q=alla&sort=luck&dir=desc&size=200&fran_ts={t0}&till_ts={t1}").get_json()
    lk = [x["net"] - x["ev"] for x in jl["rows"]]
    assert lk == sorted(lk, reverse=True)
    rp = c.get(f"/api/replay/{vid}/{j['rows'][0]['id']}")
    assert rp.status_code == 200 and rp.get_json()["steps"]
    assert c.get(f"/api/replay/{vid}/finns-inte").status_code == 404
    r = c.post(f"/v/{vid}/exportera-lista", data={"q": "forlust", "sort": "net", "dir": "asc", "limit": "3"})
    ejid = r.headers["Location"].rsplit("/", 1)[-1]
    for _ in range(300):
        if c.get(f"/jobb/{ejid}/status").get_json()["status"] in ("klar", "fel"):
            break
        time.sleep(0.1)
    eloc = c.get(f"/jobb/{ejid}/rapport").headers["Location"]
    import io as _io
    import zipfile as _zf
    from plo_leak.parser import parse_bytes as _pb
    zz = _zf.ZipFile(_io.BytesIO(c.get("/exportera/fil/" + eloc.split("klar=")[1]).data))
    worst = c.get(f"/api/hander/{vid}?q=forlust&sort=net&dir=asc&size=3").get_json()["rows"]
    got = {h.id for n in zz.namelist() for h in _pb(n, zz.read(n))}
    assert got == {w["id"] for w in worst}
    loss = c.get(f"/api/hander/{vid}?q=forlust&sort=net&dir=asc").get_json()["rows"]
    assert all(r["net"] < 0 for r in loss) and [r["net"] for r in loss] == sorted(r["net"] for r in loss)
    import json as _json
    assert isinstance(_json.loads(c.get(f"/v/{vid}/export").get_data(as_text=True)), dict)
    ej = _json.loads(c.get(f"/v/{vid}/export").get_data(as_text=True))
    assert "sessions" in ej and "focus_queue" in ej
    # djupanalys: tabellerna bakom analysen
    import csv as _csv
    import time
    r = c.get(f"/v/{vid}/djupanalys")
    djid = r.headers["Location"].rsplit("/", 1)[-1]
    for _ in range(600):
        if c.get(f"/jobb/{djid}/status").get_json()["status"] in ("klar", "fel"):
            break
        time.sleep(0.1)
    dloc = c.get(f"/jobb/{djid}/rapport").headers["Location"]
    assert "/djupanalys/klar/" in dloc, c.get(f"/jobb/{djid}/fel").get_data(as_text=True)
    assert "Ladda ner" in c.get(dloc).get_data(as_text=True)
    dz = _zf.ZipFile(_io.BytesIO(c.get("/djupanalys/fil/" + dloc.rsplit("/", 1)[-1]).data))
    assert c.get("/djupanalys/fil/../x.zip").status_code == 404
    names = set(dz.namelist())
    assert {"hands.csv", "preflop.csv", "sessions.csv", "rules.json", "LÄS_MIG.txt", "postflop.csv", "stakes.csv"} <= names
    prow = list(_csv.DictReader(_io.StringIO(dz.read("postflop.csv").decode("utf-8"))))
    assert prow and {r["street"] for r in prow} <= {"flop", "turn", "river"}
    assert {r["action"] for r in prow} <= {"check", "bet", "call", "raise", "fold"}
    assert {r["villain_better"] for r in prow} <= {"", "0", "1"} and any(r["villain_hand"] for r in prow)
    hev = {r["hand_id"]: float(r["ev_bb"]) for r in _csv.DictReader(_io.StringIO(dz.read("hands.csv").decode("utf-8")))}
    for r in prow[:200]:  # resultatet härifrån = handens all-in EV + det du redan lagt i potten
        assert abs(float(r["from_here_bb"]) - (hev[r["hand_id"]] + float(r["hero_in_bb"]))) < 0.02
    hrows = list(_csv.DictReader(_io.StringIO(dz.read("hands.csv").decode("utf-8"))))
    allh = c.get(f"/api/hander/{vid}?q=senaste&size=1").get_json()["total"]
    assert len(hrows) == allh and all(r["hand_id"] for r in hrows)
    srows = list(_csv.DictReader(_io.StringIO(dz.read("sessions.csv").decode("utf-8"))))
    assert sum(int(r["hands"]) for r in srows) == len(hrows)
    assert {r["session"] for r in hrows} == {r["session"] for r in srows}
    assert "Hero" not in dz.read("hands.csv").decode("utf-8")
    assert c.get("/").status_code == 302 and c.get("/import").status_code == 200 and c.get("/trana").status_code == 200
    assert c.get("/v/okand/oversikt").status_code == 404
    s, loc = run({"latest_on": "1", "latest": "20", "back": "preflop"})
    assert s == "klar" and loc.endswith("/preflop") and "20 händer" in c.get(loc).get_data(as_text=True)
    s, html = run({"stake": "9/9"})
    assert s == "fel" and "Inga händer matchar" in html
    web._DB = None
    del os.environ["PLO_LEAK_DB"]


def test_short_allin_open_is_not_rfi():
    """En kort all-in som enda höjning: nästa spelare är inte 'foldat till dig'."""
    from plo_leak.stats import analyze
    h = _hh("""Table 'T' 6-max Seat #1 is the button
Seat 1: A ($100 in chips)
Seat 2: B ($100 in chips)
Seat 3: C ($100 in chips)
Seat 4: D ($1.5 in chips)
Seat 5: Hero ($100 in chips)
Seat 6: F ($100 in chips)
B: posts small blind $0.5
C: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
D: raises $0.5 to $1.5 and is all-in
Hero: raises $3.5 to $5
F: folds
A: folds
B: folds
C: folds
*** SUMMARY ***
""")
    st = analyze([h], "Hero")
    assert not any(k[0] == "rfi" for k in st.decisions.groups)
    assert any(k[0] == "mot_hojning" for k in st.decisions.groups)
    assert st.s["rfi"].opps == 0


def test_security_guards():
    import plo_leak.web as web
    c = web.app.test_client()
    assert c.get("/", headers={"Host": "evil.example"}).status_code == 403
    assert c.post("/rensa", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/avsluta", headers={"Origin": "https://evil.example"}).status_code == 403
    web._LAN["token"] = "x1"
    try:
        assert c.get("/", headers={"Host": "10.0.0.2:8765"}).status_code == 403
        assert c.get("/?kod=x1", headers={"Host": "10.0.0.2:8765"}).status_code in (200, 302)
    finally:
        web._LAN["token"] = None
    assert not web._valid_date("2026-13-45") and web._valid_date("2026-02-28")


def test_sessions_are_clusters():
    """Händer med kort paus hör till samma spelpass (samma kluster), lång paus ger nytt pass."""
    import numpy as np
    from plo_leak.facts import SESSION_GAP, extract
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    ts, clu = ft.H["ts"], ft.H["clu"]
    gaps = np.diff(ts)
    same = clu[1:] == clu[:-1]
    assert (same[gaps <= SESSION_GAP]).all() and not (same[gaps > SESSION_GAP]).any()


def test_strict_cells_control_false_positives():
    """Sneda resultat med medel noll: tabellbedömningarna ger nästan aldrig ett falskt säkert utslag."""
    import numpy as np
    from plo_leak.statlib import ci_cells
    rng = np.random.default_rng(11)
    false = 0
    for _ in range(6):
        pairs = []
        for _ in range(32):
            n = int(rng.choice([40, 100, 300]))
            x = np.where(rng.random(n) < 0.08, rng.exponential(25, n), -rng.exponential(2.0, n)) - 0.16
            pairs.append((x, rng.integers(0, n // 3 + 1, n)))
        false += sum(v["verdict"] in ("förlorar", "lönsamt") for v in ci_cells(pairs))
    assert false <= 1


def test_no_hero_hands_not_rescanned(tmp_path):
    from pathlib import Path
    from plo_leak.db import HandDB
    db = HandDB(tmp_path / "t.db")
    db.add_paths([Path(__file__).parent / "real"])
    st = db.facts("Ingen-sådan-spelare")
    assert st.sync(db, workers=1) == 0 and st.sync(db, workers=1) == 0
    assert st.manifest()["segments"] == [] and st.manifest()["seen"] == db.count()


def test_threebet_over_short_allin_then_4bet():
    from plo_leak.stats import analyze
    h = _hh("""Table 'T' 6-max Seat #1 is the button
Seat 1: A ($100 in chips)
Seat 2: B ($100 in chips)
Seat 3: C ($100 in chips)
Seat 4: D ($1.5 in chips)
Seat 5: Hero ($100 in chips)
Seat 6: F ($100 in chips)
B: posts small blind $0.5
C: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [As Ad Kh Kd 2c 3c]
D: raises $0.5 to $1.5 and is all-in
Hero: raises $3.5 to $5
F: folds
A: folds
B: folds
C: raises $10 to $15
Hero: calls $10
*** FLOP *** [2s 3s Td]
C: checks
Hero: checks
*** TURN *** [2s 3s Td] [Jc]
C: checks
Hero: checks
*** RIVER *** [2s 3s Td Jc] [Qs]
C: checks
Hero: checks
*** SUMMARY ***
""")
    st = analyze([h], "Hero")
    assert any(k[0] == "mot_4bet" for k in st.decisions.groups)
    assert st.s["fold_to_4bet"].opps == 1


def test_equity_matches_independent_evaluator():
    """Equity i uppspelningen och all-in EV jämförs med en helt oberoende utvärderare (cards.eval5)."""
    import itertools
    import random
    from plo_leak import fastev
    from plo_leak.cards import eval5
    deck = [(r, s) for r in range(2, 15) for s in "cdhs"]

    def best(hole, board):
        return max(eval5(list(h) + list(b)) for h in itertools.combinations(hole, 2)
                   for b in itertools.combinations(board, 3))
    rnd = random.Random(9)
    for _ in range(6):
        k = rnd.choice([4, 6])
        c = rnd.sample(deck, 2 * k + 4)
        holes = {"a": c[:k], "b": c[k:2 * k]}
        board = c[2 * k:]
        rest = [x for x in deck if x not in c]
        ref = {"a": 0.0, "b": 0.0}
        for x in rest:
            va, vb = best(holes["a"], board + [x]), best(holes["b"], board + [x])
            if va == vb:
                ref["a"] += 0.5; ref["b"] += 0.5
            else:
                ref["a" if va > vb else "b"] += 1
        got = fastev.equity_vs_unknown(holes, 0, k, board, 100, 1)
        assert all(abs(ref[p] / len(rest) - got[p]) < 1e-12 for p in ref)
    # flop: två kort kvar räknas också exakt (alla turn+river-kombinationer)
    for _ in range(2):
        k = 4
        c = rnd.sample(deck, 2 * k + 3)
        holes = {"a": c[:k], "b": c[k:2 * k]}
        board = c[2 * k:]
        rest = [x for x in deck if x not in c]
        ref = {"a": 0.0, "b": 0.0}
        n = 0
        for x, y in itertools.combinations(rest, 2):
            va, vb = best(holes["a"], board + [x, y]), best(holes["b"], board + [x, y])
            n += 1
            if va == vb:
                ref["a"] += 0.5; ref["b"] += 0.5
            else:
                ref["a" if va > vb else "b"] += 1
        got = fastev.equity_vs_unknown(holes, 0, k, board, 100, 1)
        assert all(abs(ref[p] / n - got[p]) < 1e-12 for p in ref)


def test_showdown_curves_add_up():
    """Vinst med och utan showdown blir tillsammans det faktiska resultatet, och grafen får alla linjer."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.report import _chart
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    assert np.allclose(st.cumulative_sd + st.cumulative_nsd, st.cumulative)
    assert np.allclose(st.cumulative_sd_money + st.cumulative_nsd_money, st.cumulative_money)
    assert 0 < int(ft.H["sd"].sum()) < ft.n  # båda sorterna finns i testhänderna
    c = _chart({"net": st.cumulative, "ev": st.cumulative_ev, "rake": st.cumulative_rake,
                "sd": st.cumulative_sd, "nsd": st.cumulative_nsd}, max_points=50)
    assert {x["k"] for x in c["s"]} == {"net", "ev", "rake", "sd", "nsd"}
    assert c["x"][0] == 1 and c["x"][-1] == c["n"] == ft.n and len(c["x"]) <= 51
    assert all(len(x["v"]) == len(c["x"]) for x in c["s"])


def test_nut_fold_counts_blinds():
    """Jämfört med fold = netto när spelad + blinden som redan låg i potten (SB/BB)."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.nutfold import nut_fold_table
    from plo_leak.practice import violation_index
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    by = {h.id: h for h in hs}
    st = build_stats(ft, np.ones(ft.n, bool), hero, by.get)
    t = nut_fold_table(st)
    assert t and t["rows"]
    for g in t["grid"]:
        for c in g["cells"]:
            if c and c["played"]:
                assert c["played"] == st.by_nut_pos[(g["name"], c["pos"])].vpip
    # per hand: jämfört med fold − netto = det du själv lagt i potten före ditt beslut (blind, straddle)
    from plo_leak.rundowns import FIRST_SPOTS
    pre, H = st.decisions.pre, ft.H
    m = np.flatnonzero(pre.is_spot(*FIRST_SPOTS))
    _, f = np.unique(pre.hidx[m], return_index=True)
    checked = 0
    for j in m[f]:
        if np.isnan(pre.delta[j]):
            continue
        h = by[H["id"][pre.hidx[j]]]
        posted = sum(a.added for a in h.actions if a.player == hero and a.kind.startswith("post")) / h.bb
        assert abs(pre.delta[j] - H["ev"][pre.hidx[j]] - posted) < 1e-6, h.id
        checked += 1
    assert checked > 20
    # en regel av typen "nut" träffar just de första besluten med rätt antal egenskaper och position
    pre = st.decisions.pre
    g = t["grid"][0]
    pos = next(c["pos"] for c in g["cells"] if c)
    rule = {"type": "nut", "nut": g["name"], "pos": pos}
    vi = violation_index([rule], pre)
    hit = vi >= 0
    assert hit.any()
    assert (ft.H["nut"][pre.hidx[hit]] == ft.codes("nut")[g["name"]]).all()
    assert (pre.pos[hit] == ft.code("pos", pos)).all()


def test_likely_improvements_paths_and_rules():
    """Trolig förbättring: alla kandidattyper går att räkna och blir regler som träffar rätt händer."""
    import numpy as np
    import plo_leak.likely as L
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.practice import violation_index
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    old = (L.Q_FDR, L.N_MIN, L.MIN_BIG_WINS)
    try:
        L.Q_FDR, L.N_MIN, L.MIN_BIG_WINS = 1.0, 4, 0  # visa allt som valts ut, oavsett säkerhet
        out = L.likely_improvements(st)
    finally:
        L.Q_FDR, L.N_MIN, L.MIN_BIG_WINS = old
    assert out and all(0 <= o["p"] <= 1 and 0 <= o["p_raw"] <= 1 for o in out)
    assert [o["gain100"] for o in out] == sorted((o["gain100"] for o in out), reverse=True)
    assert all(o["rule"]["level"] == "trolig" for o in out)
    pre = st.decisions.pre
    for o in out:
        vi = violation_index([o["rule"]], pre)
        assert (vi >= 0).any(), o["title"]
    # normala gränser: bara rader som klarar falskupptäcktskontrollen
    assert all(o["q"] <= L.Q_FDR for o in L.likely_improvements(st))
    # BH-justering
    assert [round(q, 3) for q in L._bh_q([0.01, 0.04, 0.03, 0.5])] == [0.04, 0.053, 0.053, 0.5]


def test_likely_skips_what_is_already_confirmed():
    from plo_leak.likely import covered
    conf = [{"id": "rundown", "type": "rundown", "groups": ["A–3", "4"]},
            {"id": "nut|CO|0 nöt-egenskaper", "type": "nut", "pos": "CO", "nut": "0 nöt-egenskaper"}]
    rd = {"rule": {"id": "rundown|4", "type": "rundown", "groups": ["4"]}}
    rd5 = {"rule": {"id": "rundown|5", "type": "rundown", "groups": ["5"]}}
    co = {"rule": {"id": "combo|rfi|CO|ingen", "type": "combo", "pos": "CO", "combo": "ingen"}}
    out = {"rule": {"id": "nut|utanför blindarna|0 nöt-egenskaper", "type": "nut", "nut": "0 nöt-egenskaper",
                    "positions": ["LJ", "HJ", "CO", "BTN"]}}
    assert covered(rd, conf) and covered(co, conf)
    assert not covered(rd5, conf) and not covered(out, conf)


def test_zip_import_and_watched_folder(tmp_path):
    """GG:s zip-filer läses direkt (även zip i zip), andra zip-filer hoppas över, och den bevakade
    mappen läser bara in nya filer."""
    import io
    import threading
    import zipfile
    from pathlib import Path
    from plo_leak import watch
    from plo_leak.db import HandDB
    from plo_leak.parser import find_files
    src = (Path(__file__).parent / "real" / "gg_plo6_samples.txt").read_bytes()
    dl = tmp_path / "Downloads"
    dl.mkdir()
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("GG20261019-1200 - PLO-6.txt", src)
    with zipfile.ZipFile(dl / "GG_export.zip", "w") as z:
        z.writestr("__MACOSX/._x.txt", b"junk")
        z.writestr("inner.zip", inner.getvalue())
    with zipfile.ZipFile(dl / "semesterbilder.zip", "w") as z:
        z.writestr("bild.txt", b"inte poker" * 100)
    (dl / "halvfardig.zip").write_bytes(b"PK\x03\x04 inte klar")
    (dl / "anteckning.txt").write_text("handla mjolk")
    files = find_files([dl])
    assert [f.name for f in files] == ["GG_export.zip"]
    db = HandDB(tmp_path / "w.db")
    watch.save_settings(db, watch=str(dl), auto=True)
    lock = threading.Lock()
    assert watch.scan(db, lock)["hands_new"] == 0  # filerna är just skrivna – kan fortfarande laddas ner
    import os
    import time as _t
    old = _t.time() - 120
    for f in dl.iterdir():
        os.utime(f, (old, old))
    r = watch.scan(db, lock)
    assert r and r["hands_new"] > 0 and db.count() == r["hands_new"]
    n = db.count()
    r2 = watch.scan(db, lock)  # inget nytt: ingen fil öppnas alls
    assert r2["hands_new"] == 0 and r2["files"] == 0 and db.count() == n
    # standardmapp när ingen mapp valts, ingen bevakning när den stängts av
    assert watch.folder_of({}) == watch.default_folder()
    assert watch.folder_of({"watch": None}) == "" and watch.folder_of({"watch": str(dl)}) == str(dl)
    lock.acquire()
    try:
        assert watch.scan(db, lock) is None  # ett jobb pågår: ingen inläsning
    finally:
        lock.release()
    assert not lock.locked()


def test_web_watch_folder(tmp_path):
    import os
    import time
    import zipfile
    from pathlib import Path
    os.environ["PLO_LEAK_DB"] = str(tmp_path / "w.db")
    import plo_leak.web as web
    web._DB = None
    try:
        dl = tmp_path / "dl"
        dl.mkdir()
        with zipfile.ZipFile(dl / "gg.zip", "w") as z:
            z.write(Path(__file__).parent / "real" / "gg_plo6_samples.txt", "h.txt")
        c = web.app.test_client()
        assert "Standardmapp" in c.get("/import").get_data(as_text=True)
        assert c.post("/bevaka", data={"watch": str(tmp_path / "finns-inte")}).status_code == 400
        r = c.post("/bevaka", data={"watch": str(dl), "auto": "1"})
        jid = r.headers["Location"].rsplit("/", 1)[-1]
        for _ in range(300):
            if c.get(f"/jobb/{jid}/status").get_json()["status"] in ("klar", "fel"):
                break
            time.sleep(0.1)
        r = c.get(f"/jobb/{jid}/rapport")
        assert r.status_code == 302 and r.headers["Location"].endswith("/import?klar=1")
        txt = c.get("/import?klar=1").get_data(as_text=True)
        assert "nya händer lästes in" in txt and str(dl) in txt
        assert web.get_db().count() > 0
        assert "avstängd" in c.post("/bevaka", data={"off": "1"}).get_data(as_text=True)
    finally:
        web._DB = None
        del os.environ["PLO_LEAK_DB"]


def test_export_hands_roundtrip(tmp_path):
    """Exporterade händer har exakt originaltexten och kan läsas in igen; urvalen fungerar."""
    import io
    import os
    import time
    import zipfile
    from pathlib import Path
    from plo_leak.db import RE_ID
    from plo_leak.parser import parse_bytes, split_hands
    os.environ["PLO_LEAK_DB"] = str(tmp_path / "x.db")
    import plo_leak.web as web
    web._DB = None
    web._FT.update(key=None, ft=None)
    try:
        src = Path(__file__).parent / "real"
        orig = {}
        for f in sorted(src.glob("*.txt")):
            for ch in split_hands(f.read_text(encoding="utf-8")):
                m = RE_ID.search(ch[:200])
                if m:
                    orig[m.group(1)] = ch.strip("\n")
        db = web.get_db()
        db.add_paths([src])
        c = web.app.test_client()
        assert "Exportera händer" in c.get("/exportera").get_data(as_text=True)

        def run(data):
            r = c.post("/exportera", data=data)
            assert r.status_code == 302, r.get_data(as_text=True)[:300]
            jid = r.headers["Location"].rsplit("/", 1)[-1]
            for _ in range(300):
                j = c.get(f"/jobb/{jid}/status").get_json()
                if j["status"] in ("klar", "fel"):
                    break
                time.sleep(0.1)
            if j["status"] != "klar":
                return None, c.get(f"/jobb/{jid}/fel").get_data(as_text=True)
            loc = c.get(f"/jobb/{jid}/rapport").headers["Location"]
            name = loc.split("klar=")[1]
            assert "Ladda ner" in c.get(loc).get_data(as_text=True)
            z = zipfile.ZipFile(io.BytesIO(c.get(f"/exportera/fil/{name}").data))
            return z, None

        z, _ = run({})
        texts = [z.read(n).decode("utf-8") for n in z.namelist()]
        got = {}
        for t in texts:
            for ch in split_hands(t):
                got[RE_ID.search(ch[:200]).group(1)] = ch.strip("\n")
        hero_ids = {str(x) for x in web._FT["ft"].H["id"]}
        assert set(got) == hero_ids and all(got[k] == orig[k] for k in got)  # exakt originaltext
        # senaste 5 i en fil
        z, _ = run({"latest": "5", "split": "en"})
        assert len(z.namelist()) == 1
        hs = parse_bytes(z.namelist()[0], z.read(z.namelist()[0]))
        assert len(hs) == 5
        last5 = {str(x) for x in web._FT["ft"].H["id"][-5:]}
        assert {h.id for h in hs} == last5
        # datum utan händer -> begripligt fel
        z, err = run({"fran": "2001-01-01", "till": "2001-01-02"})
        assert z is None and "Inga händer matchar" in err
        assert c.post("/exportera", data={"fran": "2026-13-01"}).status_code == 400
        assert c.get("/exportera/fil/../../etc.zip").status_code == 404
    finally:
        web._DB = None
        web._FT.update(key=None, ft=None)
        del os.environ["PLO_LEAK_DB"]


def test_pot_size_table():
    """Pottgrupperna täcker alla händer, summorna stämmer och vägen in i potten räknas rätt."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.potsize import LABELS, _bucket, pot_table
    assert list(_bucket(np.array([0, 9.99, 10, 199.9, 200, 5000]))) == [0, 0, 1, 19, 20, 20]
    assert LABELS[0] == "0–10" and LABELS[-1] == "200+" and len(LABELS) == 21
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    t = pot_table(st)
    rows = [r for r in t["rows"] if r["n"]]
    assert sum(r["n"] for r in rows) == ft.n
    assert abs(sum(r["ev"] for r in rows) - st.ev_net_bb) < 1e-6
    assert abs(sum(r["net"] for r in rows) - st.net_bb) < 1e-6
    for b in t["bands"]:
        assert sum(c["n"] for c in b["cells"]) == b["n"]
    # en känd hand: straddle, höjning till 22, syn 72 och syn all-in – motståndaren satsade sist
    H = ft.H
    j = int(np.flatnonzero(H["id"].astype(str) == "OM99382500")[0])
    assert H["la"][j] == 2 and abs(H["ia"][j] - 9.0) < 1e-6 and abs(H["ic"][j] - 252.34) < 1e-6
    # ett bet som kommer tillbaka osynat räknas inte som insatta pengar
    ids = list(H["id"].astype(str))
    if "OM90955294" in ids:
        k = ids.index("OM90955294")
        assert H["la"][k] == 1 and abs(H["ia"][k]) < 1e-9


def test_hourly_rate():
    """Speltid från tidsstämplarna: pauser räknas inte, flera pass summeras, timlönen stämmer."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.hourly import PAUSE_CAP, _active_seconds, hourly_table
    sec, n, tail = _active_seconds(np.array([0, 60, 120, 10000, 10060]), np.array([0, 0, 0, 1, 1]))
    assert n == 2 and tail == 60 and sec == 60 * 3 + 2 * 60
    sec, n, tail = _active_seconds(np.array([0, 2000, 2060]), np.array([0, 0, 0]))
    assert n == 1 and sec == PAUSE_CAP + 60 + tail  # luckan på 2000 s räknas bara som 5 minuter
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    t = hourly_table(st)
    tot = t["total"]
    assert tot["hands"] == ft.n and tot["hours"] > 0
    assert abs(tot["usd_h"] * tot["hours"] - st.net_money) < 1e-6
    assert abs(tot["ev_usd_h"] * tot["hours"] - st.ev_net_money) < 1e-6
    assert abs(tot["hph"] - ft.n / tot["hours"]) < 1e-9
    assert sum(w["hands"] for w in t["weeks"]) <= ft.n and all(w["hours"] >= 1 for w in t["weeks"])


def test_trainer_scenarios():
    """Tränaren: en situation per regel (öppningsgränser, BB-försvar, nöt-egenskaper) med rätt facit."""
    from plo_leak.cards import NUT_LABELS, nut_qualities
    from plo_leak.practice import trainer_hand, trainer_scenarios
    import plo_leak.web as web
    doc = {"variant": "PLO6", "rules": [
        {"id": "nut|utanför blindarna|0", "type": "nut", "pos": "utanför blindarna", "positions": ["HJ", "CO", "BTN"],
         "nut": "0 nöt-egenskaper", "cost": -1.0, "title": "Utanför blindarna: folda händer med 0 nöt-egenskaper",
         "why": "x", "level": "trolig"},
        {"id": "nut|BB|0", "type": "nut", "pos": "BB", "nut": "0 nöt-egenskaper", "cost": -1.2,
         "title": "BB: spela inte händer med 0 nöt-egenskaper", "why": "y", "level": "bekräftad"}]}
    sc = {s["key"] for s in trainer_scenarios(doc)}
    sc = {k for k in sc if not k.startswith("pct|")}  # 2.75: reglaget finns alltid
    assert sc == {"rfi|HJ", "rfi|CO", "rfi|BTN", "bb_mot_hojning|BB"}
    answers = set()
    for seed in range(30):
        h = trainer_hand(doc, "BB", seed=seed, spot="bb_mot_hojning")
        k = sum(bool(x) for x in nut_qualities([tuple(c) for c in h["cards"]])[:3])
        assert len(h["cards"]) == 6 and h["pct"] is None
        assert (h["answer"] == "fold") == (NUT_LABELS[k] == "0 nöt-egenskaper")
        if h["answer"] == "fold":
            assert h["reasons"][0]["level"] == "bekräftad"
        answers.add(h["answer"])
    assert answers == {"fold", "free"}  # ingen gräns: det som inte bryter mot en regel är ditt val
    assert trainer_hand(doc, "SB", spot="sb_mot_hojning") is None
    c = web.app.test_client()
    j = c.get("/api/status").get_json()
    assert {"watch_new", "job_running", "latest_vid", "auto_update", "auto_running"} <= set(j)


def test_focus_leak():
    """Fokus: reglerna rangordnas efter vad de kostar nu, en vald läcka står kvar, och 'under kontroll'."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.focus import focus_list, pick
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    pos_all = ["LJ", "HJ", "CO", "BTN", "SB", "BB"]
    doc = {"variant": "PLO6", "rules": [
        {"id": "nut|alla|1", "type": "nut", "pos": "alla", "positions": pos_all, "nut": "1 nöt-egenskap",
         "cost": -0.5, "title": "A", "why": "", "level": "trolig"},
        {"id": "nut|alla|0", "type": "nut", "pos": "alla", "positions": pos_all, "nut": "0 nöt-egenskaper",
         "cost": -3.0, "title": "B", "why": "", "level": "bekräftad"}]}
    fl = focus_list(st, doc)
    assert [f["id"] for f in fl if not f["done"]] == sorted([f["id"] for f in fl if not f["done"]],
                                                          key=lambda i: -next(x["per100"] for x in fl if x["id"] == i))
    for f in fl:
        assert abs(f["per100"] - (-f["cost_hand"] * f["dev"] / f["recent_hands"] * 100)) < 1e-9
        assert len(f["weeks"]) == 8 and f["dev"] <= f["opps"]
        assert len(f["dev_rows"]) == len(set(f["dev_rows"].tolist()))
    assert pick(fl, None) is fl[0] and pick(fl, fl[-1]["id"]) is fl[-1] and pick(fl, "finns-inte") is fl[0]


def test_subgroup_exceptions():
    """Bra undergrupper i en förlorande grupp blir undantag och räknas inte som regelbrott."""
    import numpy as np
    from plo_leak.subgroups import STRUCT, shrink, struct_of
    from plo_leak.practice import violations
    assert struct_of([(9, "h"), (8, "h"), (7, "s"), (6, "s"), (4, "c"), (3, "c")]) == "trippelsuited"
    assert struct_of([(13, "h"), (9, "h"), (5, "s"), (4, "s"), (3, "c"), (2, "d")]) == "dubbelsuited + sammanhängande"
    assert struct_of([(13, "h"), (9, "h"), (7, "s"), (2, "s"), (11, "c"), (4, "d")]) == "dubbelsuited + suited kung"
    assert struct_of([(13, "h"), (9, "h"), (7, "h"), (2, "c"), (11, "s"), (4, "d")]) == "övriga"
    rng = np.random.default_rng(3)
    n = 6000
    code = rng.integers(0, len(STRUCT), n)
    clu = np.arange(n) // 20
    # trippelsuited (0) vinner klart, resten förlorar
    x = np.where(code == 0, 1.5, -1.0) + rng.normal(0, 4, n)
    s = shrink(x, clu, code)
    ex = [r["name"] for r in s["rows"] if r["exempt"]]
    assert ex == ["trippelsuited"] and s["tau"] > 0
    # ingen verklig skillnad: inga undantag (krymps mot snittet)
    x2 = -0.5 + rng.normal(0, 4, n)
    assert not [r for r in shrink(x2, clu, code)["rows"] if r["exempt"]]
    # en regel med undantag träffar inte trippelsuited händer
    rule = {"id": "nut|utanför blindarna|0 nöt-egenskaper", "type": "nut", "positions": ["CO"], "pos": "utanför blindarna",
            "nut": "0 nöt-egenskaper", "title": "t", "except": ["trippelsuited"]}
    ts = [(9, "h"), (8, "h"), (4, "s"), (3, "s"), (2, "c"), (12, "c")]
    rb = [(13, "h"), (9, "h"), (7, "h"), (2, "c"), (11, "s"), (4, "d")]
    exempt = []
    assert violations([rule], "rfi", "CO", ts, exempt) == [] and exempt and exempt[0]["name"] == "trippelsuited"
    assert violations([rule], "rfi", "CO", rb) == [rule]


def test_start_opens_analysis_automatically(tmp_path):
    """Direkt efter start (ingen analys öppen) analyseras hela databasen, så menyn fungerar direkt."""
    import os
    import time
    from pathlib import Path
    os.environ["PLO_LEAK_DB"] = str(tmp_path / "a.db")
    os.environ["PLO_LEAK_CACHE"] = str(tmp_path / "c")
    import plo_leak.web as web
    web._DB = None
    old = dict(web.VIEWS)
    web.VIEWS.clear()
    web._AUTO["job"] = None
    try:
        c = web.app.test_client()
        assert c.get("/").status_code == 200  # tom databas: importsidan
        html = c.get("/import").get_data(as_text=True)
        assert 'href="/?till=preflop"' in html and " dis\"" not in html
        web.get_db().add_paths([Path(__file__).parent / "real"])
        r = c.get("/?till=preflop")
        assert r.status_code == 302 and "/jobb/" in r.headers["Location"]
        jid = r.headers["Location"].rsplit("/", 1)[-1]
        for _ in range(600):
            st = c.get(f"/jobb/{jid}/status").get_json()["status"]
            if st in ("klar", "fel"):
                break
            time.sleep(0.1)
        assert st == "klar"
        loc = c.get(f"/jobb/{jid}/rapport").headers["Location"]
        assert loc.endswith("/preflop")
        assert c.get("/").headers["Location"].endswith("/oversikt")
    finally:
        web.VIEWS.update(old)
        web._DB = None


def test_export_without_original_text_and_to_folder(tmp_path):
    """Händer utan sparad originaltext exporteras ändå (återskapade i GG-format, med samma innehåll),
    till en vald mapp som zip eller textfiler; en ny inläsning ger tillbaka originaltexten."""
    import os
    import time
    import zipfile
    from pathlib import Path
    from plo_leak.db import RE_ID
    from plo_leak.parser import parse_hand, split_hands
    os.environ["PLO_LEAK_DB"] = str(tmp_path / "y.db")
    import plo_leak.web as web
    web._DB = None
    web._FT.update(key=None, ft=None)
    try:
        src = Path(__file__).parent / "real"
        orig = {}
        for f in sorted(src.glob("*.txt")):
            for ch in split_hands(f.read_text(encoding="utf-8")):
                m = RE_ID.search(ch[:200])
                if m:
                    orig[m.group(1)] = ch.strip("\n")
        db = web.get_db()
        db.add_paths([src])
        db.con.execute("UPDATE hands SET raw=NULL")
        db.con.commit()
        assert db.missing_raw_count() == db.count()
        c = web.app.test_client()
        assert "saknar originaltext" in c.get("/exportera").get_data(as_text=True)

        def run(data):
            r = c.post("/exportera", data=data)
            assert r.status_code == 302, r.get_data(as_text=True)[:300]
            jid = r.headers["Location"].rsplit("/", 1)[-1]
            for _ in range(300):
                j = c.get(f"/jobb/{jid}/status").get_json()
                if j["status"] in ("klar", "fel"):
                    break
                time.sleep(0.1)
            assert j["status"] == "klar", c.get(f"/jobb/{jid}/fel").get_data(as_text=True)
            loc = c.get(f"/jobb/{jid}/rapport").headers["Location"]
            return c.get(loc).get_data(as_text=True)

        out = tmp_path / "mina export" / "plo"
        page = run({"mapp": str(out), "fmt": "txt"})
        assert "Sparad i" in page and "återskapade" in page
        got = {}
        for f in out.glob("PLO_export_*.txt"):
            for ch in split_hands(f.read_text(encoding="utf-8")):
                got[RE_ID.search(ch[:200]).group(1)] = ch
        hero_ids = {str(x) for x in web._FT["ft"].H["id"]}
        assert set(got) == hero_ids  # alla händer kom med
        for hid, t in got.items():
            a, b = parse_hand(orig[hid]), parse_hand(t)
            r2 = lambda d: {k: round(v, 2) for k, v in d.items() if abs(v) > 1e-9}  # noqa: E731
            assert b is not None and r2(a.invested) == r2(b.invested) and r2(a.collected) == r2(b.collected), hid
            assert [(x.street, x.player, x.kind, round(x.added, 2), round(x.to, 2)) for x in a.actions] == \
                   [(x.street, x.player, x.kind, round(x.added, 2), round(x.to, 2)) for x in b.actions], hid
            assert a.board == b.board and a.hole == b.hole and abs(a.rake - b.rake) < 1e-9
        # mappen och formatet kommer ihåg
        html = c.get("/exportera").get_data(as_text=True)
        assert str(out) in html and 'value="txt" selected' in html
        # zip i vald mapp
        run({"mapp": str(out), "fmt": "zip"})
        assert len(list(out.glob("PLO_export_*.zip"))) == 1
        # ogiltig mapp
        assert c.post("/exportera", data={"mapp": "relativ/mapp"}).status_code == 400
        # ny inläsning med fill_raw ger tillbaka originaltexten
        r = db.add_paths([src], fill_raw=True)
        assert r["raw_filled"] == db.count() and db.missing_raw_count() == 0
        run({"mapp": str(out / "igen"), "fmt": "txt"})
        got2 = {}
        for f in (out / "igen").glob("*.txt"):
            for ch in split_hands(f.read_text(encoding="utf-8")):
                got2[RE_ID.search(ch[:200]).group(1)] = ch.strip("\n")
        assert got2 and all(got2[k] == orig[k] for k in got2)
    finally:
        web._DB = None
        web._FT.update(key=None, ft=None)
        del os.environ["PLO_LEAK_DB"]


def test_sessions():
    """Ny session efter mer än 30 minuters paus; regelbrotten räknas per session och mot snittet."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.sessions import GAP, session_bounds, session_table
    assert session_bounds(np.array([0, 60, 60 + GAP, 60 + 2 * GAP + 1, 60 + 2 * GAP + 2])).tolist() == [0, 3]
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    doc = {"rules": [{"id": "nut|alla|0", "type": "nut", "pos": "alla", "positions": ["HJ", "CO", "BTN", "SB", "BB"],
                      "nut": "0 nöt-egenskaper", "cost": -1.0, "title": "folda 0", "why": "", "level": "bekräftad"}]}
    T = session_table(st, doc)
    S = T["sessions"]
    assert sum(s["hands"] for s in S) == len(st.rows) and T["count"] == len(S)
    ts = np.sort(ft.H["ts"][np.asarray(st.rows)])
    assert T["count"] == len(session_bounds(ts))
    assert sum(s["dev"] for s in S) == sum(len(s["dev_rows"]) for s in S)
    assert all(abs(s["exp_cost"] + s["dev"]) < 1e-9 for s in S)  # kostnad -1 per brott
    first = S[-1]
    assert first["base"] is None  # första sessionen har inget snitt
    assert S[0]["start"] >= S[-1]["start"]  # senaste först
    assert session_table(st, None)["has_rules"] is False


def test_deep_export_split():
    """Stora tabeller delas upp under gränsen; varje del har rubrikraden och inga rader försvinner."""
    from plo_leak.dataexport import split_csv
    data = b"a,b\n" + b"".join(f"{i},{'x' * 50}\n".encode() for i in range(1000))
    parts = split_csv("hands.csv", data, limit=5000)
    assert len(parts) > 1 and all(n.startswith("hands_del") for n in parts)
    assert all(len(p) <= 5000 and p.startswith(b"a,b\n") for p in parts.values())
    body = b"".join(p[4:] for p in parts.values())
    assert body == data[4:]
    assert split_csv("small.csv", b"a\n1\n") == {"small.csv": b"a\n1\n"}


def test_fatigue_time_in_session():
    """Lösare spel sent i sessionerna upptäcks, gränsen rekommenderas och blir en läcka i fokuskön."""
    import numpy as np
    from types import SimpleNamespace
    from plo_leak.fatigue import fatigue_table, focus_item
    rng = np.random.default_rng(5)
    ts, vp = [], []
    t = 1_780_000_000
    for s in range(60):
        for k in range(5 * 60):  # 5 timmar, en hand per minut
            ts.append(t + k * 60)
            vp.append(rng.random() < (0.30 if k < 120 else 0.45))  # lösare efter 2 timmar
        t += 5 * 3600 + 3 * 3600
    n = len(ts)
    H = {"ts": np.array(ts), "vpip": np.array(vp), "pos": np.zeros(n, np.int16), "nplay": np.full(n, 5, np.int8),
         "stake": np.zeros(n, np.int16), "ttype": np.zeros(n, np.int8), "ev": rng.normal(0, 5, n)}
    st = SimpleNamespace(ft=SimpleNamespace(H=H, n=n), rows=np.arange(n), decisions=None)
    F = fatigue_table(st, None)
    assert F["significant"] and F["recommended_h"] == 2.0 and F["limit_h"] == 2.0
    assert not F["rows"][1].get("worse") and F["rows"][2]["worse"]
    assert abs(F["late_share"] - 60.0) < 1
    F3 = fatigue_table(st, None, 3.0)
    assert F3["limit_h"] == 3.0 and F3["recommended_h"] == 2.0
    # ingen skillnad -> ingen rekommendation
    H2 = dict(H, vpip=rng.random(n) < 0.35)
    st2 = SimpleNamespace(ft=SimpleNamespace(H=H2, n=n), rows=np.arange(n), decisions=None)
    assert not fatigue_table(st2, None)["significant"]
    it = focus_item(st, None, F, 20000, 2, 100)
    assert it and it["kind"] == "session" and "2 timmar" in it["title"] and len(it["weeks"]) == 8


def test_careful_costs():
    """Brott som i praktiken kostat mindre än regeln säger räknas med den lägre kostnaden."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.practice import careful_costs, first_rows, violation_index
    from plo_leak.fatigue import hours_text
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    pre = st.decisions.pre
    rules = [{"id": "a", "type": "nut", "pos": "x", "positions": ["HJ", "CO", "BTN", "SB", "BB"], "nut": "0 nöt-egenskaper",
              "cost": -50.0, "title": "a"}]
    c = careful_costs(rules, pre)
    vi = violation_index(rules, pre)
    m = first_rows(pre) & (vi == 0) & ~np.isnan(pre.delta)
    if m.sum() >= 30:
        from plo_leak.fatigue import _cluster_mean_se
        mean, se = _cluster_mean_se(pre.delta[m], pre.clu[m])
        f = max(0.0, 1 - (se / mean) ** 2) if mean < 0 else 0.0
        assert abs(c[0] - min(max(-50.0, mean), 0.0) * f) < 1e-9
        assert careful_costs([{**rules[0], "careful": -1.25}], pre)[0] == -1.25
    else:
        assert c[0] == -50.0
    assert hours_text(1.0) == "1 timme" and hours_text(1.5) == "1,5 timmar"


def test_stake_check():
    """En nivå där du går tydligt sämre flaggas och blir en läcka i fokuskön; slump flaggas inte."""
    import numpy as np
    from types import SimpleNamespace
    from plo_leak.stakecheck import focus_item, stake_check
    rng = np.random.default_rng(9)
    n = 60000
    ts = 1_780_000_000 + np.arange(n) * 60 + (np.arange(n) // 300) * 7200
    stake = (np.arange(n) // 15000) % 2  # växlar nivå var 15 000:e hand
    ev = rng.normal(0, 3, n) + np.where(stake == 1, -0.4, 0.05)
    H = {"ts": ts, "stake": stake.astype(np.int16), "ev": ev, "vpip": rng.random(n) < 0.4, "rake": np.full(n, 0.2)}
    ft = SimpleNamespace(H=H, n=n, label=lambda v, c: ["0.5/1", "1/2"][c])
    st = SimpleNamespace(ft=ft, rows=np.arange(n), decisions=None)
    S = stake_check(st)
    assert S["best"]["stake"] == "0.5/1" and [x["stake"] for x in S["worse"]] == ["1/2"]
    it = focus_item(st, S, 20000, 2, 100)
    assert it and it["kind"] == "stake" and it["per100"] > 0 and "$0.5/$1" in it["title"]
    H2 = dict(H, ev=rng.normal(0, 3, n))
    S3 = stake_check(SimpleNamespace(ft=SimpleNamespace(H=H2, n=n, label=ft.label), rows=np.arange(n), decisions=None))
    assert not S3["worse"]


def _fake_pre(rng, n):
    """Syntetiska preflop-beslut mot en öppning (för 3-bet-reglerna och blocken)."""
    import numpy as np
    from types import SimpleNamespace
    vocab = {"kind": ["fold", "call", "raise"], "spot": ["mot_hojning", "bb_mot_hojning", "rfi"], "pos": ["BTN", "BB", "CO"]}

    class FT:
        def __init__(self, H):
            self.H, self.n = H, len(H["ts"])
        def codes(self, v):
            return {s: i for i, s in enumerate(vocab[v])}
        def code(self, v, s):
            return self.codes(v).get(s, -999)
        def label(self, v, c):
            return vocab[v][c]

    sa = rng.random(n) < 0.4
    hp = rng.random(n) < 0.3
    H = {"sa": sa, "hp": hp, "ts": 1_780_000_000 + np.arange(n) * 60 + (np.arange(n) // 200) * 7200,
         "hole": np.full((n, 6), -1, np.int8), "feats": np.zeros((n, 12), np.int8)}
    ft = FT(H)
    kind = rng.choice([1, 2], n, p=[0.6, 0.4])
    delta = np.where(kind == 2, np.where(sa, np.where(hp, 3.5, 1.0), -2.0), np.where(sa & hp, 0.9, 0.0)) + rng.normal(0, 3, n)
    class Pre(SimpleNamespace):
        def __len__(self):
            return len(self.delta)
    pre = Pre(ft=ft, hidx=np.arange(n), spot=rng.choice([0, 1], n).astype(np.int16), pos=rng.choice([0, 1], n).astype(np.int16),
                          kind=kind.astype(np.int16), delta=delta, clu=np.arange(n) // 200)
    pre.is_spot = lambda *names: np.isin(pre.spot, [vocab["spot"].index(s) for s in names if s in vocab["spot"]])
    pre.label = lambda col, c: vocab[col][int(c)]
    return pre


def test_threebet_rules():
    """3-bets utan suited ess som förlorar mot fold och syner med högt par + suited ess där 3-bet är
    bättre blir regler av typen action; ett brott är fel handling, inte att spela handen."""
    import numpy as np
    from plo_leak.practice import broke_mask, careful_costs, violation_index
    from plo_leak.threebet import threebet_rules
    rng = np.random.default_rng(3)
    pre = _fake_pre(rng, 40000)
    rules = threebet_rules(pre)
    ids = [r["id"] for r in rules]
    assert ids == ["act|3bet_utan_sa", "act|3bet_hp_sa"], ids
    a, b = rules
    assert a["cost"] < -1.0 and a["level"] == "bekräftad" and b["level"] == "trolig" and -2.6 < b["cost"] < 0
    vi = violation_index(rules, pre)
    br = broke_mask(rules, pre, vi)
    raise_c, call_c = 2, 1
    assert ((vi == 0) <= ~pre.ft.H["sa"]).all()
    assert (br[vi == 0] == (pre.kind[vi == 0] == raise_c)).all()
    assert (br[vi == 1] == (pre.kind[vi == 1] == call_c)).all()
    c = careful_costs(rules, pre, vi)
    assert c[1] == b["cost"]  # jämförelsen mellan två handlingar behåller sin försiktiga kostnad
    # utan läcka blir det inga regler
    pre.delta = rng.normal(0.5, 3, len(pre.delta))
    assert threebet_rules(pre) == []


def test_development_blocks():
    """Blocken om 5 000 händer: läckkostnaden följer hur ofta du bryter mot reglerna, och en regel du
    börjar bryta mot oftare ger en varning om en ny läcka."""
    import numpy as np
    from types import SimpleNamespace
    from plo_leak.blocks import block_table
    from plo_leak.threebet import threebet_rules
    rng = np.random.default_rng(5)
    n = 30000
    pre = _fake_pre(rng, n)
    rules = threebet_rules(pre)
    assert rules
    # de senaste 10 000 händerna 3-bettar du utan suited ess mycket oftare
    late = np.arange(n) >= n - 10000
    pre.kind = np.where(late & ~pre.ft.H["sa"], 2, np.where(~pre.ft.H["sa"], 1, pre.kind)).astype(np.int16)
    pre.kind[~late & ~pre.ft.H["sa"] & (rng.random(n) < 0.05)] = 2
    H = pre.ft.H
    H.update(ev=rng.normal(0, 3, n), vpip=rng.random(n) < 0.4, pos=rng.choice([0, 1], n).astype(np.int16),
             nplay=np.full(n, 5, np.int16), stake=np.zeros(n, np.int16), ttype=np.zeros(n, np.int16))
    st = SimpleNamespace(ft=pre.ft, rows=np.arange(n), decisions=SimpleNamespace(pre=pre))
    T = block_table(st, {"rules": rules})
    assert len(T["blocks"]) == 6 and all(b["hands"] == 5000 for b in T["blocks"])
    row = next(r for r in T["rules"] if r["id"] == "act|3bet_utan_sa")
    assert row["cells"][0]["rate"] < 10 and row["cells"][-1]["rate"] > 90
    assert T["blocks"][-1]["cost100"] > T["blocks"][0]["cost100"] > 0
    assert any(w["kind"] == "regel" and "3-betta inte" in w["title"] for w in T["warnings"])
    assert block_table(SimpleNamespace(ft=pre.ft, rows=np.arange(9000), decisions=None), {}) == {}


def test_protect_combos_and_noise_rules():
    """En lönsam kombination i en gränsregel undantas, och en regel vars brott inte ens är en felmarginal
    under noll får kostnaden 0 (och tas bort när reglerna byggs)."""
    import numpy as np
    from plo_leak.practice import careful_costs, protect_combos, rule_mask
    rng = np.random.default_rng(11)
    pre = _fake_pre(rng, 30000)
    H = pre.ft.H
    H["rd"] = np.zeros(len(pre), bool)
    hp_sa = H["hp"] & H["sa"]
    pre.delta = np.where(hp_sa, 2.0, -0.8) + rng.normal(0, 3, len(pre))
    pre.kind = np.full(len(pre), 1, np.int16)
    rule = {"id": "x", "type": "combo", "spot": "mot_hojning", "pos": "BTN", "combo": "ingen", "cost": -1.0, "title": "t"}
    # gränsregel som träffar allt i mot_hojning/BTN: testa via en combo-regel med except_combo-logik
    r2 = {**rule, "type": "cutoff", "thr": 1e9, "weights": [0.0] * 12, "num_cards": 6}
    H["nh"] = np.full(len(pre), 6, np.int8)
    import plo_leak.ranges as rg
    old = rg.pre_features
    rg.pre_features = lambda d: np.zeros((len(pre), 12))
    try:
        out = protect_combos([r2], pre)
        assert out[0].get("except_combo") == ["högt par + suited ess"], out[0].get("except_combo")
        m = rule_mask(out[0], pre)
        assert not (m & hp_sa).any()
    finally:
        rg.pre_features = old
    # brus: brotten är bara lite under noll
    pre.delta = rng.normal(-0.02, 3, len(pre))
    info = careful_costs([rule], pre, detail=True)
    assert info[0]["n"] > 1000
    z = info[0]["real"] / info[0]["se"]
    c = careful_costs([rule], pre)
    if z > -1:
        assert c[0] == 0.0
    else:
        assert abs(c[0] - max(-1.0, info[0]["real"]) * (1 - 1 / z ** 2)) < 1e-9
    # en tydlig förlust krymps knappt
    pre.delta = rng.normal(-1.5, 3, len(pre))
    c = careful_costs([rule], pre)
    assert -1.0 <= c[0] < -0.9


def test_river_bluff_table():
    """Foldandelen mot dina river-bets per storlek jämförs med vad en bluff behöver."""
    import numpy as np
    from types import SimpleNamespace
    from plo_leak.summary import river_bluff_table
    rng = np.random.default_rng(2)
    n = 4000
    frac = rng.choice([0.3, 0.5, 0.75, 1.0], n)
    resp = np.where(rng.random(n) < 0.62, 0, 1).astype(np.int8)
    V = {"hidx": np.arange(n), "role": rng.choice([0, 1, 2], n).astype(np.int8), "frac": frac, "resp": resp,
         "bf": rng.random(n)}  # andel motståndarhänder som slår dig (0–1)
    V["resp"][V["role"] == 2] = -1
    ft = SimpleNamespace(t={"rvb": V}, n=n, H={"clu": np.arange(n) // 10, "pot": np.full(n, 20.0)},
                         subset_mask=lambda mask, name: mask[V["hidx"]])
    T = river_bluff_table(ft, np.arange(n))
    assert len(T["sizes"]) == 4 and T["any_edge"]
    pot = next(s for s in T["sizes"] if s["size"] == "Pott eller mer")
    assert abs(pot["need_pct"] - 50) < 1e-6 and pot["edge"]
    assert T["ip"] and all(0 <= r["bet_pct"] <= 100 for r in T["ip"])
    assert T["est100"] > 0


def test_river_call_guide():
    """Syna-gränsen på river: syner med starka händer går plus, med svaga minus; folds med en hand starkare
    än gränsen räknas som missar."""
    import numpy as np
    from types import SimpleNamespace
    from plo_leak.summary import river_call_guide
    rng = np.random.default_rng(4)
    n = 6000
    bf = rng.random(n)  # andel motståndarhänder som slår dig
    kind = np.where(rng.random(n) < 0.5, 1, 0).astype(np.int16)  # 0 fold, 1 call
    delta = np.where(bf < 0.25, 8.0, -6.0) + rng.normal(0, 4, n)
    vocab = {"kind": ["fold", "call", "raise"], "size": ["liten (under 40 % av potten)", "medel (40–60 %)",
                                                        "stor (60–85 %)", "pott eller mer (över 85 %)"]}
    R = {"hidx": np.arange(n), "bf": bf, "kind": kind, "delta": delta, "size": rng.choice([0, 1], n).astype(np.int16),
         "cat": np.full(n, 5, np.int8)}
    ft = SimpleNamespace(t={"riv": R}, n=n, H={"clu": np.arange(n) // 20, "ts": np.arange(n), "id": np.array([f"h{i}" for i in range(n)], dtype=object)},
                         subset_mask=lambda mask, name: mask[R["hidx"]],
                         code=lambda v, s: vocab[v].index(s) if s in vocab[v] else -999)
    G = river_call_guide(ft, np.arange(n))
    assert len(G["sizes"]) == 2
    for z in G["sizes"]:
        assert abs(z["thr"] - 0.25) < 1e-9, z["thr"]
        assert 40 < z["fold_pct"] < 60
    assert G["missed"] and G["val100"] > 0


def test_threebet_trainer():
    """3-bet-träningen: högt par + suited ess = 3-betta; utan suited ess = syna eller folda (aldrig 3-bet);
    suited ess utan högt par = 3-betta eller syna; en foldregel går före."""
    from plo_leak.cards import nut_qualities
    from plo_leak.practice import trainer_hand, trainer_scenarios
    doc = {"variant": "PLO6", "rules": [
        {"id": "nut|BTN|0", "type": "nut", "pos": "BTN", "nut": "0 nöt-egenskaper", "cost": -1.0, "title": "BTN: 0", "level": "trolig"},
        {"id": "act|3bet_utan_sa", "type": "action", "cond": "no_sa", "bad_kind": "raise", "title": "a", "level": "bekräftad", "cost": -1},
        {"id": "act|3bet_hp_sa", "type": "action", "cond": "hp_sa", "bad_kind": "call", "title": "b", "level": "trolig", "cost": -1}]}
    keys = [s["key"] for s in trainer_scenarios(doc)]
    assert keys[:4] == ["3bet|BB", "3bet|SB", "3bet|BTN", "3bet|CO"]
    seen = set()
    for seed in range(60):
        h = trainer_hand(doc, "BTN", seed=seed, spot="3bet")
        hp, sa, rd = nut_qualities([tuple(c) for c in h["cards"]])
        if hp and sa:
            assert h["ok"] == ["raise"]
        elif not (hp or sa or rd):
            assert h["ok"] == ["fold"]  # foldregeln går före
        elif not sa:
            assert h["ok"] == ["call", "fold"]
        else:
            assert h["ok"] == ["raise", "call"]
        seen.add(tuple(h["ok"]))
    assert ("raise",) in seen and ("call", "fold") in seen
    assert trainer_hand(doc, "HJ", spot="3bet") is None


def test_holdout_validate():
    """Test på nya händer: en regel som förlorar även på de nya händerna håller; en som vänder tas bort."""
    import numpy as np
    from types import SimpleNamespace
    import plo_leak.holdout as ho
    from plo_leak.threebet import threebet_rules
    rng = np.random.default_rng(8)
    n = 120000
    pre = _fake_pre(rng, n)
    rules = threebet_rules(pre)
    assert [r["id"] for r in rules] == ["act|3bet_utan_sa", "act|3bet_hp_sa"]
    for r in rules:
        r["careful"] = r["cost"]
    cut = int(pre.ft.H["ts"][int(n * 2 / 3)])
    # vänd 3-bet-läckan utan suited ess på de nya händerna
    new = pre.ft.H["ts"][pre.hidx] >= cut
    flip = new & (pre.kind == 2) & ~pre.ft.H["sa"]
    pre.delta[flip] = rng.normal(3.0, 3, flip.sum())
    st = SimpleNamespace(rows=np.arange(n), decisions=SimpleNamespace(pre=pre), ft=pre.ft)
    old = ho._discover_old
    ho._discover_old = lambda *a, **k: ({"rules": rules}, cut, int(n * 2 / 3), n - int(n * 2 / 3))
    try:
        out = ho.validate({"rules": rules, "dropped": []}, st, "Hero")
    finally:
        ho._discover_old = old
    ids = [r["id"] for r in out["rules"]]
    assert "act|3bet_utan_sa" not in ids and any(d["id"] == "act|3bet_utan_sa" for d in out["dropped"])
    hp = next(r for r in out["rules"] if r["id"] == "act|3bet_hp_sa")
    assert hp["holdout"]["verdict"] == "inte oberoende" and hp["level"] == "trolig" and hp["careful"] == 0  # action contrasts remain observational
    assert out["holdout"]["n_new"] > 30000


def test_when_table():
    """Tid på dygnet: ett block som går tydligt bättre hittas, och läckkartan får ett försiktigt värde."""
    import numpy as np
    from types import SimpleNamespace
    from plo_leak.timeofday import when_table
    rng = np.random.default_rng(1)
    n = 40000
    ts = 1_780_000_000 + np.arange(n) * 300 + (np.arange(n) // 50) * 3600
    hour = (ts // 3600) % 24
    ev = rng.normal(0, 3, n) + np.where((hour >= 6) & (hour < 12), 0.3, -0.1)
    H = {"ts": ts, "ev": ev, "stake": np.zeros(n, np.int16)}
    ft = SimpleNamespace(H=H, n=n, label=lambda v, c: "0.5/1")
    W = when_table(SimpleNamespace(ft=ft, rows=np.arange(n)))
    assert W["best"] == "06–12" and W["significant"] and W["value100"] > 0
    assert len(W["grid"]) == 4 and W["cols"][1]["label"] == "$0.5/$1"


def test_aggression_facts():
    """Postflop-besluten hamnar i faktatabellen och aggressionsmåtten går att räkna."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.aggr import aggression, session_stab
    from plo_leak.facts import extract
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    P = ft.t["pfd"]
    assert len(P["hidx"]) > 0 and set(np.unique(P["st"])) <= {1, 2, 3}
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    A = aggression(st)
    if A:
        assert len(A["streets"]) == 3 and 0 <= A["stab"] <= 100
        t0, t1 = int(ft.H["ts"].min()), int(ft.H["ts"].max())
        s = session_stab(st, t0, t1, A["stab"])
        assert s is None or 0 <= s["stab"] <= 100


def test_watch_folder_mac_paths(tmp_path, monkeypatch):
    import os
    from plo_leak import watch
    monkeypatch.setattr(watch.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Downloads").mkdir()
    if os.name != "nt":
        assert watch._foreign("C:\\\\Users\\\\a\\\\Downloads")
        assert watch.folder_of({"watch": "C:\\\\Users\\\\a\\\\Downloads"}) == str(tmp_path / "Downloads")
    assert watch.normalize("~/Hämtade filer") == str(tmp_path / "Downloads")
    assert watch.folder_problem(str(tmp_path / "saknas")).startswith("Mappen")
    assert watch.folder_problem(str(tmp_path / "Downloads")) == ""


def test_session_hands_match_session_file():
    """Pott-numren på sessionssidan är samma som i sessionsfilen, och alla sessionens händer finns med."""
    import re
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.sessionfile import build, session_hands
    from plo_leak.sessions import session_detail, session_table
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    T = session_table(st, None)
    s = session_detail(T, T["sessions"][0]["key"], st, hero)
    rows = session_hands(st, s, None)
    assert len(rows) == s["hands"]
    top = sorted((r for r in rows if r["nr"]), key=lambda r: r["nr"])
    text = build(st, s, hero, None, None, "test")
    ids = re.findall(r"### Pott \d+: (\S+)", text)
    assert [r["id"] for r in top] == ids
    assert all(abs(r["luck"] - (r["net"] - r["ev"])) < 1e-9 for r in rows)


def test_beat_n_six_card_and_blockers():
    """"Slår dig" räknas mot 6-kortshänder med dina kort borttagna – inte som 2-kortskombinationer."""
    from plo_leak.board import BoardTable
    from plo_leak.cards import parse_cards
    bt = BoardTable(parse_cards("Kd 9d 7c 4d 2s"))
    jhigh = parse_cards("Jd Td Ts 9c 8c 2h")
    assert bt.beat_frac(jhigh) < 0.03            # gamla 2-kortsmåttet: alldeles för lågt för PLO6
    assert 0.10 < bt.beat_n(jhigh) < 0.25        # mot 6-kortshänder: ca 16 %
    assert bt.beat_n(jhigh) == bt.beat_n(jhigh)  # samma svar varje gång
    # blocker: med Qd själv kan motståndaren inte ha Q-hög färg – färre händer slår dig
    qblock = parse_cards("Jd Td Qd 9c 8c 2h")
    assert bt.beat_n(qblock) < bt.beat_n(jhigh)
    assert bt.beat_n(parse_cards("Ad 3d Ts 9c 8c 2h")) == 0.0  # nötfärgen


def test_river_coach_from_fact_table():
    """River-coachen körs på river-situationerna i faktatabellen och ger råd per hand med EV per alternativ."""
    import sys
    import numpy as np
    sys.path.insert(0, str(HERE.parent / "tools"))
    from generate_sample import Table
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract as fx
    from plo_leak.parser import parse_text
    from plo_leak.rivercoach import coach, line_text
    t = Table(3)
    hands = parse_text("\n\n\n".join(t.play() for _ in range(8000)))
    ft = fx(hands, "Hero")
    assert len(ft.t["rsp"]["hidx"]) > 500 and len(ft.t["rsp"]["obj"]) == len(ft.t["rsp"]["hidx"])
    st = build_stats(ft, np.ones(ft.n, bool), "Hero", {h.id: h for h in hands}.get)
    C = coach(st, "Hero")
    assert C["n_dec"] > 100 and set(C["ok"]) == {"mot_bet", "ip_efter_check"}
    facing = [e for e in C["decisions"].values() if e["kind"] == "mot_bet"]
    ip = [e for e in C["decisions"].values() if e["kind"] == "ip_efter_check"]
    assert facing and ip
    e = facing[0]
    assert 0 <= e["p_win"] <= 1 and 0 < e["need"] < 1 and line_text(e) == ""  # 2.77: dold när kontrollen inte klaras
    assert "vinstchans mot hans linje" in line_text({**e, "ok": True})
    assert "check" in ip[0]["ev"] and "bäst:" in line_text({**ip[0], "ok": True})


def test_high_rundown_exempt_vs_3bet():
    """Höga rundowns (5+ i följd, högsta kort J+) foldas inte av gränsregler mot 3-bet; låga rundowns gör det."""
    from plo_leak.cards import parse_cards
    from plo_leak.practice import high_rundown, violations
    assert high_rundown(parse_cards("Qs Jd Th 9s 8d 7c")) and high_rundown(parse_cards("Kh Qh Jd Td 9s 2c"))
    assert high_rundown(parse_cards("Jh Tc 9h 8c 7s 2s"))
    assert not high_rundown(parse_cards("9s 8s 7d 6d 5c 4h")) and not high_rundown(parse_cards("Th 9h 8d 7d 4c 3s"))
    rule = {"id": "cut|mot_3bet_oop|CO", "type": "cutoff", "spot": "mot_3bet_oop", "pos": "CO", "thr": 99.0,
            "weights": [0.0] * 12, "num_cards": 6, "title": "CO", "cost": -1}
    ex = []
    assert violations([rule], "mot_3bet_oop", "CO", parse_cards("Qs Jd Th 9s 8d 7c"), ex) == [] and ex
    assert violations([rule], "mot_3bet_oop", "CO", parse_cards("9s 8s 7d 6d 5c 4h")) == [rule]
    rfi = {**rule, "id": "cut|rfi|CO", "spot": "rfi"}
    assert violations([rfi], "rfi", "CO", parse_cards("Qs Jd Th 9s 8d 7c")) == [rfi]  # gäller bara mot 3-bet


def test_model_analyses_reused_across_dates(tmp_path):
    """Modellanalyserna räknas en gång per data (variant/bord/nivå) – inte om när bara datum/senaste N ändras."""
    from pathlib import Path
    from plo_leak.db import HandDB
    from plo_leak.pipeline import build
    from plo_leak.selection import Selection
    db = HandDB(tmp_path / "m.db")
    db.add_paths([Path(__file__).parent / "real"], fill_raw=True)
    hero = db.detect_hero()
    store = db.facts(hero)
    store.sync(db)
    ft, sig, cdir = store.load(), store.signature(), tmp_path / "res"
    t = {}
    for lab, kw in (("senaste", {"latest": 50}), ("hela", {}), ("datum", {"date_from": "2026-07-01"})):
        col = {}
        build(ft, hero, db.get_hand, Selection(games=("PLO6",), **kw), use_db=True, data_sig=sig, cache_dir=cdir,
              as_context=True, collect=col)
        t[lab] = col["timings"]
    assert t["senaste"]["leaks"][0] == "räknat"
    assert t["hela"]["leaks"][0] == "sparat" and t["datum"]["river_coach"][0] == "sparat"
    assert t["datum"]["hourly"][0] == "räknat"  # beskrivande delar följer urvalet
    col = {}
    C = build(ft, hero, db.get_hand, Selection(games=("PLO6",), latest=40), use_db=True, data_sig=sig, cache_dir=cdir,
              as_context=True, collect=col, model_on_selection=True)
    assert col["timings"]["leaks"][0] == "räknat" and C["filters"]["model_sel"]  # manuellt: läckor på urvalet


def test_vs3bet_nut_rule():
    """Mot 3-bet: händer med 0 nöt-egenskaper som förlorar mot fold blir en regel; lönsamma undergrupper undantas."""
    import numpy as np
    import plo_leak.subgroups as sg
    from plo_leak.threebet import vs3bet_nut_rule
    rng = np.random.default_rng(1)
    n = 900
    spots = {"mot_3bet_oop": 0, "mot_3bet_ip": 1, "rfi": 2}
    sc = rng.integers(0, len(sg.STRUCT), n)
    k_sk = sg.STRUCT.index("dubbelsuited + suited kung")
    dl = np.where(sc == k_sk, 5.0, -4.0) + rng.normal(0, 3, n)
    sp_arr, pos_arr = rng.integers(0, 2, n), rng.integers(0, 3, n)

    class FT:
        H = {"nut": np.zeros(n, np.int16), "feats": np.zeros((n, 12), np.int8)}
        def codes(self, v): return {"0 nöt-egenskaper": 0} if v == "nut" else {}
        def label(self, v, c): return ["HJ", "CO", "BTN"][c]

    class Pre:
        ft = FT(); hidx = np.arange(n); spot = sp_arr; delta = dl
        clu = np.arange(n) // 10; pos = pos_arr; kind = np.zeros(n, np.int8)
        def __len__(self): return n
        def is_spot(self, *names): return np.isin(self.spot, [spots[x] for x in names])
        def label(self, v, c): return self.ft.label(v, c)

    orig = sg.struct_codes
    sg.struct_codes = lambda feats: sc
    try:
        rules = vs3bet_nut_rule(Pre())
    finally:
        sg.struct_codes = orig
    assert len(rules) == 1 and rules[0]["level"] == "bekräftad" and rules[0]["cost"] < -3
    assert "dubbelsuited + suited kung" in rules[0]["except"]  # tillräckligt många händer (≥ 100) och plus and rules[0]["spots"] == ["mot_3bet_oop", "mot_3bet_ip"]
    from plo_leak.practice import violations
    from plo_leak.cards import parse_cards
    r = {**rules[0], "except": None}
    weak = parse_cards("9s 8d 6c 5h 3d 2c")  # inget högt par, inget suited ess, ingen rundown-nöt
    assert violations([r], "rfi", "HJ", weak) == []  # gäller bara mot 3-bet


def test_guideline_aa_suited_ace():
    """Riktlinje (inte regel): syna inte en 3-bet med AA + suited ess (~100 bb, eller ur position)."""
    from plo_leak.cards import parse_cards as P
    from plo_leak.guidelines import aa_suited_ace, preflop_note
    assert aa_suited_ace(P("As Ah Ks Jd 8h 4c")) and not aa_suited_ace(P("As Ah Kc Jd 8c 4d"))
    assert not aa_suited_ace(P("As Ah Ac Kd 8s 4h"))  # trips ess räknas inte
    # 2.70: riktlinjen höll bara i hälften av passen (granskning 2026-11-12) – visas inte längre
    assert preflop_note("mot_3bet_ip", "call", P("As Ah Ks Jd 8h 4c"), 100) == ""


def _sim_pre(n, rng, mean):
    """Konstgjorda beslut mot 3-bet (0 nöt-egenskaper) med tunga svansar, grupperade i spelpass."""
    import numpy as np

    class FT:
        def __init__(self, H): self.H = H
        def codes(self, v): return {"nut": {"0 nöt-egenskaper": 0}, "spot": {"mot_3bet_oop": 0, "mot_3bet_ip": 1},
                                    "pos": {"BTN": 0, "CO": 1, "HJ": 2}}[v]
        def code(self, v, s): return self.codes(v).get(s, -999)
        def label(self, v, c): return {v2: k for k, v2 in self.codes(v).items()}[int(c)]
    feats = np.zeros((n, 12), np.int8)
    g = rng.integers(0, 6, n)
    for k, (s5, s8, s11) in enumerate([(3, 0, 0), (2, 4, 0), (2, 0, 1), (2, 0, 0), (1, 4, 0), (1, 0, 0)]):
        feats[g == k, 5], feats[g == k, 8], feats[g == k, 11] = s5, s8, s11

    class Pre:
        pass
    p = Pre()
    p.ft = FT({"nut": np.zeros(n, np.int16), "feats": feats})
    p.hidx, p.spot = np.arange(n), np.zeros(n, np.int16)
    p.pos, p.kind = rng.integers(0, 3, n).astype(np.int16), np.zeros(n, np.int16)
    p.delta = rng.standard_t(3, n) * 15 + mean
    p.clu = rng.integers(0, n // 8, n).astype(np.int64)
    p.__class__.__len__ = lambda self: len(self.delta)
    p.is_spot = lambda *names: np.isin(p.spot, [p.ft.code("spot", x) for x in names])
    p.label = lambda col, c: p.ft.label(col, c)
    return p


def test_vs3bet_rule_not_confirmed_on_noise():
    """Granskning 2.54: undantagen väljs i ena halvan och testas i andra – på slumpdata blir regeln sällan bekräftad."""
    import numpy as np
    from plo_leak.threebet import vs3bet_nut_rule
    rng = np.random.default_rng(11)
    R = 120
    conf = sum(1 for _ in range(R) if [r for r in vs3bet_nut_rule(_sim_pre(1200, rng, 0.0)) if r["level"] == "bekräftad"])
    assert conf / R <= 0.07, conf / R
    strong = sum(1 for _ in range(30) if [r for r in vs3bet_nut_rule(_sim_pre(1200, rng, -5.0)) if r["level"] == "bekräftad"])
    assert strong >= 25  # en verklig läcka hittas fortfarande


def test_careful_cost_drops_profitable_breaks():
    """Granskning 2.54: regler där brotten gått plus mot fold ska bort (faktor 0), inte behållas."""
    import numpy as np
    from plo_leak.practice import careful_costs
    rng = np.random.default_rng(3)
    rule = {"id": "x", "type": "nut", "spots": ["mot_3bet_oop"], "positions": ["BTN", "CO", "HJ"], "pos": "mot 3-bet",
            "nut": "0 nöt-egenskaper", "cost": -1.0}
    d = careful_costs([rule], _sim_pre(3000, rng, 3.0), detail=True)[0]
    assert d["n"] >= 30 and d["factor"] == 0.0


def test_rule_matching_respects_spots():
    """Granskning 2.54: en regel mot 3-bet är inte samma regel som en öppningsregel med samma nöt-etikett."""
    from plo_leak.holdout import _match
    from plo_leak.likely import covered
    r3b = {"id": "nut3b|mot 3-bet|0 nöt-egenskaper", "type": "nut", "spots": ["mot_3bet_oop", "mot_3bet_ip"],
           "positions": ["BTN", "CO", "HJ"], "pos": "mot 3-bet", "nut": "0 nöt-egenskaper"}
    rfi = {"id": "nut|UTG|0 nöt-egenskaper", "type": "nut", "positions": ["UTG", "HJ"], "pos": "UTG", "nut": "0 nöt-egenskaper"}
    assert _match(r3b, [rfi]) is None and _match(r3b, [r3b]) is r3b
    btn = {"rule": {"id": "nut|BTN|0", "type": "nut", "positions": ["BTN"], "pos": "BTN", "nut": "0 nöt-egenskaper"}}
    assert not covered(btn, [r3b])
    co = {"rule": {"id": "combo|rfi|CO|ingen", "type": "combo", "spot": "rfi", "pos": "CO", "combo": "ingen"}}
    assert not covered(co, [r3b])


def test_stakecheck_bonferroni():
    from plo_leak.stakecheck import _z_bonf
    assert abs(_z_bonf(1) - 1.96) < 0.01 and _z_bonf(3) > 2.3


def test_postflop_guideline_notes():
    from plo_leak.guidelines import GUIDELINES, postflop_note
    assert len([g for g in GUIDELINES if g["area"] == "postflop"]) == 16
    base = {"players": 2, "ip": 1, "pfa": 0, "hand": "par", "flush_draw": "", "straight_outs": 0, "size_pct": "",
            "beat_frac": "", "prev_aggressor": "annan", "pot_type": "enkel höjning", "made_frac": "", "facing_allin": "",
            "facing_pct": ""}
    # 2.77: #1 (river-bluff var tredje gång) ersatt av river-bluff-test v2, #2 nedgraderad (strider mot teori)
    assert "#1" not in postflop_note({**base, "street": "river", "facing": "ingen", "action": "check", "beat_frac": 0.8, "ip": 0})
    assert postflop_note({**base, "street": "river", "facing": "ingen", "action": "check", "beat_frac": 0.3}) == ""
    assert "#2" not in postflop_note({**base, "street": "flop", "facing": "bet", "action": "call", "made_frac": 0.2, "facing_allin": 0})
    assert postflop_note({**base, "street": "flop", "facing": "bet", "action": "call", "made_frac": 0.2, "facing_allin": 1}) == ""
    assert "#3" in postflop_note({**base, "street": "flop", "facing": "ingen", "action": "check", "pfa": 1, "ip": 0, "made_frac": 0.1})
    assert "#4" in postflop_note({**base, "street": "turn", "facing": "ingen", "action": "check", "prev_aggressor": "ingen", "made_frac": 0.7})
    assert "#5" in postflop_note({**base, "street": "turn", "facing": "bet", "action": "fold", "facing_allin": 1, "flush_draw": "ja",
                                  "facing_pct": 40})
    assert "#6" in postflop_note({**base, "street": "flop", "facing": "ingen", "action": "check", "pfa": 1, "ip": 1, "made_frac": 0.5})
    assert postflop_note({**base, "street": "river", "facing": "ingen", "action": "check", "beat_frac": 0.05, "players": 3}) == ""  # top 10% is not nuts
    assert postflop_note({**base, "street": "turn", "facing": "ingen", "action": "check", "prev_aggressor": "hero", "hand": "färg",
                          "made_frac": 0.05}) == ""  # turn-barrel med färdig färg höll inte i omgång 2
    # 2.67: tre nya riktlinjer
    assert postflop_note({**base, "street": "river", "facing": "raise", "action": "call", "hand": "kåk", "ip": 1,
                          "board_paired": 1, "made_frac": 0.06}) == ""  # 2.70: #12 inte verifierad (1,8 felmarginaler)
    assert "#12" not in postflop_note({**base, "street": "river", "facing": "raise", "action": "call", "hand": "kåk", "ip": 1,
                                       "board_paired": 1, "made_frac": 0.0})  # nöten: syna
    assert "#11" in postflop_note({**base, "street": "river", "facing": "bet", "action": "call", "hand": "två par",
                                   "board_paired": 0, "facing_size_pct": 80, "made_frac": 0.3})
    assert postflop_note({**base, "street": "river", "facing": "bet", "action": "call", "hand": "stege",
                          "board_paired": 0, "facing_size_pct": 80, "made_frac": 0.1}) == ""  # stegar: syna
    # 2.69: #10 omskriven efter granskningen
    assert postflop_note({**base, "street": "flop", "facing": "raise", "action": "raise", "hand": "par", "flush_draw": "nöt"}) == ""
    # 2.71: #10 är bara en granskningsuppmaning (ingen fryst regel) och visas inte
    assert "" == postflop_note({**base, "street": "flop", "facing": "raise", "action": "call", "hand": "par",
                                          "flush_draw": "ja", "straight_outs": 4, "facing_allin": 0})
    assert "" == postflop_note({**base, "street": "flop", "facing": "raise", "action": "call", "hand": "par", "flush_draw": "nöt",
                                   "straight_outs": 8, "facing_allin": 0, "eff_stack_bb": 80, "pot_bb": 30, "to_call_bb": 10})
    assert "#11" in postflop_note({**base, "street": "river", "facing": "bet", "action": "call", "hand": "kåk",
                                   "board_paired": 1, "facing_size_pct": 80, "made_frac": 0.2})
    assert "#11" not in postflop_note({**base, "street": "river", "facing": "bet", "action": "call", "hand": "kåk",
                                       "board_paired": 1, "facing_size_pct": 80, "made_frac": 0.14})


def test_postflop_guidelines_on_overview():
    from plo_leak.report import _postflop_leaks
    assert not [x for x in _postflop_leaks({}) if x.get("guide")]  # 2.81: tomt analysresultat – inga uppskattade kostnader
    L = _postflop_leaks({"leaks": []})
    g = [x for x in L if x.get("guide")]
    assert len(g) == 6 and max(x["per100"] for x in g) == 1.0  # 2.77: #1 dold, #2 #8 #14 nedgraderade, preflop-riktlinjer ersatta av solvern
    assert all(x.get("guide") for x in g)
    assert all(x["title"] and x["link"] in ("postflop", "preflop") for x in g)
    assert not any(x["title"].startswith("Flop: din bet blir höjd") for x in g)  # struken i nattanalysen
    assert len([x for x in _postflop_leaks({"leaks": []}, {"pf_river_bluff"}) if x.get("guide")]) == 6
    assert all("uppskattning" in x["estimate"] for x in g)


def test_postflop_focus_items():
    """Postflop-fokus (#1 river-bluff, #2 flop-3-bet): räknas från faktatabellen, mål och vecka för vecka."""
    import numpy as np
    from plo_leak.aggregate import build_stats
    from plo_leak.facts import extract
    from plo_leak.pffocus import SPECS, _spots, focus_items, good
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    P = ft.t["pfd"]
    assert len(P["bf"]) == len(P["hidx"]) == len(P["size"])
    riv = P["st"] == 3
    assert ((P["bf"][riv] >= 0) | (P["bf"][riv] == -1)).all() and (P["bf"][~riv] == -1).all()
    sp = _spots(ft, P, np.ones(len(P["hidx"]), bool))
    assert set(sp) == {s["id"] for s in SPECS}
    st = build_stats(ft, np.ones(ft.n, bool), hero, {h.id: h for h in hs}.get)
    for it in focus_items(st, 20000, 2):
        assert it["kind"] == "pf" and it["per100"] >= 0 and 0 <= it["rate"] <= 100 and len(it["weeks"]) == 8
        assert it["opps"] >= it["dev"] and len(it["dev_rows"]) <= it["dev"]
    assert good({"dir": "min", "goal": 45}, 50) and not good({"dir": "max", "goal": 5}, 10)


def test_v258_guidelines():
    from plo_leak.guidelines import hj_sa_low, postflop_note, preflop_note
    from plo_leak.pffocus import SPECS
    assert [s["id"] for s in SPECS] == ["pf|river_bluff"] and SPECS[0]["eff"] == 1.9
    A9 = [(14, 'h'), (9, 'h'), (8, 's'), (7, 'd'), (4, 'c'), (3, 's')]
    assert hj_sa_low(A9) and preflop_note("rfi", "raise", A9, 100, "HJ") == ""  # 2.70: inte verifierad – visas inte
    assert not hj_sa_low([(14, 'h'), (14, 's'), (8, 'h'), (7, 'd'), (4, 'c'), (3, 's')])
    r = {"street": "flop", "facing": "raise", "action": "raise", "players": 2, "hand": "två par"}
    assert postflop_note(r) == ""  # gamla #2 borttagen
    assert postflop_note({"street": "flop", "facing": "bet", "action": "call", "players": 2, "hand": "triss"}) == ""  # triss-höjning höll inte (omgång 2)


def test_bb_0nut_guideline():
    from plo_leak.guidelines import ds_suited_king, preflop_note
    weak = [(9, 'h'), (8, 'c'), (6, 'h'), (4, 'd'), (3, 'c'), (2, 's')]       # 0 nöt-egenskaper, dubbelsuited utan kung
    dsk = [(13, 'h'), (9, 'h'), (8, 'c'), (6, 'c'), (4, 'd'), (2, 's')]      # dubbelsuited + suited kung
    assert preflop_note("bb_mot_hojning", "call", weak, 100) == ""  # 2.70: trolig, inte verifierad – visas inte
    assert ds_suited_king(dsk) and preflop_note("bb_mot_hojning", "call", dsk, 100) == ""
    assert preflop_note("bb_mot_hojning", "fold", weak, 100) == ""


def test_postflop_rows_new_columns():
    """2.62: all-in-flaggor, effektiv stack, handstyrka på alla gator och resultat per pott."""
    from plo_leak.postflop_rows import HEADER, rows_for_hand
    hs, hero = _real_hands()
    ix = {k: i for i, k in enumerate(HEADER)}
    n = fa = mf = 0
    for h in hs[:60]:
        for x in rows_for_hand(h, hero, 1.0):
            n += 1
            assert len(x) == len(HEADER)
            assert x[ix["hero_allin"]] in (0, 1) and x[ix["eff_stack_bb"]] >= 0
            if x[ix["facing"]] == "ingen":
                assert x[ix["facing_allin"]] == ""
            else:
                fa += 1
                assert x[ix["facing_allin"]] in (0, 1)
            if x[ix["street"]] != "river" and x[ix["made_frac"]] != "":
                mf += 1
                assert 0 <= x[ix["made_frac"]] <= 1
            if x[ix["from_here_pot"]] != "":
                assert abs(x[ix["from_here_pot"]] * x[ix["pot_bb"]]) <= abs(x[ix["from_here_bb"]]) + 1e-6 + abs(x[ix["from_here_bb"]])
    assert n and fa and mf


def test_quick_update_reuses_models(tmp_path=None):
    """Snabb uppdatering: modellanalyserna återanvänds från senaste fulla analysen, regler sparas inte om."""
    import tempfile
    from pathlib import Path
    import numpy as np
    from plo_leak.facts import extract
    from plo_leak.pipeline import QUICK_MAX, _model_sig_get, build
    from plo_leak.selection import Selection
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    by = {h.id: h for h in hs}
    d = Path(tempfile.mkdtemp())
    C1 = build(ft, hero, by.get, Selection(games=("PLO6",)), use_db=False, data_sig="sigA", cache_dir=d, as_context=True)
    assert C1.get("quick_info") is None
    st = _model_sig_get(d, f"{Selection(games=('PLO6',)).key()}|{hero}")
    assert st and st["sig"] == "sigA" and st["n"] == ft.n
    C2 = build(ft, hero, by.get, Selection(games=("PLO6",)), use_db=False, data_sig="sigB", cache_dir=d, as_context=True, quick=True)
    assert C2["quick_info"] and C2["quick_info"]["since"] == 0 and C2["quick_info"]["max"] == QUICK_MAX
    assert _model_sig_get(d, f"{Selection(games=('PLO6',)).key()}|{hero}")["sig"] == "sigA"  # snabb uppdatering ändrar inte
    C3 = build(ft, hero, by.get, Selection(games=("PLO6",)), use_db=False, data_sig="sigC", cache_dir=d, as_context=True)
    assert C3.get("quick_info") is None and _model_sig_get(d, f"{Selection(games=('PLO6',)).key()}|{hero}")["sig"] == "sigC"


def test_session_zip_job():
    """2.66: zip för valda sessioner – bara sessionens händer, med sessionsfil och handhistorik."""
    import io
    import tempfile
    import zipfile
    from pathlib import Path
    import plo_leak.web as W
    from plo_leak.facts import extract
    from plo_leak.pipeline import build
    from plo_leak.selection import Selection
    hs, hero = _real_hands()
    ft = extract(hs, hero)
    by = {h.id: h for h in hs}
    C = build(ft, hero, by.get, Selection(games=("PLO6",)), use_db=False, as_context=True)
    key = C["sessions"]["sessions"][0]["key"]
    W.VIEWS["tst"] = {"C": C, "hero": hero}
    class J:
        def set(self, *a, **k): pass
    d = Path(tempfile.mkdtemp())
    old = W.get_db
    W.get_db = lambda: type("D", (), {"path": d / "x.db"})()
    try:
        url = W._deep_job(J(), {"vid": "tst", "keys": [key]})
    finally:
        W.get_db = old
    name = url.rsplit("/", 1)[1]
    z = zipfile.ZipFile(io.BytesIO((d / "x_export" / name).read_bytes()))
    names = z.namelist()
    assert "session.md" in names and "handhistorik.txt" in names and "hands.csv" in names
    n_hands = len(z.read("hands.csv").decode("utf-8").strip().splitlines()) - 1
    s0 = C["sessions"]["sessions"][0]
    assert 0 < n_hands <= ft.n and n_hands == s0["hands"]
    assert z.read("handhistorik.txt").decode("utf-8").count("Poker Hand #") == n_hands


def test_auto_update_on_new_hands(tmp_path, monkeypatch):
    """2.67: bevakningen kollar var 10:e sekund, och nya händer startar en snabb uppdatering i programmet."""
    from plo_leak import watch, web
    assert watch.INTERVAL <= 10 and watch.SETTLE <= 5
    started = []
    class FakeJob:
        id = "j1"; status = "väntar"; stage = ""
    class FakeMgr:
        run_lock = __import__("threading").Lock()
        def get(self, jid): return None
        def start(self, title, fn, spec):
            started.append(spec); return FakeJob()
    import plo_leak.jobs as jobs
    monkeypatch.setattr(jobs, "MANAGER", FakeMgr())
    class FakeDB:
        path = tmp_path / "x.db"
    monkeypatch.setattr(web, "get_db", lambda: FakeDB())
    monkeypatch.setattr(web, "_last_vid", lambda: "abc")
    web._AUTO["job"] = None; web._AUTO["started"] = 0.0
    watch.save_settings(FakeDB(), last_spec={"stake": "1/2", "back": "sessioner", "folder": "/hemlig"})
    web._auto_update()
    assert started and started[0]["quick"] and started[0]["stake"] == "1/2" and started[0]["folder"] == ""
    watch.save_settings(FakeDB(), auto_update=False)
    started.clear(); web._AUTO["job"] = None; web._AUTO["started"] = 0.0
    web._auto_update()
    assert not started


def test_v268_cold_call_note_and_stop_rule():
    from plo_leak.cards import parse_cards
    from plo_leak.guidelines import preflop_note
    weak = parse_cards("6s 6h 7s 7h Jd Tc")      # dubbelpar, 0 nöt-egenskaper
    good = parse_cards("As Ks Kh Qh Jd Tc")      # suited ess + högt par
    # 2.70: riktlinjen om kall syn mot 3-bet är borttagen (inte säker)
    assert preflop_note("kall_mot_3bet", "call", parse_cards("Ks Qh Jd 9c 8s 3h"), 100, "BTN", "1/2") == ""
    assert preflop_note("rfi", "raise", weak, 100, "CO") == ""  # 2.77: ersatt av solvern
    assert preflop_note("rfi", "raise", parse_cards("6s 6h 7s 7h Jd Tc").__class__([*parse_cards("6s 6h 7s 7d Ks Td")]), 100, "CO") == ""  # ds + suited kung
    assert preflop_note("mot_hojning", "call", parse_cards("As Ah Kd 9c 8s 3h"), 100, "BTN") == ""  # 2.77: aa_ip_3bet dold (solvern)
    import numpy as np
    from plo_leak import fatigue
    # liten konstgjord session: 300 händer, −1 bb per hand → gränsen −150 bb nås vid hand 151
    class FT: pass
    ft = FT(); n = 300
    ft.n = n
    ft.H = {"ts": np.arange(n) * 20, "net": -np.ones(n), "ev": -np.ones(n) * 0.5, "vpip": np.r_[np.zeros(150), np.ones(150)],
            "pos": np.zeros(n, int), "nplay": np.full(n, 5), "stake": np.zeros(n, int), "ttype": np.zeros(n, int)}
    class ST: pass
    st = ST(); st.ft = ft; st.rows = np.arange(n); st.decisions = None
    S = fatigue.session_stop(st, {}, 0, int(ft.H["ts"][-1]), stop_bb=150.0)  # 2.72: standard −500, här prövas mekaniken
    assert not S["kept"] and S["why"].startswith("−150") and S["after"]["hands"] == 150 and S["before"]["vpip"] == 0
    assert S["after"]["vpip"] == 100


def test_v270_notes_verified_only_and_night():
    from plo_leak.guidelines import GUIDELINES, PRIO, postflop_note, visible
    assert len(PRIO) == 7 and PRIO[0][1].startswith("Syna mindre") and visible("set_cr") and not visible("cbet_size") and not visible("pf_river_cr_paired")
    assert all(("verified" in g) == bool(g.get("verified")) for g in GUIDELINES)
    base = {"players": 2, "ip": 0, "pfa": 0, "hand": "triss", "flush_draw": "", "straight_outs": 0, "facing_allin": 0}
    assert "#13" in postflop_note({**base, "street": "flop", "facing": "bet", "action": "call", "order": 2, "set_rank": "mellan",
                                   "board_type": "regnbåge"})
    assert postflop_note({**base, "street": "flop", "facing": "bet", "action": "call", "order": 2, "set_rank": "botten",
                          "board_type": "högt torrt"}) == ""
    assert "#14" not in postflop_note({**base, "hand": "par", "pfa": 1, "street": "flop", "facing": "ingen", "action": "bet",  # 2.77 nedgraderad
                                   "size_pct": 50, "flush_draw": "nöt"})
    # #12 är inte verifierad → ingen not
    assert postflop_note({**base, "hand": "kåk", "ip": 1, "street": "river", "facing": "raise", "action": "call",
                          "board_paired": 1, "made_frac": 0.06}) == ""
    from plo_leak.night import outs, top_two
    hole = [(14, 's'), (13, 's'), (12, 'h'), (11, 'd'), (9, 'c'), (2, 'h')]
    n1, n2, npair = outs(hole, [(10, 's'), (8, 's'), (3, 'd')])
    assert npair == 9 and n1 >= 8
    from plo_leak.postflop_rows import board_type, set_rank
    assert board_type([(14, 's'), (11, 'd'), (4, 'c')]) == "högt torrt"
    assert board_type([(3, 's'), (5, 'd'), (6, 'c')]) == "lågt sammanhängande"
    assert set_rank([(9, 's'), (9, 'd'), (2, 'c'), (3, 'h'), (4, 'h'), (5, 'c')], [(13, 'h'), (9, 'c'), (4, 'd')]) == "mellan"
