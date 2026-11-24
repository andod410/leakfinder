"""2.86: tolv nya solverlägen (56), all-in EV inkl. rakeback i sessionsgraferna och sessionsfilen, paus 15 min."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from test_v284 import _h  # noqa: E402


def _node(seq, hero):
    from plo_leak.solvergroups import extra_decisions, ALL_NODES
    return [ALL_NODES[x[0]] for x in extra_decisions(_h(seq, None), hero)]


NEW = ("RC5-RC17-RC58-F-F", "RC5-F-F-C-RC21-C", "RC5-F-F-RC16-C", "RC5-C-RC24", "RC5-RC17-C-F", "RC5-F-C-C",
       "RC5-C-C-C", "RC5-RC17-F-F", "RC5-C-RC24-F", "RC5-F-RC17-F", "RC5-F-RC17-C-F", "RC5-C-F-F")


def test_56_nodes_with_texts():
    from plo_leak.solvergroups import ALL_NODES, NODE_DESC, NODE_LABEL
    assert len(ALL_NODES) == 56
    for n in NEW:
        assert n in ALL_NODES and n in NODE_DESC and NODE_LABEL.get(n)


def test_new_nodes_match():
    U, C, B, S, BB = "UTG", "CO", "BTN", "SB", "BB"
    r, c, f = "raise", "call", "fold"
    assert _node([(U, r), (C, r), (B, r), (S, f), (BB, f), (U, f)], U) == ["RC5-RC17-RC58-F-F"]
    assert _node([(U, r), (C, f), (B, f), (S, c), (BB, r), (U, c), (S, f)], S) == ["RC5-F-F-C-RC21-C"]
    assert _node([(U, r), (C, f), (B, f), (S, r), (BB, c), (U, f)], U) == ["RC5-F-F-RC16-C"]
    assert _node([(U, r), (C, c), (B, r), (S, f)], S) == ["RC5-C-RC24"]
    assert _node([(U, r), (C, r), (B, c), (S, f), (BB, f)], BB) == ["RC5-RC17-C-F"]
    assert _node([(U, r), (C, f), (B, c), (S, c), (BB, f)], BB) == ["RC5-F-C-C"]
    assert _node([(U, r), (C, c), (B, c), (S, c), (BB, f)], BB) == ["RC5-C-C-C"]
    assert _node([(U, r), (C, r), (B, f), (S, f), (BB, f)], BB) == ["RC5-RC17-F-F"]
    assert _node([(U, r), (C, c), (B, r), (S, f), (BB, f)], BB) == ["RC5-C-RC24-F"]
    assert _node([(U, r), (C, f), (B, r), (S, f), (BB, f)], BB) == ["RC5-F-RC17-F"]
    assert _node([(U, r), (C, f), (B, r), (S, c), (BB, f), (U, f)], U) == ["RC5-F-RC17-C-F"]
    assert _node([(U, r), (C, c), (B, f), (S, f), (BB, f)], BB) == ["RC5-C-F-F"]


def test_new_nodes_categories_and_words():
    from plo_leak.solverfacit import _cat
    from plo_leak.solvergroups import EXTRA_PRIOR
    for n in ("RC5-RC17-RC58-F-F", "RC5-F-F-RC16-C", "RC5-F-RC17-C-F"):
        assert EXTRA_PRIOR[n] == ("root", 2) and _cat(n, 1) is None and _cat(n, 2) == "raise"
    assert EXTRA_PRIOR["RC5-F-F-C-RC21-C"] == ("RC5-F-F", 1) and _cat("RC5-F-F-C-RC21-C", 1) is None
    assert _cat("RC5-C-RC24", 1) == "call"          # SB kallsynar en squeeze: syn utanför BB
    for n in ("RC5-RC17-C-F", "RC5-F-C-C", "RC5-C-C-C", "RC5-RC17-F-F", "RC5-C-RC24-F", "RC5-F-RC17-F", "RC5-C-F-F"):
        assert _cat(n, 1) is None and _cat(n, 2) == "raise"   # BB försvarar: ingen syn-kategori


def test_rb_rows_and_chart_series():
    from types import SimpleNamespace
    from plo_leak.rbcurve import rb_rows, DEFAULT
    from plo_leak.report import _chart

    class FT:
        H = {"game": np.zeros(4, np.int16), "stake": np.zeros(4, np.int16), "ttype": np.zeros(4, np.int8),
             "rake": np.array([1.0, 0.0, 2.0, 1.0]), "rake_m": np.array([1.0, 0.0, 2.0, 1.0]),
             "ev": np.array([1.0, -2.0, 3.0, 0.0])}

        @staticmethod
        def label(col, code):
            return {"game": "PLO6", "stake": "0.5/1"}[col]
    cfg = {**DEFAULT, "ocean": 20.0, "agent": 0.0, "lb": {**DEFAULT["lb"], "PLO6 0.5/1": 5.0}}
    rb, rb_m = rb_rows(FT, np.arange(4), cfg)
    assert np.allclose(rb, [0.25, 0.0, 0.5, 0.25]) and np.allclose(rb_m, rb)
    ch = _chart({"net": np.cumsum(FT.H["ev"]), "ev": np.cumsum(FT.H["ev"]), "ev_rb": np.cumsum(FT.H["ev"] + rb)})
    s = {x["k"]: x for x in ch["s"]}
    assert "ev_rb" in s and abs(s["ev_rb"]["v"][-1] - 3.0) < 1e-9 and s["ev_rb"]["label"] == "All-in EV inkl. rakeback"
    assert SimpleNamespace  # används inte vidare


def test_rb_line_in_session_file():
    from plo_leak.sessionfile import _rb_line
    from plo_leak.rbcurve import DEFAULT  # noqa: F401

    class FT:
        H = {"game": np.zeros(2, np.int16), "stake": np.zeros(2, np.int16), "ttype": np.zeros(2, np.int8),
             "rake": np.array([2.0, 2.0]), "rake_m": np.array([2.0, 2.0]), "money": np.array([-5.0, -5.0])}

        @staticmethod
        def label(col, code):
            return {"game": "PLO6", "stake": "0.5/1"}[col]
    line = _rb_line(FT, np.arange(2), -10.0, -10.0, 2)
    assert "Verklig winrate (all-in EV inkl. rakeback)" in line and "% av raken" in line and "Tur i all-ins" in line


def test_pause_is_15_min():
    from plo_leak import fatigue
    from plo_leak.guidelines import PRIO
    assert fatigue.PAUSE_SEC == 900
    assert "15 min" in PRIO[6][2] and "2 min" not in PRIO[6][2]
    src = (Path(__file__).parent.parent / "plo_leak" / "sessionfile.py").read_text(encoding="utf-8")
    assert "15 min paus efter förlorad pott" in src


def test_version():
    import plo_leak
    from plo_leak.facts import FACTS_VERSION
    assert plo_leak.__version__ >= "2.86" and FACTS_VERSION >= 24
