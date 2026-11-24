"""2.75: träningsreglage med winrate-kurva, positionsläckor, egen kö för natten, nya framåthypoteser, rundown-text."""
import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_v272 import _st  # noqa: E402


# ---------------------------------------------------------------- reglaget
def test_slider_answer_follows_cut():
    from plo_leak.practice import trainer_hand
    for seed in range(40):
        h = trainer_hand(None, "BTN", seed=seed, spot="pct", cut=30)
        assert h["mode"] == "pct" and h["answer"] == ("open" if h["pct"] <= 30 else "fold")
    assert trainer_hand(None, "CO", seed=1, spot="pct", cut=0)["answer"] == "fold"
    assert trainer_hand(None, "CO", seed=1, spot="pct", cut=100)["answer"] == "open"
    assert trainer_hand(None, "BB", spot="pct", cut=30) is None  # BB öppnar aldrig


def test_slider_rules_are_info_only():
    """Regler ändrar inte facit i reglagets läge – de visas som extra information."""
    from plo_leak.practice import trainer_hand
    doc = {"variant": "PLO6", "rules": [
        {"id": "nut|utanför blindarna|0", "type": "nut", "pos": "utanför blindarna", "positions": ["HJ", "CO", "BTN"],
         "nut": "0 nöt-egenskaper", "cost": -1.0, "title": "folda 0 nöt", "why": "x", "level": "trolig"}]}
    seen = False
    for seed in range(200):
        h = trainer_hand(doc, "BTN", seed=seed, spot="pct", cut=100)
        assert h["answer"] == "open" and h["reasons"] == []
        seen = seen or bool(h["rule_notes"])
    assert seen


def test_winrate_curve_peak_and_selection_guard():
    from plo_leak.ranges import _winrate_curve
    rng = np.random.default_rng(1)
    n = 20000
    pct = rng.random(n)
    played = pct < 0.6
    # sant värde: +1 bb för topp 30 %, −0,5 bb därefter
    delta = np.where(pct < 0.3, 1.0, -0.5) + rng.normal(0, 3, n)
    c = _winrate_curve(pct, played, delta, 100000)
    assert 25 <= c["peak_pct"] <= 35
    assert c["max_pct"] == 60  # inga data över din spelade range
    # band där du bara spelat ett urval räknas inte som topp
    played2 = (pct < 0.3) | ((pct < 0.9) & (rng.random(n) < 0.2))
    delta2 = np.where(pct < 0.3, 1.0, 2.0)  # de få valda händerna ser bra ut – urvalseffekt
    c2 = _winrate_curve(pct, played2, delta2, 100000)
    assert c2["peak_pct"] <= 30
    assert not any(p[3] for p in c2["points"] if p[0] > 35)


def test_slider_winrate_lookup():
    from plo_leak.practice import slider_winrate
    curve = {"points": [[0, 0.0, 0.0, True], [1, 1.0, 0.5, True], [2, 1.5, 0.7, False]], "peak_pct": 1, "peak_bb100": 1.0,
             "peak_ci": 0.5, "max_pct": 2, "solid_max_pct": 1, "plateau": [1, 1], "now_bb100": 0.8, "now_pct": 2.0,
             "share_of_hands": 0.2}
    doc = {"rules": [], "wr_curves": {"BTN": curve}}
    w = slider_winrate(doc, "BTN", 1)
    assert w["bb100"] == 1.0 and w["bb100_total"] == 0.2 and w["solid"]
    assert slider_winrate(doc, "BTN", 50)["no_data"]
    assert slider_winrate(doc, "CO", 10) is None


# ---------------------------------------------------------------- positionsläckor
def test_position_leaks_sums():
    from plo_leak.positionleaks import position_leaks
    st = _st()
    r = position_leaks(st)
    assert r and r["positions"]
    for p in r["positions"]:
        for g in p["largest"]:
            assert g["total"] < 0 and g["n"] >= r["min_n"]
            assert abs(g["bb100_total"] - 100 * g["total"] / r["hands"]) < 1e-9
            assert g["lo"] <= g["mean"] <= g["hi"]
            assert g["sure_minus"] == (g["hi"] < 0)
        assert all(g["sure_minus"] for g in p["sure"])


def test_ranges_store_curve_and_weights():
    from plo_leak.ranges import analyze_ranges
    st = _st()
    rs = analyze_ranges(st.decisions)
    rfi = [r for r in rs if r["spot"] == "rfi"]
    assert rfi and all("wr_curve" in r for r in rfi)
    from plo_leak import practice
    hw = next(iter(rs))["weights"]
    w = practice.hand_weights({"hand_weights": list(hw.values()), "rules": []})
    assert len(w) == 12
    assert practice.hand_weights(None) == practice.DEFAULT_HAND_WEIGHTS


# ---------------------------------------------------------------- egen kö för natten
def test_night_lane_does_not_block_main():
    import threading
    import time
    from plo_leak.jobs import JobManager
    m = JobManager()
    gate = threading.Event()
    night = m.start("Nattberäkning", lambda j: gate.wait(5), key="natt", lane="natt")
    time.sleep(0.05)
    a = m.start("Analys", lambda j: "ok")
    t0 = time.time()
    while a.status != "klar" and time.time() - t0 < 3:
        time.sleep(0.01)
    assert a.status == "klar" and night.status == "kör"  # analysen väntade inte på natten
    # två jobb i huvudkön körs fortfarande ett i taget
    g2 = threading.Event()
    b = m.start("Analys", lambda j: g2.wait(5))
    time.sleep(0.05)
    c = m.start("Export", lambda j: "ok")
    time.sleep(0.1)
    assert c.status == "väntar"
    g2.set(); gate.set()
    t0 = time.time()
    while (c.status != "klar" or night.status != "klar") and time.time() - t0 < 3:
        time.sleep(0.01)
    assert c.status == "klar" and night.status == "klar" and b.status == "klar"


def test_two_connections_same_db(tmp_path):
    """Nattkön har en egen anslutning: den skriver medan huvudanslutningen läser och skriver."""
    import threading
    from plo_leak.db import HandDB
    a = HandDB(tmp_path / "x.db")
    b = HandDB(tmp_path / "x.db")
    b.con.execute("CREATE TABLE IF NOT EXISTS t (k INTEGER PRIMARY KEY, v TEXT)")
    b.con.commit()
    err = []

    def writer():
        try:
            for i in range(300):
                b.con.execute("INSERT OR REPLACE INTO t VALUES (?, ?)", (i, "x" * 50))
                if i % 20 == 0:
                    b.con.commit()
            b.con.commit()
        except Exception as e:  # pragma: no cover
            err.append(e)
    th = threading.Thread(target=writer)
    th.start()
    for _ in range(50):
        a.con.execute("SELECT COUNT(*) FROM hands").fetchone()
        a.con.execute("SELECT COUNT(*) FROM t").fetchone()
    a.con.execute("CREATE TABLE IF NOT EXISTS u (k INTEGER)")
    a.con.execute("INSERT INTO u VALUES (1)")
    a.con.commit()
    th.join()
    assert not err
    assert a.con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 300


def test_run_night_holds_prep_lock_only_for_prep(monkeypatch, tmp_path):
    import threading
    from plo_leak import night, night2, nightly
    from plo_leak.db import HandDB
    lock = threading.Lock()
    seen = {}
    monkeypatch.setattr(night, "blocked", lambda db: "")
    monkeypatch.setattr(nightly, "backup", lambda db: (seen.setdefault("backup", lock.locked()), "b")[1])
    monkeypatch.setattr(nightly, "_main_st", lambda db, hero: (seen.setdefault("fakta", lock.locked()), (_st(), None))[1])
    monkeypatch.setattr(nightly, "ts_map", lambda ft, rows: None)
    monkeypatch.setattr(night2, "run", lambda *a, **k: (seen.setdefault("calc", lock.locked()), "klar")[1])
    monkeypatch.setattr(night2, "acceptance", lambda *a, **k: {"status": "x", "text": "", "parts": {}})
    monkeypatch.setattr(nightly, "morning_report", lambda *a, **k: "")
    monkeypatch.setattr(nightly, "receipts_dir", lambda db: tmp_path)
    monkeypatch.setattr(nightly, "reports_dir", lambda db: tmp_path)
    nightly.run_night(None, 1, lambda m: None, db=HandDB(tmp_path / "n.db"), prep_lock=lock)
    assert seen == {"backup": True, "fakta": True, "calc": False}


# ---------------------------------------------------------------- nya hypoteser
def test_hypotheses_only_after_date(monkeypatch):
    from plo_leak import hypotheses as hy
    st = _st()
    monkeypatch.setattr(hy, "hyp_ts", lambda: 2 ** 62)  # inga händer efter datumet
    r = hy.hypotheses_test(st)
    assert r["hands_after"] == 0 and all(x["n"] == 0 and x["verdict"] == "för få" for x in r["rules"])
    monkeypatch.setattr(hy, "hyp_ts", lambda: -(2 ** 62))  # alla händer räknas
    r = hy.hypotheses_test(st)
    assert [x["id"] for x in r["rules"]] == ["H1", "H2", "H3"] and r["hash"] == hy.HYP_HASH
    assert sum(x["n"] for x in r["rules"]) > 0
    assert "compare" in r["rules"][2]


def test_hypotheses_frozen_and_separate():
    """Fingeravtrycket är låst – och hypoteserna rör inte de frysta reglerna eller postflop-specarna."""
    from plo_leak import hypotheses as hy, pfforward
    from plo_leak.practice import DEFAULT_HAND_WEIGHTS
    assert hy.HYP_HASH == hy.hyp_hash() == "e4e93fbb9face71d"
    assert hy.HAND_WEIGHTS == DEFAULT_HAND_WEIGHTS
    assert pfforward.SPECS_FROZEN_HASH == "eee8fd8d3da53304"
    pct = hy.hand_pct(np.zeros((1, 12), np.int8))
    assert 0 <= pct[0] <= 100
