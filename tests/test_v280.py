"""2.80: rättningar efter den oberoende granskningen av 2.79.1 (19 nov 2026)."""
from datetime import datetime
from pathlib import Path

from plo_leak.cards import parse_cards as P
from plo_leak.parser import Action, Hand

HERE = Path(__file__).parent


def _river_hand(resp):
    h = Hand("rb" + resp, "PLO-6", .5, 1, datetime(2026, 11, 20), seats={"V": 1, "H": 2},
             stacks={"V": 100, "H": 100}, positions={"V": "BB", "H": "BTN"},
             hole={"H": P("2c 3d 4h 5s 7c 8d")}, board=P("Ks Qh 9d 2s Jh"))
    h.actions = [Action("preflop", "H", "raise", 3, 3), Action("preflop", "V", "call", 2, 3),
                 Action("flop", "V", "check"), Action("flop", "H", "check"),
                 Action("turn", "V", "check"), Action("turn", "H", "check"),
                 Action("river", "V", "check"), Action("river", "H", "bet", 4.5, 4.5),
                 Action("river", "V", resp, 4.5 if resp == "call" else 0, 4.5 if resp == "call" else 0)]
    return h


def test_river_fold_keeps_the_spot():
    """Granskningen P1: en fold på river tog bort läget ur riverförsöket – foldprocenten blev systematiskt för låg."""
    from plo_leak.riverbluff import _eff_ok
    assert _eff_ok(_river_hand("call"), "H")
    assert _eff_ok(_river_hand("fold"), "H")


def _hh(name):
    return (HERE / "real" / "user_hand_4bet_pot.txt").read_text(encoding="utf-8")


def test_truncated_then_complete_import_gives_the_real_result(tmp_path):
    """Granskningen: OM108301143 avkortad före floppen sparades som −27 och låstes – rätt är −135."""
    from plo_leak.db import HandDB
    full = _hh("x")
    cut = full[:full.index("*** FLOP ***")]
    f = tmp_path / "h.txt"
    db = HandDB(tmp_path / "a.db")
    f.write_text(cut, encoding="utf-8")
    r = db.add_paths([f])
    assert r["hands_new"] == 0 and r.get("hands_incomplete") == 1
    f.write_text(full, encoding="utf-8")
    r = db.add_paths([f])
    assert r["hands_new"] == 1
    r = db.add_paths([f])
    assert r["hands_new"] == 0 and db.count() == 1
    h = db.get_hand("OM108301143")
    assert abs(h.net("Hero") - (-135.0)) < 1e-9 and "*** SUMMARY ***" in h.raw


def test_filtered_read_does_not_block_full_read(tmp_path):
    from plo_leak.db import HandDB
    f = tmp_path / "h.txt"
    f.write_text(_hh("x"), encoding="utf-8")
    db = HandDB(tmp_path / "b.db")
    assert db.add_paths([f], require_player="NågonAnnan")["hands_new"] == 0
    assert db.add_paths([f], require_player="NågonAnnan")["files_skipped"] == 1   # filtrerad läsning: läst
    assert db.add_paths([f])["hands_new"] == 1                                       # full läsning: läses om


def test_old_incomplete_rows_are_repaired(tmp_path):
    import sqlite3, zlib
    from plo_leak.db import HandDB
    full = _hh("x")
    f = tmp_path / "h.txt"
    f.write_text(full, encoding="utf-8")
    db = HandDB(tmp_path / "c.db")
    db.add_paths([f])
    cut = full[:full.index("*** FLOP ***")]
    db.con.execute("UPDATE hands SET raw=? WHERE id='OM108301143'", (zlib.compress(cut.encode()),))
    db.con.execute("DELETE FROM meta WHERE k='incomplete_v1'")
    db.con.commit()
    db2 = HandDB(tmp_path / "c.db")
    assert db2.repaired_incomplete == 1 and db2.count() == 0
    assert db2.add_paths([f])["hands_new"] == 1


def test_same_card_in_two_places_is_rejected():
    from plo_leak.parser import parse_hand
    full = _hh("x")
    bad = full.replace("1db8bc70: shows [4s Ad 5h Ks 5s As]", "1db8bc70: shows [4s Ad 5h Ks 5s Ah]")  # Ah har Hero
    assert parse_hand(full) is not None and parse_hand(bad) is None


def test_allin_ev_before_rake_uses_expected_fee():
    """Granskningen: OM105003672 – EV före rake ska vara 66,86667 (equity × pott utan avgift), inte samma som efter."""
    from plo_leak.parser import load_paths
    from plo_leak.stats import analyze
    h = {x.id: x for x in load_paths([HERE / "real" / "gg_plo6_samples.txt"])}["OM105003672"]
    st = analyze([h], "Hero")
    assert abs(st.ev_net_money - 65.40833) < 1e-3
    assert abs(st.ev_net_money + st.ev_rake_money - 66.86667) < 1e-3


def test_facing_size_not_shrunk_by_earlier_caller():
    """Granskningen: OM107644459 – bet 21 i pott 42 är 50 % även om en annan spelare synar före Hero."""
    from plo_leak.parser import load_paths
    from plo_leak.postflop_rows import HEADER, rows_for_hand
    h = {x.id: x for x in load_paths([HERE / "real" / "gg_plo6_samples.txt"])}["OM107644459"]
    rows = [dict(zip(HEADER, r)) for r in rows_for_hand(h, "Hero", 0.0, light=True)]
    r = next(x for x in rows if x["street"] == "flop" and x["facing"] == "bet")
    assert abs(r["facing_size_pct"] - 50.0) < 0.05 and abs(r["pot_at_decision_bb"] - 84.0) < 0.01


def test_inferred_fold_counts_in_table_state():
    """Granskningen: utan explicit knappfold ska Hero ändå vara två-vägs i position på floppen."""
    from plo_leak.parser import parse_hand
    from plo_leak.postflop_rows import HEADER, rows_for_hand
    full = _hh("x")
    a = parse_hand(full)
    b = parse_hand(full.replace("81c9823b: folds\n", ""))
    ra = [dict(zip(HEADER, r)) for r in rows_for_hand(a, "Hero", 0.0, light=True)]
    rb = [dict(zip(HEADER, r)) for r in rows_for_hand(b, "Hero", 0.0, light=True)]
    assert [(r["players"], r["ip"]) for r in ra] == [(r["players"], r["ip"]) for r in rb]


def test_nut_straight_is_never_called_low_straight():
    from types import SimpleNamespace
    from plo_leak import misstag
    from plo_leak.postflop_rows import HEADER
    idx = {k: HEADER.index(k) for k in HEADER}
    row = [""] * len(HEADER)
    row[idx["street"]], row[idx["action"]], row[idx["facing"]] = "river", "call", "bet"
    row[idx["hand"]], row[idx["board_paired"]], row[idx["beat_frac"]] = "stege", 0, 0.47
    nut = SimpleNamespace(hole={"Hero": P("Kd Ac 2c 3d 4h 5c")}, board=P("8s 9s Ts Jd Qh"), actions=[])
    assert misstag.postflop(nut, "Hero", [row], idx) == []
    low = SimpleNamespace(hole={"Hero": P("7d 6c 2c 3d 4h 5c")}, board=P("8s 9s Ts Jd Qh"), actions=[])
    m = misstag.postflop(low, "Hero", [row], idx)
    assert m and m[0]["kind"] == "granska"


def test_stake_choice_uses_dollars_per_hour():
    """Granskningen: +10 bb/100 på 0,25/0,50 (5 $/h) mot +5 bb/100 på 1/2 (10 $/h) – 1/2 får inte klassas som sämre."""
    import numpy as np
    from types import SimpleNamespace
    from plo_leak import stakecheck
    n = 20000
    rng = np.random.default_rng(3)
    stake = np.r_[np.zeros(n // 2, int), np.ones(n // 2, int)]
    bb = np.where(stake == 0, 0.5, 2.0)
    ev = np.where(stake == 0, 0.10, 0.05) + rng.normal(0, 0.01, n)
    ts = np.arange(n) * 36  # 100 händer per timme
    clu = np.arange(n) // 100
    H = {"stake": stake, "ev": ev, "bb": bb, "ts": ts, "clu": clu, "vpip": np.zeros(n, bool), "rake": np.zeros(n)}
    ft = SimpleNamespace(H=H, n=n, label=lambda col, c: ["0.25/0.5", "1/2"][c])
    st = SimpleNamespace(ft=ft, rows=np.arange(n))
    import plo_leak.fatigue as fat
    orig = fat.hand_session_info
    fat.hand_session_info = lambda st: (np.arange(n), clu, None)
    try:
        S = stakecheck.stake_check(st)
    finally:
        fat.hand_session_info = orig
    assert S["best"]["stake"] == "1/2" and [x["stake"] for x in S["worse"]] == ["0.25/0.5"]
    assert abs(S["best"]["usd_h"] - 10.0) < 0.1


def test_night2_no_final_verdict_before_full_coverage():
    """Granskningen: en avbruten nattkö fick låsa 'inte avgjord' permanent."""
    import sys
    sys.path.insert(0, str(HERE))
    from test_v273 import _acc_world
    N, db, st = _acc_world(20, bias_v2=-0.4, luck_mean=1.0, luck_noise=10.0)
    db.con.execute("DELETE FROM night2_hand WHERE rowid % 2 = 0")
    r = N.acceptance(db, st)
    assert r["status"] == "väntar" and r["coverage"][0] < r["coverage"][1]
    assert N.meta_get(db.con, "acceptance_final") is None


def test_two_different_orders_get_two_jobs():
    import threading
    from plo_leak.jobs import JobManager
    from plo_leak.web import _job_key
    m = JobManager()
    gate = threading.Event()
    a = m.start("A", lambda j: gate.wait(5), key=_job_key("djup", "v1", ["s1"]))
    b = m.start("B", lambda j: gate.wait(5), key=_job_key("djup", "v1", ["s2"]))
    c = m.start("C", lambda j: gate.wait(5), key=_job_key("djup", "v1", ["s1"]))
    gate.set()
    assert a.id != b.id and c.id == a.id


def test_api_gg_reports_status(monkeypatch):
    from plo_leak import night, web
    monkeypatch.setattr(night, "gg_status", lambda: "ja")
    assert web.app.test_client().get("/api/gg").get_json() == {"gg": "ja"}


def test_hourly_interval_includes_pace_variation():
    """Granskningen: 20 pass, 1 $ EV per hand, hälften 10 s och hälften 100 s mellan händerna – intervallet får inte vara noll."""
    import numpy as np
    from plo_leak.hourly import _block
    ts, clu = [], []
    t = 0
    for k in range(20):
        gap = 10 if k % 2 else 100
        for i in range(50):
            ts.append(t); clu.append(k); t += gap
        t += 7200
    n = len(ts)
    H = {"ts": np.array(ts), "clu": np.array(clu), "money": np.ones(n), "ev_m": np.ones(n), "rake_m": np.zeros(n),
         "net": np.ones(n), "ev": np.ones(n), "rake": np.zeros(n), "bb": np.ones(n)}
    b = _block(H, np.arange(n))
    assert b["ev_hi"] - b["ev_lo"] > 10


def test_post_without_origin_is_rejected(monkeypatch):
    """2.81: formulär utan Origin/Referer avvisas (granskningen: CSRF lokalt)."""
    from plo_leak import web
    monkeypatch.setenv("PLO_ALLOW_NO_ORIGIN", "0")
    c = web.app.test_client()
    assert c.post("/sessgrans", data={}).status_code == 403
    assert c.post("/sessgrans", data={}, headers={"Origin": "http://evil.example"}).status_code == 403


def test_removed_solver_stays_removed(monkeypatch, tmp_path):
    import json, sys
    sys.path.insert(0, str(HERE))
    from types import SimpleNamespace
    from test_v276 import _fake_raw
    from plo_leak import solverref
    src = tmp_path / "privat.json"
    src.write_text(json.dumps(_fake_raw()), encoding="utf-8")
    monkeypatch.setattr(solverref, "BUNDLED", src)
    db = SimpleNamespace(path=tmp_path / "hander.db")
    solverref._CACHE.clear()
    assert solverref.load(db)[0] is not None
    solverref.remove(db)
    solverref._CACHE.clear()
    assert solverref.load(db) == (None, None)
    solverref._CACHE.clear()
    assert solverref.load(db) == (None, None)
