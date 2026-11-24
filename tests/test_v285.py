"""2.85: åtta nya solverlägen – matchning av sekvenser, kategorier och texter."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_v284 import _h  # noqa: E402


def _node(seq, hero):
    from plo_leak.solvergroups import extra_decisions, ALL_NODES
    return [ALL_NODES[x[0]] for x in extra_decisions(_h(seq, None), hero)]


def test_new_nodes_match():
    assert _node([("UTG", "raise"), ("CO", "raise"), ("BTN", "fold"), ("SB", "fold"), ("BB", "fold"), ("UTG", "call")], "UTG") == ["RC5-RC17-F-F-F"]
    assert _node([("UTG", "raise"), ("CO", "fold"), ("BTN", "fold"), ("SB", "raise"), ("BB", "fold"), ("UTG", "call")], "UTG") == ["RC5-F-F-RC16-F"]
    assert _node([("UTG", "raise"), ("CO", "fold"), ("BTN", "fold"), ("SB", "fold"), ("BB", "raise"), ("UTG", "fold")], "UTG") == ["RC5-F-F-F-RC15"]
    assert _node([("UTG", "fold"), ("CO", "raise"), ("BTN", "fold"), ("SB", "raise"), ("BB", "fold"), ("CO", "call")], "CO") == ["F-RC5-F-RC16-F"]
    assert _node([("UTG", "raise"), ("CO", "call"), ("BTN", "call"), ("SB", "fold")], "SB") == ["RC5-C-C"]
    assert _node([("UTG", "fold"), ("CO", "raise"), ("BTN", "call"), ("SB", "call"), ("BB", "raise"), ("CO", "fold")], "CO") == ["F-RC5-C-C-RC28"]
    assert _node([("UTG", "raise"), ("CO", "call"), ("BTN", "call"), ("SB", "fold"), ("BB", "raise"), ("UTG", "call")], "UTG") == ["RC5-C-C-F-RC29"]
    assert _node([("UTG", "raise"), ("CO", "fold"), ("BTN", "fold"), ("SB", "call"), ("BB", "raise"), ("UTG", "call")], "UTG") == ["RC5-F-F-C-RC21"]


def test_new_nodes_categories():
    from plo_leak.solverfacit import _cat
    from plo_leak.solvergroups import NODE_DESC, EXTRA_PRIOR, ALL_NODES
    assert len(ALL_NODES) >= 44
    assert _cat("RC5-C-C", 1) == "call" and _cat("RC5-C-C", 2) == "raise"
    for n in ("RC5-RC17-F-F-F", "RC5-F-F-RC16-F", "RC5-F-F-F-RC15", "F-RC5-F-RC16-F", "F-RC5-C-C-RC28", "RC5-C-C-F-RC29", "RC5-F-F-C-RC21"):
        assert _cat(n, 1) is None and _cat(n, 2) == "raise" and n in EXTRA_PRIOR and n in NODE_DESC
