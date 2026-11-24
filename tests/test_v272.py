"""2.72: nattberäkning v2, betstorlek, river-bluff-testet, framåttest postflop, stoppregel, vila/morgon, drift."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from plo_leak.cards import parse_cards as P

HERE = Path(__file__).parent


def _sample(n=6000, seed=3):
    import sys
    sys.path.insert(0, str(HERE.parent / "tools"))
    from generate_sample import Table
    from plo_leak.parser import parse_text
    t = Table(seed)
    return parse_text("\n\n\n".join(t.play() for _ in range(n)))


_CACHE = {}


def _st():
    if "st" not in _CACHE:
        from plo_leak.aggregate import build_stats
        from plo_leak.facts import extract
        hs = _sample()
        ft = extract(hs, "Hero")
        _CACHE["st"] = build_stats(ft, np.ones(ft.n, bool), "Hero", {h.id: h for h in hs}.get)
        _CACHE["hands"] = hs
    return _CACHE["st"]


# ---------------------------------------------------------------- vila, morgon, fyrfärg
def test_rest_and_morning_tags():
    from plo_leak.facts import ts_of
    from plo_leak.sessions import rest_info
    t = ts_of(datetime(2026, 11, 14, 8, 30))
    a = rest_info(t, 10.0)
    assert a["morning"] and a["rested"] and "🌅 morgonpass" in a["rest_tags"] and "10,0 h" in a["gap_txt"]
    b = rest_info(ts_of(datetime(2026, 11, 14, 22, 0)), 3.0)
    assert not b["morning"] and b["rested"] is False and "⚠ kort vila" in b["rest_tags"]
    assert rest_info(t, None)["rested"] is None


def test_sessions_carry_rest_info():
    T = __import__("plo_leak.sessions", fromlist=["session_table"]).session_table(_st(), None)
    S = T["sessions"]
    assert all("gap_txt" in s and "rested" in s for s in S)
    assert S[-1]["gap_h"] is None and all(s["gap_h"] > 0.5 for s in S[:-1])  # ny session = paus > 30 min


def test_four_colour_cards_in_session_file():
    from plo_leak.sessionfile import _cards
    assert _cards(P("Kd Qs Jc 4c 4s 2h")) == "K🔷 Q♠️ J☘️ 4☘️ 4♠️ 2♥️"


# ---------------------------------------------------------------- regler och texter
def test_prio_and_stop_rule_texts():
    from plo_leak.fatigue import BIG_LOSS_BB, STOP_BB, STOP_H
    from plo_leak.guidelines import GUIDELINES, PRIO
    assert STOP_BB == 500 and STOP_H == 2 and BIG_LOSS_BB == 175
    txt = " ".join(t + d for _i, t, d in PRIO)
    assert "−500 bb" in txt and "175 bb" in txt and "2 h" in txt and "¾ pott" in txt  # 2.87: en tidsregel (2 h)
    assert "13+" not in txt and "jamma" not in txt  # 13+-jam är struken
    g11 = next(g for g in GUIDELINES if g["id"] == "pf_river_bigbet_call")
    assert g11["preregistered"]["kåk_slår_dig_över"] == 0.16


def test_pause_after_big_loss():
    from plo_leak.fatigue import _pause_check
    H = {"net": np.array([-200.0, 1.0, -180.0, 2.0, 3.0])}
    ts = np.array([0, 1000, 1100, 1120, 1600])  # 2.86: paus 15 min – första förlusten: 1000 s paus, andra: 20 s
    r = _pause_check(H, np.arange(5), ts)
    assert r == {"big_losses": 2, "pauses_taken": 1}


def test_hypothesis_notes():
    from plo_leak.guidelines import preflop_note
    rd = P("9s 8d 7h 6c 3s 2d")          # rundown utan suited ess
    assert "rundown utan suited ess" in preflop_note("mot_hojning", "raise", rd, 100)
    assert preflop_note("mot_hojning", "call", rd, 100) == ""
    low = P("9s 9d 8h 7c 6s 2d")         # lägre par utan suited ess (rundown → inte "0 nöt-egenskaper")
    assert "lägre par" in preflop_note("mot_4bet", "call", low, 100)
    assert preflop_note("mot_4bet", "call", P("Qs Qd Kh 9c 5s 2d"), 100) == ""          # QQ+
    assert preflop_note("mot_4bet", "call", P("9s 9d As 5s 7h 2c"), 100) == ""          # suited ess


def test_threebet_rule_says_call_with_rundowns():
    import inspect
    from plo_leak import threebet
    assert "rundowns: syna i stället" in inspect.getsource(threebet.threebet_rules)


# ---------------------------------------------------------------- framåttest postflop
def test_pf_forward_evaluate():
    from plo_leak.pfforward import SPECS, evaluate
    rng = np.random.default_rng(1)
    rows, cl = [], []
    for i in range(2000):
        bet = rng.random() < 0.5
        rows.append({"street": "flop", "facing": "ingen", "pfa": 1, "players": 2, "ip": 1,
                     "action": "bet" if bet else "check", "from_here_pot": (0.3 if bet else 0.0) + rng.normal(0, 0.5)})
        cl.append(i // 40)
    res = {r["nr"]: r for r in evaluate(rows, cl)}
    assert res["#6"]["n"] == 2000 and res["#6"]["verdict"] == "håller framåt" and abs(res["#6"]["diff"] - 0.3) < 0.1
    assert res["#1"]["n"] == 0 and res["#1"]["verdict"] == "för få"
    for r in rows:
        r["from_here_pot"] = rng.normal(0, 0.5)
    assert {r["nr"]: r for r in evaluate(rows, cl)}["#6"]["verdict"] in ("osäkert", "för få")
    assert len(SPECS) == 11 and not any(s[0] == "#10" for s in SPECS)


def test_pf_forward_on_sample_hands():
    from plo_leak.pfforward import forward_postflop
    st = _st()
    F = forward_postflop(st, "Hero", freeze_ts=int(np.median(st.ft.H["ts"])))
    assert F["hands"] < st.ft.n and F["decisions"] > 100 and len(F["rules"]) == 11


# ---------------------------------------------------------------- river-bluff-testet
def _fake_bluff_ft(n, fold_p, bet_p, seed=0):
    rng = np.random.default_rng(seed)
    bet = rng.random(n) < bet_p
    vocab = {"bet": 0, "check": 1}
    Pf = {"hidx": np.arange(n), "st": np.full(n, 3, np.int8), "np": np.full(n, 2, np.int8), "ip": np.ones(n, bool),
          "facing": np.zeros(n, np.int8), "ord": np.ones(n, np.int8), "bf": np.full(n, 0.9),
          "kind": np.where(bet, 0, 1).astype(np.int16), "size": np.where(bet, 100.0, np.nan),
          "fh": np.where(bet, np.where(rng.random(n) < fold_p, 10.0, -10.0), 0.0), "pot": np.full(n, 10.0)}
    resp = np.where(rng.random(n) < fold_p, 0, 1).astype(np.int8)
    V = {"hidx": np.arange(n)[bet], "role": np.ones(int(bet.sum()), np.int8), "resp": resp[bet]}
    H = {"ts": np.full(n, 1_900_000_000), "clu": np.arange(n) // 10}
    ft = SimpleNamespace(n=n, H=H, t={"pfd": Pf, "rvb": V}, codes=lambda v: vocab,
                         subset_mask=lambda mask, name: mask[{"pfd": Pf, "rvb": V}[name]["hidx"]])
    return SimpleNamespace(ft=ft, rows=np.arange(n))


def test_river_bluff_test_verdicts():
    from plo_leak.riverbluff import bluff_test
    good = bluff_test(_fake_bluff_ft(600, 0.72, 0.5))
    assert good["spots"] == 600 and "klart" in good["verdict"] and 40 < good["bet_share"] < 60
    assert 65 < good["fold_pct"] < 80 and good["pot_bets"] == good["bets"]
    bad = bluff_test(_fake_bluff_ft(320, 0.50, 0.5, 1))
    assert "Avbryt" in bad["verdict"]
    skew = bluff_test(_fake_bluff_ft(120, 0.72, 0.9, 2))
    assert "slumpregeln" in skew["verdict"]
    assert bluff_test(_fake_bluff_ft(50, 0.7, 0.5), since_ts=2_000_000_000)["spots"] == 0


# ---------------------------------------------------------------- betstorlek
def test_bet_events_sizes_and_responses():
    from plo_leak.betsize import bet_events, size_code
    from plo_leak.parser import load_paths
    h = {x.id: x for x in load_paths([HERE / "real" / "gg_plo6_samples.txt"])}["OM89894742"]
    ev = bet_events(h, "Hero")
    river = [e for e in ev if e[0] == 3][0]
    assert river[1] == 1 and river[5] == 0  # du bettade river, motståndaren foldade
    assert abs(river[2] - 64.5 / 72) < 1e-6  # effektiv storlek (han hade bara 64,5 bb kvar)
    assert [size_code(x) for x in (0.3, 0.5, 0.7, 1.0, 1.5)] == [0, 1, 2, 3, 4]


def test_betsize_report_on_sample():
    from plo_leak.betsize import betsize_report
    st = _st()
    assert len(st.ft.t["bsz"]["hidx"]) > 1000
    B = betsize_report(st)
    assert B["table"] and B["dist"] and B["matrix"]
    for r in B["table"]:
        if r.get("be") is not None:
            assert 0 < r["be"] < 60  # break-even under 60 % även för överbet med rake
    for d in B["dist"]:
        if d["n_hero"]:
            assert abs(sum(d["hero"]) - 100) < 1e-6
    assert 0 <= B["ext_hero"] <= 100


def test_break_even_with_rake():
    b, r = 1.0, 0.05
    assert abs(b / (b + 1 - r) - 0.5128) < 1e-3  # pottstor bluff: ~51 % fold före showdown-värde


# ---------------------------------------------------------------- nattberäkning v2
def test_night2_bands_and_lookup():
    from plo_leak import night2 as N
    f = {"bet": 30, "check": 70}
    assert N.band(f, "bet", "none") == (0.0, 0.3, True) and N.band(f, "check", "none") == (0.3, 1.0, False)
    g = {"fold": 50, "call": 40, "raise": 10}
    lo, hi, aggr = N.band(g, "call", 2)
    assert abs(lo - 0.1) < 1e-9 and abs(hi - 0.5) < 1e-9 and not aggr
    assert N.band(g, "fold", 2) is None
    lines = {"1|none|1|0.5/1": {"bet": 10, "check": 10}, "1|none|1|*": {"bet": 400, "check": 600}}
    freq, lvl = N.lookup(lines, 1, "none", 1, "0.5/1")
    assert lvl == 1 and freq["bet"] == 400  # för tunt per nivå – ihopslaget


def test_night2_equity_converges_and_is_a_martingale():
    from plo_leak import night2 as N
    hole, flop = P("As Ks Qd Jd Th 9h"), P("Ts 8s 2d")
    r = N.eq_range(hole, flop, [], 0.2, seed=5)
    assert r[1] <= N.SE_TARGET + 1e-9 and 0.6 < r[0] < 0.9
    nuts = N.eq_range(P("As Ks Qs Js 2h 3h"), P("Ts 9s 8s 4d 4c"), [], 0.0, seed=1)
    assert nuts[0] > 0.97  # färgstege med ess-hög på river
    # förväntad equity efter turnkortet = equity före (samma motståndarhänder)
    hist = [(flop, (0.0, 0.3, True))]
    before = N.eq_range(hole, flop, hist, 0.0, seed=2)[0]
    deck = [(r_, s) for r_ in range(2, 15) for s in "cdhs" if (r_, s) not in hole + flop]
    afters = [N.eq_range(hole, flop + [c], hist, 0.0, seed=3)[0] for c in deck[::3]]
    assert abs(np.mean(afters) - before) < 0.04


def test_night2_walk_and_hand_calc():
    from plo_leak import night2 as N
    from plo_leak.parser import detect_hero, load_paths
    hs = load_paths([HERE / "real"])
    hero = detect_hero(hs)
    lines = N.line_counts(hs, hero)
    assert lines and all(k.count("|") == 3 for k in lines)
    ev = N.walk(hs[0])
    assert all(e["fac"] == "none" or 0 <= e["fac"] <= 4 for e in ev)
    n_dec = n_luck = 0
    for h in hs[:30]:
        d, hr = N.hand_calc(h, hero, lines, 0.2)
        n_dec += len(d)
        assert all(0 <= x[3] <= 1 and x[4] >= 0 for x in d)
        if hr and hr["trans"]:
            n_luck += 1
    assert n_dec > 5 and n_luck >= 1


def test_night2_job_and_acceptance_wait(tmp_path):
    """Hela kedjan på en liten databas: körning (1 process), sparade rader och acceptanstestet säger 'väntar'."""
    from plo_leak import night2 as N
    from plo_leak.aggregate import build_stats
    from plo_leak.db import HandDB
    from plo_leak.nightly import ts_map
    import plo_leak.night as n1
    db = HandDB(tmp_path / "n.db")
    db.add_paths([HERE / "real" / "gg_plo6_samples.txt"])
    hero = db.detect_hero()
    store = db.facts(hero)
    store.sync(db, workers=1)
    ft = store.load()
    old = n1.blocked
    n1.blocked = lambda db: ""
    try:
        msg = N.run(SimpleNamespace(set=lambda *a, **k: None), db, 1, ts_of=ts_map(ft))
    finally:
        n1.blocked = old
    assert "klar" in msg or "beräknat" in msg, msg
    assert N.status(db)["done"] == db.count()
    st = build_stats(ft, np.ones(ft.n, bool), hero, db.get_hand)
    A = N.acceptance(db, st, hero)
    assert A["status"] == "väntar" and "används inte" in A["text"]
    assert N.export_rows(db, [str(x) for x in ft.H["id"]])


# ---------------------------------------------------------------- drift
def test_nightly_backup_receipt_and_report(tmp_path):
    from plo_leak import nightly
    from plo_leak.aggregate import build_stats
    from plo_leak.db import HandDB
    db = HandDB(tmp_path / "b.db")
    db.add_paths([HERE / "real"])
    fp = nightly.fingerprint(db)
    assert fp["hands"] == db.count() and len(fp["hash"]) == 16
    for _ in range(2):
        b = nightly.backup(db, keep=1)
    assert Path(b).exists() and len(list(Path(b).parent.glob("plo_leak_*.db"))) == 1
    hero = db.detect_hero()
    store = db.facts(hero)
    store.sync(db, workers=1)
    ft = store.load()
    st = build_stats(ft, np.ones(ft.n, bool), hero, db.get_hand)
    txt = nightly.morning_report(db, st, hero, {"text": "⏳ test", "parts": {}}, "klar", {"db_after": fp, "backup": b})
    assert txt.startswith("# Morgonrapport") and "Prio-listan" in txt and len(txt) < 20000
    nightly._save_receipt(db, {"status": "klar", "start": "x"})
    assert nightly.last_receipt(db)["status"] == "klar"
    import sys
    if sys.platform not in ("win32", "darwin"):
        assert not nightly.schedule_status()["supported"] and "stöds bara" in nightly.install_schedule("03:30")
    try:
        nightly._hhmm("25:00")
        raise AssertionError
    except ValueError:
        pass
