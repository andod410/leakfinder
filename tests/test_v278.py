"""2.78: extra solverlägen (mot 3-bet, kallsyn, överkall, limp, 4-bet). Påhittade frekvenser."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))
from test_v276 import L0  # noqa: E402


def _hand(seq, hero_seat_name="Hero"):
    from plo_leak.parser import Action
    from plo_leak.cards import parse_cards
    names = ["U", "C", "B", "S", "BB"]
    acts = [Action("preflop", "S", "post_sb", 0.5), Action("preflop", "BB", "post_bb", 1.0)]
    for p, k, amt in seq:
        acts.append(Action("preflop", p, k, amt))
    return SimpleNamespace(num_hole=6, seats={n: i for i, n in enumerate(names)}, actions=acts, bb=1.0,
                           positions={"U": "HJ", "C": "CO", "B": "BTN", "S": "SB", "BB": "BB"})


def test_extra_decisions_match_sequences():
    from plo_leak.solvergroups import ALL_NODES, extra_decisions
    # BTN öppnar, SB foldar, BB 3-bettar, BTN synar
    h = _hand([("U", "fold", 0), ("C", "fold", 0), ("B", "raise", 3.5), ("S", "fold", 0), ("BB", "raise", 11.5), ("B", "call", 8.5)])
    r = extra_decisions(h, "B")
    assert len(r) == 1 and ALL_NODES[r[0][0]] == "F-F-RC5-F-RC15" and r[0][1] == 1 and abs(r[0][2] - 3.5) < 1e-9
    # BB kallsyn: BTN öppnar, SB 3-bettar, BB synar
    h = _hand([("U", "fold", 0), ("C", "fold", 0), ("B", "raise", 3.5), ("S", "raise", 11.5), ("BB", "call", 11)])
    r = extra_decisions(h, "BB")
    assert ALL_NODES[r[0][0]] == "F-F-RC5-RC16" and r[0][1] == 1 and abs(r[0][2] - 1.0) < 1e-9
    # BB mot SB-limp: check = kolumn 0, höj = 2
    h = _hand([("U", "fold", 0), ("C", "fold", 0), ("B", "fold", 0), ("S", "call", 0.5), ("BB", "check", 0)])
    r = extra_decisions(h, "BB")
    assert ALL_NODES[r[0][0]] == "F-F-F-C" and r[0][1] == 0
    # straddle eller fel antal spelare -> inget
    h.seats = {"a": 1}
    assert extra_decisions(h, "BB") == []


def test_normalize_extra_list_rows():
    from plo_leak.solverref import normalize_extra
    rows = []
    for l0 in L0:
        rows.append([l0, 0, [10, 80, 10], 1.0])
        rows.append(["AA", 1, [0, 50, 50], 0.1])
    raw = {"nodes": {"F-F-RC5-F-RC15": {"rows": rows}, "F-F-F-C": {"rows": [[l, 0, [60, 40], 1] for l in L0]}}}
    T = normalize_extra(raw)
    assert set(T) == {"F-F-RC5-F-RC15", "F-F-F-C"}
    assert T["F-F-F-C"][(L0[0],)] == [60.0, 0.0, 40.0]


def test_extra_nodes_in_facit_and_trainer():
    import json
    import numpy as np
    from test_v272 import _st
    from test_v276 import _fake_raw
    from plo_leak import solverref, solverfacit
    from plo_leak.solvergroups import EXTRA_NODES
    tab = solverref.normalize(_fake_raw())
    rows = [[l0, 0, [20, 70, 10], 1.0] for l0 in L0]
    tab.update(solverref.normalize_extra({"nodes": {n: {"rows": rows} for n in EXTRA_NODES}}))
    D = solverfacit.build(_st(), tab)
    assert D is not None
    sc = solverfacit.trainer_scenarios(tab)
    assert len(sc) == 14 + len(EXTRA_NODES)
    h = solverfacit.trainer_hand(tab, "F-F-F-C", seed=2)
    assert h and h["labels"]["fold"] == "Checka" and h["open_node"]
    h = solverfacit.trainer_hand(tab, "F-F-RC5-F-RC15", seed=2)
    assert h and set(h["ok"]) <= {"fold", "call", "raise"}


def test_force_skips_recent_hh_but_not_gg(monkeypatch):
    from plo_leak import night
    monkeypatch.setattr(night, "gg_status", lambda: "nej")
    monkeypatch.setattr(night, "recent_hh", lambda db: True)
    night.FORCE["until"] = 0
    assert "10 minuterna" in night.blocked(None)
    night.force_for(1)
    assert night.blocked(None) == ""
    monkeypatch.setattr(night, "gg_status", lambda: "ja")
    assert "GG-klienten körs" in night.blocked(None)
    night.FORCE["until"] = 0


def test_session_solver_entry_per_decision():
    from plo_leak.sessionfile import _solver_entry
    h = _hand([("U", "fold", 0), ("C", "fold", 0), ("B", "raise", 3.5), ("S", "fold", 0), ("BB", "raise", 11.5), ("B", "call", 8.5)])
    SF = {"ids": {"x": {"F-F": {"node": "BTN öppnar", "act": 2}, "F-F-RC5-F-RC15": {"node": "BTN öppnade, BB 3-bettar", "act": 1}}}}
    assert _solver_entry(SF, h, "B", "x", 0, "raise")["node"] == "BTN öppnar"
    assert _solver_entry(SF, h, "B", "x", 1, "call")["node"] == "BTN öppnade, BB 3-bettar"
    assert _solver_entry(SF, h, "B", "x", 1, "raise") is None


def test_every_node_has_description():
    from plo_leak.solvergroups import ALL_NODES, NODE_DESC
    assert all(n in NODE_DESC and "Du sitter" in NODE_DESC[n] for n in ALL_NODES)
