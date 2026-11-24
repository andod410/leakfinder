"""2.76: solverjämförelse (egen fil, dold när GG körs, H4), handgrupper som solverns, rakeback i vinstkurvan.

Testerna använder en PÅHITTAD solverfil med slumpade siffror – ingen riktig solverdata finns i programmet."""
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from test_v272 import _st  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
L0 = [f"{p} {s}" for p in ("Unpaired", "One Pair", "Two Pair", "Three Pair")
      for s in ("Triple Suited", "Double Suited", "Single Suited")]


def _fake_raw(offset_node="F-F", two_cols=("root", "F", "F-F")):
    """Liten påhittad solverfil: alla 14 noder, nivå 0–1 och några nivå 2-rader, slumpade frekvenser."""
    from plo_leak.solvergroups import NODES
    rnd = random.Random(7)

    def f(n):
        a = rnd.uniform(0, 100)
        b = rnd.uniform(0, 100 - a)
        return [round(a, 2), round(100 - a, 2)] if n in two_cols else [round(a, 2), round(b, 2), round(100 - a - b, 2)]
    nodes = {}
    for n in NODES:
        off = 1 if n == offset_node else 0
        rows = []
        for l0 in L0:
            rows.append({"lab": l0, "d": 0 + off, "f": f(n), "wt": 1})
            for l1 in ("AA", "KK", "4Card Rundowns (0,1,2 gaps)", "Ragged"):
                rows.append({"lab": l1, "d": 1 + off, "f": f(n), "wt": 1})
                rows.append({"lab": "Pure, Suited Ace", "d": 2 + off, "f": f(n), "wt": 1})
        if off:
            rows += [{"lab": "A", "d": 0, "f": [1, 2], "wt": 1}]  # skräprad som ska hoppas över
        nodes[n] = {"rows": rows}
    return {"source": "TEST", "settings": ["Cash", "Preflop", "5-Max", "100bb", "3.5x"], "nodes": nodes}


# ---------------------------------------------------------------- inläsning
def test_normalize_offset_junk_and_two_columns():
    from plo_leak.solverref import normalize
    tab = normalize(_fake_raw())
    assert set(tab) and all(len(v) == 3 for T in tab.values() for v in T.values())
    assert ("Unpaired Triple Suited",) in tab["F-F"]  # nivåförskjutningen hanterad
    assert all(T[k][1] == 0.0 for T in (tab["root"],) for k in T)  # fold/höj-noder får syn = 0
    assert not any(k == ("A",) for k in tab["F-F"])


def test_normalize_rejects_missing_node():
    from plo_leak.solverref import normalize
    raw = _fake_raw()
    del raw["nodes"]["RC5"]
    try:
        normalize(raw)
    except ValueError as e:
        assert "CO mot UTG" in str(e)
    else:
        raise AssertionError("saknad nod ska ge fel")


def test_upload_saved_next_to_db_and_hash_stable(tmp_path):
    from plo_leak import solverref
    db = SimpleNamespace(path=tmp_path / "hander.db")
    data = json.dumps(_fake_raw()).encode()
    inf = solverref.save_upload(db, data)
    assert solverref.solver_path(db).exists() and solverref.solver_path(db).parent.name == "hander_solver"
    h1 = inf["hash"]
    solverref._CACHE.clear()
    assert solverref.info(db)["hash"] == h1
    try:
        solverref.save_upload(db, b"inte json")
    except ValueError:
        pass
    else:
        raise AssertionError
    solverref.remove(db)
    assert solverref.load(db) == (None, None)


# ---------------------------------------------------------------- handgrupper
def _c(s):
    from plo_leak.cards import parse_cards
    return parse_cards(" ".join(s[i:i + 2] for i in range(0, len(s), 2)))


def test_classify_known_hands():
    from plo_leak.solvergroups import classify
    assert classify(_c("AsAhAdKs5c2d")) is None  # trips finns inte i solvern
    l0, l1, c, a = classify(_c("AsAhJs6h4h2s"))
    assert (l0, l1) == ("One Pair Double Suited", "AA") and c[0] == "Trip Suited, 2 Nut Suits" and a
    l0, l1, c, _ = classify(_c("AhAcTd9s7h3s"))
    assert c[0] == "Pure, 1 Nut Suit"
    l0, l1, c, _ = classify(_c("KcJcTh9d7h6s"))
    assert l1.startswith("6Card") and c[0] == "Pure, 2+ Broadway"
    # klädda kort räknas utanför paret: KK med en klädd sidokort = Other, inte 2+ Broadway
    l0, l1, c, _ = classify(_c("KsKdJs9d8h3s"))
    assert l1 == "KK" and c[0] == "Trip Suited, Other"
    l0, l1, c, _ = classify(_c("8s8h7s7h5s3s"))
    assert l0 == "Two Pair Double Suited" and l1 == "99-88" and c[0] == "Quad Suited, Other"
    l0, l1, _, _ = classify(_c("Ad5h4c3s2h9d"))
    assert l1.startswith("5Card")  # ess räknas även lågt
    l0, l1, _, _ = classify(_c("AdKhQcTs9h3d"))
    assert l1.startswith("5Card")


def test_node_of_uses_internal_hj():
    from plo_leak.solvergroups import NODES, node_of
    A = lambda p, k: SimpleNamespace(street="preflop", player=p, kind=k)
    pos = {"u": "HJ", "c": "CO", "b": "BTN", "s": "SB", "bb": "BB"}
    h = SimpleNamespace(num_hole=6, positions=pos, actions=[A("s", "post_sb"), A("bb", "post_bb"), A("u", "raise"), A("c", "call")])
    assert NODES[node_of(h, "c")[0]] == "RC5" and node_of(h, "c")[1] == 1
    assert NODES[node_of(h, "u")[0]] == "root"
    h.actions = [A("s", "post_sb"), A("bb", "post_bb"), A("u", "call"), A("c", "raise")]
    assert node_of(h, "c") is None  # limpare före – inte i solvern
    h.actions = [A("s", "post_sb"), A("bb", "post_bb"), A("u", "raise"), A("c", "call"), A("b", "raise")]
    assert node_of(h, "b") is None  # synare efter öppningen
    h.num_hole = 4
    assert node_of(h, "u") is None


# ---------------------------------------------------------------- jämförelsen
def test_compare_runs_and_h4_waits_for_date():
    from plo_leak import solverref
    st = _st()
    assert len(st.ft.t["spn"]["hidx"]) > 1000
    R = solverref.compare(st, solverref.normalize(_fake_raw()))
    assert not R["empty"] and R["decisions"] > 1000 and len(R["lagen"]) == 14
    for r in R["lagen"]:
        assert abs(sum(r["du"]) - 100) < 1e-6 and abs(sum(r["sol"]) - 100) < 1.5
    assert R["h4"]["verdict"] == "för få" and R["h4"]["start"] == "2026-11-17"
    assert all(r["total"] <= R["rows"][-1]["total"] for r in R["rows"][:1])


def test_spn_matches_first_preflop_decision():
    st = _st()
    S, P = st.ft.t["spn"], st.ft.t["pre"]
    first = {}
    for k in range(len(P["hidx"])):
        first.setdefault(int(P["hidx"][k]), k)
    kinds = {c: st.ft.label("kind", c) for c in set(P["kind"].tolist())}
    for j in range(min(500, len(S["hidx"]))):
        k = first[int(S["hidx"][j])]
        assert {"fold": 0, "call": 1, "raise": 2}[kinds[int(P["kind"][k])]] == int(S["act"][j])


# ---------------------------------------------------------------- web: dold när GG körs
def _client(monkeypatch, tmp_path, gg):
    from plo_leak import night, web
    db = SimpleNamespace(path=tmp_path / "hander.db")
    monkeypatch.setattr(web, "get_db", lambda: db)
    monkeypatch.setattr(night, "gg_status", lambda: gg)
    st = _st()
    vid = web._add_view({"st": st, "leaks": [], "fu": {}, "mixed": False}, "Hero")
    return web.app.test_client(), vid, db


def test_solver_page_hidden_while_gg_runs(monkeypatch, tmp_path):
    c, vid, db = _client(monkeypatch, tmp_path, "ja")
    html = c.get(f"/v/{vid}/solver").get_data(as_text=True)
    assert "Solver-sidan är dold" in html and "Frekvenser per läge" not in html
    r = c.post("/solver/fil", data={"vid": vid})
    assert r.status_code == 409


def test_solver_page_unknown_gg_status_also_hidden(monkeypatch, tmp_path):
    c, vid, _ = _client(monkeypatch, tmp_path, "okänd")
    assert "Solver-sidan är dold" in c.get(f"/v/{vid}/solver").get_data(as_text=True)


def test_solver_page_with_file(monkeypatch, tmp_path):
    from plo_leak import solverref
    c, vid, db = _client(monkeypatch, tmp_path, "nej")
    assert "Ingen solverfil inlagd" in c.get(f"/v/{vid}/solver").get_data(as_text=True)
    solverref.save_upload(db, json.dumps(_fake_raw()).encode())
    html = c.get(f"/v/{vid}/solver").get_data(as_text=True)
    assert "Frekvenser per läge" in html and "H4" in html and "BB mot SB" in html


# ---------------------------------------------------------------- licensskydd
def test_solver_data_never_in_exports_or_package():
    src = ROOT / "plo_leak"
    # 2.77: sessionsfilen får solverfacit (Andreas 2026-11-18: programmet används bara av honom, delning med Claude tillåten)
    for mod in ("dataexport.py", "share.py", "hhexport.py", "export.py", "nightly.py"):
        assert "solverref" not in (src / mod).read_text(encoding="utf-8"), mod
    for p in ROOT.rglob("*.json"):
        if "privat" in p.parts:  # 2.77.2: solverfilen får ligga i privat/, men aldrig i kodpaketet (se test_v277)
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        assert "PLO Mastermind" not in t and "PLO6_PLO6-GG" not in t, p


def test_frozen_definitions_unchanged():
    from plo_leak import hypotheses
    assert hypotheses.HYP_HASH == "e4e93fbb9face71d"


# ---------------------------------------------------------------- rakeback i grafen
def test_rakeback_curve_settings_and_summary(tmp_path):
    from plo_leak import rbcurve
    db = SimpleNamespace(path=tmp_path / "hander.db")
    assert rbcurve.settings(db)["on"] is False
    rbcurve.save(db, {"toggle": "1"})
    assert rbcurve.settings(db)["on"] is True
    rbcurve.save(db, {"ocean": "20", "agent": "x", "lb_PLO6 0.5/1": "5,5"})
    cfg = rbcurve.settings(db)
    assert cfg["ocean"] == 20 and cfg["agent"] == 0 and cfg["lb"]["PLO6 0.5/1"] == 5.5 and cfg["on"] is True
    st = _st()
    S = rbcurve.summary(st, cfg)
    assert S["ev100_rb"] > S["ev100"] and len(S["cum_ev_rb"]) == st.hands
    assert 19.9 < S["pct"] < 40


def test_overview_shows_rakeback_line_when_on(monkeypatch, tmp_path):
    from plo_leak import rbcurve, web
    from plo_leak.report import _chart
    st = _st()
    db = SimpleNamespace(path=tmp_path / "hander.db")
    monkeypatch.setattr(web, "get_db", lambda: db)
    C = {"st": st, "chart": _chart({"net": st.cumulative, "ev": st.cumulative_ev, "rake": st.cumulative_rake})}
    assert not any(s["k"] == "ev_rb" for s in web._rb_extra(C).get("chart", C["chart"])["s"])
    rbcurve.save(db, {"toggle": "1"})
    ch = web._rb_extra(C)["chart"]
    assert ch["s"][-1]["k"] == "ev_rb" and len(ch["s"][-1]["v"]) == len(ch["x"])
