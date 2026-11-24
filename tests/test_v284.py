"""2.84: fem nya solverlägen (påhittade sekvenser testas mot matchningen, ingen riktig solverdata här)."""
from types import SimpleNamespace


def _h(seq, hero_seat_order):
    """Bygg en minimal hand: seq = lista av (spelare, handling)."""
    acts = [SimpleNamespace(street="preflop", kind="post_sb", player="SB", added=0.5),
            SimpleNamespace(street="preflop", kind="post_bb", player="BB", added=1.0)]
    acts += [SimpleNamespace(street="preflop", kind=k, player=p, added=0.0) for p, k in seq]
    return SimpleNamespace(num_hole=6, seats={i: x for i, x in enumerate(["UTG", "CO", "BTN", "SB", "BB"])}, actions=acts, bb=1.0)


def test_new_nodes_match_sequences():
    from plo_leak.solvergroups import extra_decisions, ALL_NODES
    h = _h([("UTG", "raise"), ("CO", "raise"), ("BTN", "fold"), ("SB", "call")], None)
    d = extra_decisions(h, "SB")
    assert [ALL_NODES[x[0]] for x in d] == ["RC5-RC17-F"] and d[0][1] == 1
    h = _h([("UTG", "fold"), ("CO", "raise"), ("BTN", "raise"), ("SB", "fold")], None)
    assert [ALL_NODES[x[0]] for x in extra_decisions(h, "SB")] == ["F-RC5-RC17"]
    h = _h([("UTG", "raise"), ("CO", "call"), ("BTN", "call"), ("SB", "fold"), ("BB", "raise")], None)
    assert [ALL_NODES[x[0]] for x in extra_decisions(h, "BB")] == ["RC5-C-C-F"]
    h = _h([("UTG", "fold"), ("CO", "fold"), ("BTN", "raise"), ("SB", "call"), ("BB", "raise"), ("BTN", "call")], None)
    assert [ALL_NODES[x[0]] for x in extra_decisions(h, "BTN")] == ["F-F-RC5-C-RC21"]
    h = _h([("UTG", "fold"), ("CO", "raise"), ("BTN", "fold"), ("SB", "call"), ("BB", "raise"), ("CO", "fold")], None)
    assert [ALL_NODES[x[0]] for x in extra_decisions(h, "CO")] == ["F-RC5-F-C-RC21"]


def test_new_nodes_categories_and_texts():
    from plo_leak.solverfacit import _cat
    from plo_leak.solvergroups import NODE_DESC, EXTRA_PRIOR
    assert _cat("RC5-RC17-F", 1) == "call" and _cat("F-RC5-RC17", 2) == "raise"
    assert _cat("RC5-C-C-F", 1) is None                       # BB-försvar räknas inte
    assert _cat("F-F-RC5-C-RC21", 1) is None and _cat("F-RC5-F-C-RC21", 2) == "raise"
    assert EXTRA_PRIOR["F-F-RC5-C-RC21"] == ("F-F", 2) and EXTRA_PRIOR["F-RC5-F-C-RC21"] == ("F", 2)
    for n in ("RC5-RC17-F", "F-RC5-RC17", "RC5-C-C-F", "F-F-RC5-C-RC21", "F-RC5-F-C-RC21"):
        assert n in NODE_DESC
