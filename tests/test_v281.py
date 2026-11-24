"""2.81: resten av granskningen av 2.79.1."""
from pathlib import Path

import numpy as np

from plo_leak.cards import parse_cards as P

HERE = Path(__file__).parent


def test_sequential_reading_is_frozen_on_first_passes():
    """Avläsningen vid 20 pass ändras inte av att fler pass läggs till (fasta prefix)."""
    from plo_leak.seqtest import cohorts, sequential
    rng = np.random.default_rng(1)
    ts = np.arange(30 * 10) * 60
    clu = np.repeat(np.arange(30), 10)
    x = rng.normal(-1, 1, len(ts))

    def cell(cm, fam):
        return {"verdict": "osäkert", "n": int(cm.sum())}
    r20 = sequential(cell, clu, cohorts(ts[:250], clu[:250]), 1)
    r30 = sequential(cell, clu, cohorts(ts, clu), 1)
    assert r20["look"] == r30["look"] == 20 and r20["n"] == r30["n"] == 200


def test_replay_folded_known_cards_are_dead_and_uncalled_returned():
    from plo_leak.parser import load_paths
    from plo_leak.replayer import replay_steps
    h = {x.id: x for x in load_paths([HERE / "real" / "gg_plo6_samples.txt"])}["OM89894633"]
    R = replay_steps(h, "Hero")
    flop = next(s for s in R["steps"] if s["street"] == "Flop")
    assert flop["pot"] == 81.5
    assert abs(flop["eq"]["by"]["0"] - 19.35) < 0.1 and abs(flop["eq"]["by"]["1"] - 80.65) < 0.1


def test_river_change_new_highest_straight():
    from plo_leak.riverbluff import river_change
    assert river_change(P("5c 6h 7s Kd 8d"), P("Ah Ad 2c 3c 4s 9s"))["straight"]


def test_beat_split_nut_broadway_is_zero_better():
    from plo_leak.board import BoardTable
    bt = BoardTable(P("Kc Qh Td 3s 7c"))
    better, tie = bt.beat_split(P("As Jh 2h 4d 5d 6s"))
    assert better == 0.0 and tie > 0


def test_showdown_risk_uses_whole_hands():
    from math import comb
    from plo_leak.board import BoardTable
    bt = BoardTable(P("2s 5s 9s Jd Qc"))
    exact = 6 / 41 * (1 - comb(33, 5) / comb(40, 5))
    assert abs(bt.beat_split(P("Ks 8s 3h 4h 7d Th"), 6, samples=4000)[0] - exact) < 0.015


def test_order_hash_changes_with_rule_order():
    from plo_leak.forward import rules_hash, rules_order_hash
    a = {"id": "a", "type": "cutoff", "spot": "rfi", "pos": "HJ", "thr": 1.0, "weights": [1]}
    b = {"id": "b", "type": "cutoff", "spot": "rfi", "pos": "CO", "thr": 1.0, "weights": [1]}
    assert rules_hash({"rules": [a, b]}) == rules_hash({"rules": [b, a]})
    assert rules_order_hash({"rules": [a, b]}) != rules_order_hash({"rules": [b, a]})


def test_signed_cache_rejects_unsigned(tmp_path, monkeypatch):
    import pickle
    monkeypatch.setenv("PLO_LEAK_CACHE", str(tmp_path))
    from plo_leak import signcache
    signcache._KEY.clear()
    blob = signcache.dumps({"a": 1})
    assert signcache.loads(blob) == {"a": 1}
    for bad in (pickle.dumps({"a": 1}), blob[:-1] + b"x"):
        try:
            signcache.loads(bad)
        except ValueError:
            continue
        raise AssertionError("osignerad fil lästes")


def test_short_bb_keeps_header_stake():
    from plo_leak.parser import parse_hand
    txt = (HERE / "real" / "user_hand_4bet_pot.txt").read_text(encoding="utf-8")
    t = txt.replace("Hero: posts big blind $1", "Hero: posts big blind $0.6 and is all-in")
    h = parse_hand(t)
    assert h is None or abs(h.bb - 1.0) < 1e-9


def test_sim_cache_key_has_seed():
    from plo_leak.sim import cache_path
    assert cache_path(10, 2, True, True, 1) != cache_path(10, 2, True, True, 2)


def test_v282_new_extra_nodes_match_sequences():
    """2.82: fem nya lägen – öppning + synare (SB/BB) och kall 4-bet på BTN."""
    import sys
    sys.path.insert(0, str(HERE))
    from test_v278 import _hand
    from plo_leak.solvergroups import ALL_NODES, NODE_DESC, extra_decisions
    h = _hand([("U", "raise", 3.5), ("C", "fold", 0), ("B", "call", 3.5), ("S", "fold", 0), ("BB", "call", 2.5)])
    r = extra_decisions(h, "BB")
    assert ALL_NODES[r[0][0]] == "RC5-F-C-F" and r[0][1] == 1
    h = _hand([("U", "fold", 0), ("C", "raise", 3.5), ("B", "call", 3.5), ("S", "raise", 15)])
    assert ALL_NODES[extra_decisions(h, "S")[0][0]] == "F-RC5-C"
    h = _hand([("U", "raise", 3.5), ("C", "raise", 12), ("B", "fold", 0)])
    assert ALL_NODES[extra_decisions(h, "B")[0][0]] == "RC5-RC17"
    for n in ("RC5-F-C-F", "F-RC5-F-C", "F-RC5-C", "RC5-F-C", "RC5-RC17"):
        assert "Du sitter" in NODE_DESC[n]
