"""2.79: snabbare analyser, cachenyckel per analys, urvalscache och förberäkningskö."""
import random

import numpy as np


def test_has_straight_matches_reference():
    from plo_leak.postflop_rows import _has_straight, _has_straight_ref
    rnd = random.Random(11)
    deck = [(r, s) for r in range(2, 15) for s in "cdhs"]
    for _ in range(20000):
        nh, nb = rnd.choice([4, 5, 6]), rnd.choice([3, 4, 5])
        c = rnd.sample(deck, nh + nb)
        h, b = [x[0] for x in c[:nh]], [x[0] for x in c[nh:]]
        if rnd.random() < 0.3:
            b.append(rnd.randint(2, 14))
        assert _has_straight(h, b) == _has_straight_ref(h, b)


def test_fingerprint_follows_source(monkeypatch):
    from plo_leak import analyses
    fp = analyses.fingerprint("potsize")
    assert fp == analyses.fingerprint("potsize") and not fp.startswith("v")
    assert "potsize" in analyses._closure({"potsize"})
    orig = analyses._mod_src
    monkeypatch.setattr(analyses, "_FP", {})
    monkeypatch.setattr(analyses, "_mod_src", lambda m: (orig(m) or b"") + (b"#x" if m == "potsize" else b""))
    assert analyses.fingerprint("potsize") != fp
    # en modul utanför analysens beroenden (webben) påverkar inte nyckeln
    monkeypatch.setattr(analyses, "_FP", {})
    monkeypatch.setattr(analyses, "_mod_src", lambda m: (orig(m) or b"") + (b"#x" if m == "web" else b""))
    assert analyses.fingerprint("potsize") == fp


def test_context_cache_roundtrip(tmp_path, monkeypatch):
    from pathlib import Path
    from plo_leak.db import HandDB
    from plo_leak.pipeline import build
    from plo_leak.selection import Selection
    from plo_leak import precompute
    monkeypatch.setenv("PLO_LEAK_CACHE", str(tmp_path / "c"))
    monkeypatch.setenv("PLO_CTX_CACHE", "1")
    db = HandDB(tmp_path / "h.db")
    db.add_paths([Path(__file__).parent / "real"])
    hero = db.detect_hero()
    store = db.facts(hero)
    store.sync(db)
    ft = store.load()
    cd = tmp_path / "h_resultat"
    kw = dict(use_db=True, data_sig=store.signature(), cache_dir=cd, as_context=True, view=True, imports=[])
    sel = Selection(games=("PLO6",), latest=50)
    C1 = build(ft, hero, db.get_hand, sel, **kw)
    assert len(list((cd / precompute.CTX_DIR).glob("*.pkl"))) == 1
    C2 = build(ft, hero, db.get_hand, sel, **kw)
    assert C2 is not C1 and C2["st"].ft is ft
    assert C2["st"].hands == C1["st"].hands and C2["filters"] == C1["filters"]
    assert C2["st"].hands_by_id._lookup is not None  # händerna kan hämtas ur databasen igen
    assert C2["leaks"] == C1["leaks"] and C2["chart"] == C1["chart"]
    assert precompute.plan(ft)[0] == ("view", {"games": ("PLO6",)})
    assert precompute.plan(ft)[-1][0] == "warm"
