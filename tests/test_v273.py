"""2.73: rättningar efter den externa granskningen av 2.72.2 – granskarens motexempel som negativa kontroller."""
import io
import json
import os
import pickle
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from tests.test_v272 import _fake_bluff_ft

HERE = Path(__file__).parent
ROOT = HERE.parent


# ---------------------------------------------------------------- F1: stora zip-filer
def test_big_zip_member_is_streamed_not_skipped(tmp_path):
    from plo_leak import parser
    from plo_leak.db import HandDB
    txt = (HERE / "real" / "gg_plo6_samples.txt").read_text(encoding="utf-8")
    n = len(parser.split_hands(txt))
    assert n > 20
    z = tmp_path / "stor.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("allt.txt", txt)
    old = parser.ZIP_STREAM_FROM, parser.ZIP_STREAM_PIECE, parser.ZIP_MEMBER_MAX
    parser.ZIP_STREAM_FROM, parser.ZIP_STREAM_PIECE, parser.ZIP_MEMBER_MAX = 5000, 20000, 6000  # "stor" fil i liten skala
    try:
        with zipfile.ZipFile(z) as zf:
            info = zf.infolist()[0]
            assert info.file_size > parser.ZIP_MEMBER_MAX  # skulle ha hoppats över tyst i 2.72.2
            parts = list(parser.zip_member_texts(zf, info))
        assert len(parts) > 3
        assert sum(len(parser.split_hands(t)) for t in parts) == n
        assert "".join(parts) == txt
        db = HandDB(tmp_path / "a.db")
        r = db.add_paths([z])
        assert r["hands_seen"] == n and r["hands_new"] == n and r["rejected"] == []
    finally:
        parser.ZIP_STREAM_FROM, parser.ZIP_STREAM_PIECE, parser.ZIP_MEMBER_MAX = old


def test_rejected_zip_member_is_reported_not_silent(tmp_path):
    from plo_leak import parser
    from plo_leak.db import HandDB
    txt = (HERE / "real" / "gg_plo6_samples.txt").read_text(encoding="utf-8")
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("h.txt", txt)
    z = tmp_path / "yttre.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("inre.zip", inner.getvalue())
    old = parser.ZIP_MEMBER_MAX
    parser.ZIP_MEMBER_MAX = 1000
    try:
        r = HandDB(tmp_path / "b.db").add_paths([z])
    finally:
        parser.ZIP_MEMBER_MAX = old
    assert r["hands_seen"] == 0
    assert len(r["rejected"]) == 1 and r["rejected"][0][1] == "inre.zip" and "packa upp" in r["rejected"][0][2]


# ---------------------------------------------------------------- F2: river-bluff-testet
def test_river_test_600_small_bets_without_checks_is_not_done():
    from plo_leak.riverbluff import bluff_test
    st = _fake_bluff_ft(600, 1.0, 1.0)
    st.ft.t["pfd"]["size"][:] = 10.0
    r = bluff_test(st)
    assert r["pot_bets"] == 0 and r["checks"] == 0 and r["small_bets"] == 600
    assert r["tone"] != "good" and "Testet är klart" not in r["verdict"]
    assert r["problems"] and r["known"] == 0  # små bets räknas inte i fold-andelen


def test_river_test_needs_both_arms_and_uses_effective_size():
    from plo_leak.riverbluff import bluff_test
    st = _fake_bluff_ft(600, 0.72, 0.5)
    P = st.ft.t["pfd"]
    P["esz"] = np.where(np.isnan(P["size"]), np.nan, 30.0)  # råstorlek pott, men motståndaren kunde bara syna 30 %
    r = bluff_test(st)
    assert r["pot_bets"] == 0 and r["tone"] != "good"
    ok = bluff_test(_fake_bluff_ft(600, 0.72, 0.5))
    assert ok["tone"] == "good" and ok["look"] == 2 and ok["diff_pot"] is not None and ok["clusters"] >= 20
    few = _fake_bluff_ft(600, 0.72, 0.5)
    few.ft.H["clu"] = np.arange(600) // 60   # bara 10 pass
    assert bluff_test(few)["tone"] != "good"


def test_river_test_shows_no_interim_fold_rate_and_has_safety_stop():
    from plo_leak.riverbluff import bluff_test
    mid = bluff_test(_fake_bluff_ft(200, 0.72, 0.5))
    assert mid["look"] == 0 and mid["fold_pct"] is None and "Pågår" in mid["verdict"]
    stop = bluff_test(_fake_bluff_ft(250, 0.25, 0.5, 3))
    assert "Avbryt" in stop["verdict"]  # hela intervallet under 51 % – säkerhetsstopp före första avläsningen


# ---------------------------------------------------------------- F3: #5
def test_draw_fold_vs_allin_is_review_marker_not_call_command():
    from plo_leak.guidelines import GUIDELINES, postflop_note
    note = postflop_note(dict(street="turn", action="fold", facing="bet", players=2, hand="högt kort", flush_draw="ja",
                              straight_outs=0, facing_allin=1, facing_pct=50, nut_outs=3))
    assert "#5" in note and "granska" in note and "3 nöt-outs" in note
    assert not note.rstrip().endswith("syna") and "inget facit" in note
    g = next(x for x in GUIDELINES if x["id"] == "pf_allin_draw_call")
    assert g["per100"] == 0.0  # ingen kostnad bokförs för en fold


# ---------------------------------------------------------------- F4: "bekräftad" bara från framåttestet
def test_focus_item_is_never_confirmed_without_forward_test():
    from plo_leak.pffocus import SPECS, focus_items
    f = focus_items(_fake_bluff_ft(600, 1.0, 0.0), 20000, 2)
    assert f and all(x["level"] != "bekräftad" for x in f)
    assert all(s["goal"] == s["target"] for s in SPECS)


def test_rule_level_follows_forward_verdict_and_frozen_definition():
    from plo_leak.report import _forward_levels
    r1 = {"id": "a", "type": "nut", "nut": "0 nöt-egenskaper", "pos": "BB", "positions": ["BB"], "level": "bekräftad"}
    r2 = {"id": "b", "type": "cutoff", "spot": "rfi", "pos": "HJ", "thr": 1.0, "weights": [1], "level": "bekräftad"}
    frozen = {"rules": [dict(r1), {**r2, "thr": 2.0}]}
    fwd = {"rules": [{"id": "a", "verdict": "håller"}, {"id": "b", "verdict": "håller"}]}
    out = {r["id"]: r for r in _forward_levels([r1, r2], fwd, frozen)}
    assert out["a"]["level"] == "bekräftad"
    assert out["b"]["level"] == "trolig" and out["b"]["forward_same_definition"] is False  # ändrad definition
    none = _forward_levels([r1, r2], None, None)
    assert all(r["level"] == "trolig" for r in none)
    wait = _forward_levels([r1], {"rules": [{"id": "a", "verdict": "för få"}]}, frozen)
    assert wait[0]["level"] == "trolig"


# ---------------------------------------------------------------- F5: tid
def test_freeze_limit_is_hand_time_in_every_timezone():
    code = ("from plo_leak.forward import freeze_ts; from plo_leak.riverbluff import start_ts; "
            "from plo_leak.night2 import freeze_ts as f2; print(freeze_ts(), start_ts(), f2())")
    outs = []
    for tz in ("UTC", "Europe/Stockholm", "America/Los_Angeles"):
        env = dict(os.environ, TZ=tz, PYTHONPATH=str(ROOT))
        outs.append(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(ROOT)).stdout.split())
    assert outs[0] == outs[1] == outs[2] and len(outs[0]) == 3
    from plo_leak.facts import ts_of
    from plo_leak.forward import freeze_ts
    assert freeze_ts() == ts_of(datetime(2026, 11, 13)) and int(outs[0][0]) == freeze_ts()
    assert ts_of(datetime(2026, 11, 12, 23, 30)) < freeze_ts() <= ts_of(datetime(2026, 11, 13, 0, 0))


def test_frozen_rules_hash_ignores_costs_but_not_definitions():
    from plo_leak.forward import rules_hash
    r = {"id": "a", "type": "cutoff", "spot": "rfi", "pos": "HJ", "thr": 1.0, "weights": [1, 2], "cost": -1.0, "title": "x"}
    h = rules_hash({"rules": [r]})
    assert h and h == rules_hash({"rules": [{**r, "cost": -9.0, "title": "annan text"}]})
    assert h != rules_hash({"rules": [{**r, "thr": 1.5}]})
    assert rules_hash({"rules": []}) is None


def test_postflop_specs_are_locked():
    from plo_leak import pfforward as p
    assert p.specs_hash() == p.SPECS_FROZEN_HASH


def test_pfforward_minimum_counts_only_decisions_with_known_outcome():
    from plo_leak import pfforward as p
    rows, clu = [], []
    for i in range(200):   # #6: c-bet HU som preflop-höjare
        bet = i % 2 == 0
        known = (i < 40) if not bet else True   # bara 20 checkar har känt utfall (under MIN_ARM = 30)
        rows.append({"street": "flop", "facing": "ingen", "pfa": 1, "players": 2, "action": "bet" if bet else "check",
                     "from_here_pot": (0.5 if bet else 0.1) if known else ""})
        clu.append(i % 40)
    r = next(x for x in p.evaluate(rows, clu) if x["nr"] == "#6")
    assert r["n"] == 200 and r["n_used"] == 120 and r["verdict"] == "för få"


# ---------------------------------------------------------------- F6: GG-vakten
def test_unknown_gg_status_blocks_night_run(monkeypatch):
    from plo_leak import night

    def boom(*a, **k):
        raise OSError("processlistan kunde inte läsas")
    monkeypatch.setattr(subprocess, "run", boom)
    assert night.gg_status() == "okänd" and night.gg_running() is False
    assert "inte att kontrollera" in night.blocked(SimpleNamespace())


# ---------------------------------------------------------------- acceptans v2
def _acc_world(n_clu_new, bias_v2, luck_mean, v1=0.0, actual=0.8, per=100, luck_noise=0.0, ev_sd=10.0):
    from plo_leak import night2 as N
    con = sqlite3.connect(":memory:")
    N.ensure_tables(con)
    N.meta_set(con, "lam", 0.2)
    cut = N.freeze_ts()
    n_old, n_new = 2000, n_clu_new * per
    n = n_old + n_new
    rng = np.random.default_rng(1)
    ts = np.concatenate([np.full(n_old, cut - 100), cut + 100 + np.arange(n_new)])
    clu = np.concatenate([np.repeat(np.arange(20), 100), 1000 + np.arange(n_new) // per])
    ev = rng.normal(0, ev_sd, n)
    H = dict(id=np.array([str(i) for i in range(n)]), ts=ts, ai_eq=np.full(n, actual), clu=clu, ev=ev,
             sb=np.full(n, 0.5), bb=np.ones(n))
    objs = []
    for i in range(n):
        fold = i % 2 == 0
        s = dict(kind="bet", response="fold" if fold else "call", frac=0.25 if fold else 1.0, role="ip",
                 bettor="Pool" if i < n_old else "Hero", hero_role=i >= n_old)
        objs.append(pickle.dumps(s))
        if i >= n_old:
            con.execute("INSERT INTO night2_ai VALUES (?,?,?)",
                        (str(i), json.dumps(dict(v1=v1, v2={"0.2": actual + bias_v2})), N.VERSION))
            luck = luck_mean + (0.9 * (ev[i] - ev[n_old:].mean()) if luck_noise == 0 else rng.normal(0, luck_noise))
            con.execute("INSERT INTO night2_hand VALUES (?,?,?,?,?)", (str(i), float(luck), 1, None, N.VERSION))
    ft = SimpleNamespace(H=H, t={"rsp": dict(hidx=np.arange(n), obj=objs)})
    return N, SimpleNamespace(con=con), SimpleNamespace(ft=ft, rows=np.arange(n))


def test_acceptance_rejects_the_auditors_counterexample():
    """Bättre än en dålig v1 men 40 pe fel, tur +1 bb/hand med stor spridning: fick 'godkänd' i 2.72.2."""
    N, db, st = _acc_world(20, bias_v2=-0.4, luck_mean=1.0, luck_noise=10.0)
    r = N.acceptance(db, st)
    assert r["status"] == "underkänd" and r["checkpoint"] == 20
    assert r["parts"]["kalibrering"]["ok"] is False and abs(r["parts"]["kalibrering"]["bias"] + 0.4) < 1e-9
    assert r["parts"]["tur"]["ok"] is False
    again = N.acceptance(db, st)
    assert again["status"] == "underkänd" and again.get("stored")  # första avgörandet är slutligt


def test_acceptance_waits_before_first_checkpoint_and_shows_no_interim_numbers():
    N, db, st = _acc_world(19, bias_v2=0.0, luck_mean=0.0)
    r = N.acceptance(db, st)
    assert r["status"] == "väntar" and r["passes"] == 19 and r["checkpoint"] == 0 and r["parts"] == {}
    assert N.meta_get(db.con, "acceptance_final") is None


def test_acceptance_can_pass_a_well_calibrated_low_variance_model():
    N, db, st = _acc_world(20, bias_v2=0.01, luck_mean=0.0, v1=0.3, per=400, ev_sd=0.5)
    r = N.acceptance(db, st)
    p = r["parts"]
    assert p["kalibrering"]["ok"] is True and p["fold"]["ok"] is True, p
    assert p["tur"]["var_gain"] > 0.5 and p["tur"]["ok"] is True, p["tur"]
    assert r["status"] == "godkänd"


def test_acceptance_luck_is_equivalence_not_failure_to_reject():
    """Medel 0 men stor osäkerhet: |m| < 2 SE räckte i 2.72.2. Nu krävs att intervallet ryms inom marginalen."""
    N, db, st = _acc_world(20, bias_v2=0.0, luck_mean=0.0, v1=0.3, luck_noise=10.0)
    r = N.acceptance(db, st)
    assert r["parts"]["tur"]["ok"] is not True and r["status"] != "godkänd"


def test_new_model_version_resets_anchor_and_grid_reaches_half():
    from plo_leak import night2 as N
    assert N.VERSION >= 3 and max(N.LAMBDAS) == 0.5
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE night2_meta (k TEXT PRIMARY KEY, v TEXT)")
    con.execute("INSERT INTO night2_meta VALUES ('lam', '0.3')")
    con.execute("INSERT INTO night2_meta VALUES ('ver', '2')")
    N.ensure_tables(con)
    assert N.meta_get(con, "lam") is None and N.meta_get(con, "ver") == N.VERSION


# ---------------------------------------------------------------- pengafält, svansvakt, coach
def test_actual_return_is_read_from_the_original_text():
    from plo_leak.postflop_rows import HEADER, actual_return
    h = SimpleNamespace(raw="x\nUncalled bet ($23.15) returned to abc123\ny", bb=2.0)
    assert actual_return(h, "Hero") == (11.57, 0) or actual_return(h, "Hero") == (11.58, 0)
    h2 = SimpleNamespace(raw="Uncalled bet ($4) returned to Hero", bb=1.0)
    assert actual_return(h2, "Hero") == (4.0, 1)
    assert actual_return(SimpleNamespace(raw=None, bb=1.0), "Hero") == ("", "")
    assert HEADER[-5:-2] == ["unmatched_bb", "hand_returned_bb", "hand_returned_to_hero"]  # 2.81: beat_strict, tie_frac sist


def test_tail_guard_says_why_it_blocks():
    from plo_leak.statlib import ci_cell
    r = ci_cell(np.tile([-1.0, -2.0, -3.0], 100), np.repeat(np.arange(30), 10))
    assert r["verdict"] == "osäkert (svansvakt)" and r["tail_blocked"] and r["hi"] < 0


def test_river_coach_declares_bet_fold_policy():
    from plo_leak import rivercoach
    assert rivercoach.BET_POLICY == "bet/fold"
    assert "bet/fold" in (ROOT / "plo_leak" / "templates" / "parts" / "postflop.html").read_text(encoding="utf-8")


def test_method_file_describes_273():
    from plo_leak import __version__
    from plo_leak.dataexport import METOD
    for k in ("Version " + __version__, "ekvivalenstest", "20, 40 och 80", "handtid", "bet/fold", "unmatched_bb", "svansvakt"):
        assert k in METOD, k
