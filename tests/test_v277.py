"""2.77: solvern som facit, Topp 3, träningsruta, 4 h-flagga, dolda/nedgraderade riktlinjer.
Påhittad solverfil – ingen riktig solverdata i programmet."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from test_v272 import _st  # noqa: E402
from test_v276 import _fake_raw, _client  # noqa: E402


def _D():
    from plo_leak import solverref, solverfacit
    return solverfacit.build(_st(), solverref.normalize(_fake_raw()))


def test_verdict_levels():
    from plo_leak.solverfacit import verdict
    assert verdict(0.5) == "fel" and verdict(1.0) == "tveksamt" and verdict(9.9) == "tveksamt" and verdict(10) == "ok"


def test_build_marks_errors_consistently():
    D = _D()
    assert len(D["hidx"]) and (D["fel"] == (D["s_act"] < 1)).all()
    assert not (D["fel"] & D["tvek"]).any()


def test_training_box_selects_by_errors_and_has_four_colour_examples(monkeypatch):
    from plo_leak import solverfacit
    monkeypatch.setattr(solverfacit, "MIN_BESLUT_LAGE", 5)
    monkeypatch.setattr(solverfacit, "MIN_GRUPP", 3)
    T = solverfacit.training(_st(), None, days=3650, D=_D())
    assert not T["empty"] and 1 <= len(T["lagen"]) <= 3
    # 2.83: sorteras på $/h när timtakten finns, annars på klara fel per 100 händer
    key = [(r["usd_h"] if T.get("hph") else r["per100"]) or 0.0 for r in T["all"]]
    assert key == sorted(key, reverse=True)
    ex = [e for r in T["lagen"] for e in r["examples"]]
    assert ex and all(e["s_act"] < 1 for e in ex)
    assert any(s in ex[0]["cards"] for s in ("♠️", "♥️", "🔷", "☘️"))
    for r in T["lagen"]:
        for x in r["rules"]:
            assert (x["kind"] == "folda" and x["sol"] <= 10) or (x["kind"] == "spela" and x["sol"] >= 80)


def test_long_session_flag_only_when_ev_negative_or_worse():
    from plo_leak import solverfacit
    st = _st()
    H = st.ft.H
    t0 = int(H["ts"].min())
    assert solverfacit.long_session_flag(st, None, t0, t0 + 3 * 3600) is None
    f = solverfacit.long_session_flag(st, None, t0, t0 + 5 * 3600)
    m = (H["ts"] >= t0) & (H["ts"] <= t0 + 5 * 3600)
    assert f["warn"] == (float(H["ev"][m].sum()) < 0)


def test_solver_page_shows_training(monkeypatch, tmp_path):
    from plo_leak import solverref, solverfacit
    monkeypatch.setattr(solverfacit, "MIN_BESLUT_LAGE", 5)
    c, vid, db = _client(monkeypatch, tmp_path, "nej")
    solverref.save_upload(db, json.dumps(_fake_raw()).encode())
    html = c.get(f"/v/{vid}/solver").get_data(as_text=True)
    assert "Frekvenser per läge" in html


def test_top3_hidden_solver_when_gg_unknown(monkeypatch, tmp_path):
    from plo_leak import solverref, web
    c, vid, db = _client(monkeypatch, tmp_path, "okänd")
    T = web._top3({"st": _st()})
    assert all("klara fel" not in x["title"] for x in T["items"])


def test_top3_max_three_items(monkeypatch, tmp_path):
    from plo_leak import solverref, solverfacit, web
    monkeypatch.setattr(solverfacit, "MIN_BESLUT_LAGE", 5)
    c, vid, db = _client(monkeypatch, tmp_path, "nej")
    solverref.save_upload(db, json.dumps(_fake_raw()).encode())
    T = web._top3({"st": _st(), "postflop_leaks": [{"do": "x", "per100": 0.5, "link": "postflop"}]})
    assert len(T["items"]) <= 3


def test_guidelines_hidden_and_downgraded():
    from plo_leak.guidelines import GUIDELINES, HIDDEN_277, DOWNGRADE_277, visible
    G = {g["id"]: g for g in GUIDELINES}
    assert all(not visible(i) for i in HIDDEN_277 | DOWNGRADE_277)
    assert all(G[i]["level"].startswith("trolig") for i in DOWNGRADE_277)
    assert visible("set_cr")


def test_two_hour_rule_not_a_leak():
    import inspect
    from plo_leak import report
    src = inspect.getsource(report.add_session_focus)
    assert "focus_item(st, rules_doc" not in src


def test_frozen_fingerprints_unchanged():
    from plo_leak import hypotheses, pfforward
    assert hypotheses.HYP_HASH == "e4e93fbb9face71d"
    assert pfforward.specs_hash() == pfforward.SPECS_FROZEN_HASH == "eee8fd8d3da53304"


def test_solver_trainer_hand_and_gate(monkeypatch, tmp_path):
    from plo_leak import solverref, solverfacit
    tab = solverref.normalize(_fake_raw())
    for nd in ("root", "F-F-RC5"):
        h = solverfacit.trainer_hand(tab, nd, seed=3)
        assert h and h["mode"] == "3bet" and len(h["cards"]) == 6 and set(h["ok"]) <= {"fold", "call", "raise"}
        assert h["open_node"] == (nd == "root")
    c, vid, db = _client(monkeypatch, tmp_path, "okänd")
    solverref.save_upload(db, json.dumps(_fake_raw()).encode())
    assert c.get("/trana/hand?s=sol|root").status_code == 404
    c, vid, db = _client(monkeypatch, tmp_path, "nej")
    solverref.save_upload(db, json.dumps(_fake_raw()).encode())
    r = c.get("/trana/hand?s=sol|root")
    assert r.status_code == 200 and r.get_json()["ok"]
    assert "🧮" in c.get("/trana").get_data(as_text=True)


def test_river_change_and_veto():
    from plo_leak.cards import parse_cards as pc
    from plo_leak.riverbluff import river_change
    b = pc("9s 8h 2c Kd 4s")           # blank river
    assert not river_change(b, pc("Ah Qh Jc Tc 3d 3h"))["s1"]
    b = pc("9s 8h 2s Kd 4s")           # ny färg (spader)
    r = river_change(b, pc("Ah Qh Jc Tc 3d 3h"))
    assert r["s1"] and r["flush"] and r["veto"]            # inget spader – veto
    assert not river_change(b, pc("As Qh Jc Tc 3d 3h"))["veto"]
    assert river_change(pc("9s 8h 2c Kd 9d"), pc("Ah Qh Jc Tc 3d 3h"))["s1"]   # parat
    assert river_change(pc("Ks Qh 2c 3d Js"), pc("Ah Qd Jc 7c 3h 3s"))["straight"]


def test_bluff_v2_runs_itt_and_v1_not_shown():
    from plo_leak.riverbluff import bluff_test_v2
    st = _st()
    B = bluff_test_v2(st, since_ts=0)
    assert B["version"] == 2 and "spots" in B and "¾ pott" in B["rule"]
    import inspect
    from plo_leak import report
    assert "bluff_test_v2(st)" in inspect.getsource(report)


def test_rakeback_day_form(tmp_path):
    from plo_leak import rbweek
    db = SimpleNamespace(path=tmp_path / "hander.db")
    st = _st()
    from plo_leak.facts import dt_of
    d = dt_of(int(st.ft.H["ts"][st.rows].max())).strftime("%Y-%m-%d")
    rbweek.add(db, {"day": d, "gems": "100", "gem_usd": "", "lb_usd": "3", "other_usd": ""})
    rbweek.add(db, {"gem_rate": "0,05"})
    T = rbweek.table(st, db)
    assert len(T["rows"]) == 1 and abs(T["rows"][0]["value"] - 8.0) < 1e-9 and T["rows"][0]["hands"] > 0 and T["weeks"]
    rbweek.add(db, {"redeem": "1", "rday": d, "rgems": "1000", "rusd": "80"})
    T = rbweek.table(st, db)
    assert T["rate_realized"] and abs(T["gem_rate"] - 0.08) < 1e-9 and abs(T["rows"][0]["value"] - 11.0) < 1e-9
    assert abs(T["rows"][0]["cash_pct"] * T["rows"][0]["rake"] / 100 - 3.0) < 1e-6
    rbweek.add(db, {"day": d, "ta_bort": "1"})
    assert rbweek.table(st, db)["rows"] == []


def test_session_file_with_solver_facit():
    from plo_leak.sessionfile import build
    from plo_leak.sessions import session_detail, session_table
    st = _st()
    T = session_table(st, None)
    s = session_detail(T, T["sessions"][0]["key"], st, "Hero")
    D = _D()
    txt = build(st, s, "Hero", {"rules": []}, None, "2.77", None, D)
    assert "Preflop mot solvern" in txt and "klara fel" in txt
    assert "🧮 solvern" in txt or "0 beslut" in txt
    txt0 = build(st, s, "Hero", {"rules": []}, None, "2.77", None, None)
    assert "Preflop mot solvern" not in txt0 and "🧮" not in txt0


def test_misstag_detectors():
    from plo_leak import misstag
    from plo_leak.parser import Action
    from plo_leak.cards import parse_cards as pc
    h = SimpleNamespace(hole={"Hero": pc("Ks Qd Jh 9c 8s 4d")}, board=[],
                        actions=[Action("preflop", "A", "raise"), Action("preflop", "Hero", "raise"), Action("preflop", "A", "raise"),
                                 Action("preflop", "Hero", "raise"), Action("preflop", "A", "raise"), Action("preflop", "Hero", "call")])
    assert misstag.preflop(h, "Hero")[0]["kind"] == "granska"
    from plo_leak.postflop_rows import HEADER
    idx = {k: HEADER.index(k) for k in HEADER}
    row = [""] * len(HEADER)
    row[idx["street"]], row[idx["action"]], row[idx["facing"]] = "flop", "call", "raise"
    row[idx["board_paired"]], row[idx["hand"]], row[idx["beat_frac"]] = 1, "två par", 0.4
    h2 = SimpleNamespace(hole={"Hero": pc("As Ah Jd Jc Ts 4h")}, board=pc("9s 6h 3c 3d"), actions=[])
    assert misstag.postflop(h2, "Hero", [row], idx)[0]["kind"] == "granska"  # 2.80: granska, inte fel
    row2 = list(row); row2[idx["street"]], row2[idx["facing"]], row2[idx["hand"]], row2[idx["board_paired"]] = "river", "bet", "stege", 0
    h3 = SimpleNamespace(hole={"Hero": pc("5s 4h Kd Kc Ts 2h")}, board=pc("6s 7h 8c Kd 9d"), actions=[])
    assert any("fyra till stege" in m["text"] for m in misstag.postflop(h3, "Hero", [row2], idx))


def test_trainer_page_solver_default_and_notes(monkeypatch, tmp_path):
    from plo_leak import solverref, solverfacit
    tab = solverref.normalize(_fake_raw())
    f = solverfacit.open_freq(tab, n=500)
    assert set(f) == {"HJ", "CO", "BTN", "SB"} and all(0 <= v <= 100 for v in f.values())
    c, vid, db = _client(monkeypatch, tmp_path, "nej")
    assert "ingen solverfil" in c.get("/trana").get_data(as_text=True)
    solverref.save_upload(db, json.dumps(_fake_raw()).encode())
    html = c.get("/trana").get_data(as_text=True)
    assert "Solvern är facit: välj ett läge" in html and 'value="sol|root" selected' in html
    c, vid, db = _client(monkeypatch, tmp_path, "ja")
    assert "GG-klienten körs" in c.get("/trana").get_data(as_text=True)


def test_bundled_solver_installed_and_never_packed(monkeypatch, tmp_path):
    from plo_leak import solverref
    src = tmp_path / "privat.json"  # påhittad fil – conftest stänger av den riktiga
    src.write_text(json.dumps(_fake_raw()), encoding="utf-8")
    monkeypatch.setattr(solverref, "BUNDLED", src)
    db = SimpleNamespace(path=tmp_path / "hander.db")
    solverref._CACHE.clear()
    tab, inf = solverref.load(db)
    assert tab is not None and solverref.solver_path(db).exists()
    import importlib.util
    spec = importlib.util.spec_from_file_location("pack", Path(__file__).resolve().parents[1] / "tools" / "pack.py")
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    assert "privat" in pack.SKIP_DIRS
    for rel, _p in pack.files(str(Path(__file__).resolve().parents[1])):
        assert not rel.startswith("privat/")



def test_gg_day_start_dst():
    from datetime import datetime
    from plo_leak.rbweek import day_start
    assert day_start(datetime(2026, 11, 18)) == datetime(2026, 11, 18, 9, 0)
    assert day_start(datetime(2026, 7, 1)) == datetime(2026, 7, 1, 10, 0)
    assert day_start(datetime(2026, 3, 29)) == datetime(2026, 3, 29, 10, 0)   # sommartid börjar 29 mars 2026
    assert day_start(datetime(2026, 10, 25)) == datetime(2026, 10, 25, 9, 0)  # vintertid från 25 okt 2026


def test_multi_sessions_view_and_file(monkeypatch, tmp_path):
    from plo_leak import web
    from plo_leak.sessions import session_table, session_detail
    from plo_leak.sessionfile import build_multi
    st = _st()
    T = session_table(st, None)
    keys = [s["key"] for s in T["sessions"]][:7]
    db = SimpleNamespace(path=tmp_path / "hander.db")
    monkeypatch.setattr(web, "get_db", lambda: db)
    V = {"C": {"st": st, "sessions": T}, "hero": "Hero"}
    M = web._multi_sessions(V, keys)
    assert M["n_sess"] == len(keys) and M["hands"] > 0 and M["chart"]["d"] and len(M["chart"]["d"]) == len(M["chart"]["x"])
    S = sorted([session_detail(T, k, st, "Hero") for k in keys], key=lambda x: x["t0"])
    if len(S) > 5:
        txt = build_multi(st, S, "Hero", {"rules": []}, None, "2.77.6", None, None)
        assert f"# Alla {len(S)} sessioner" in txt and txt.count("### Pott ") <= 20


def test_night3_line_fit_predict_and_acceptance(tmp_path, monkeypatch):
    import numpy as np
    from plo_leak import night3
    from test_v272 import _CACHE
    _st()
    hs = _CACHE["hands"]
    rng = np.random.default_rng(1)
    monkeypatch.setattr(night3, "K", 40)
    monkeypatch.setattr(night3, "NEXT", 3)
    tr, hi = [], []
    for h in hs:
        if len(h.board) != 5:
            continue
        for p in h.remaining():
            if p != "Hero":
                it = night3.train_item(h, "Hero", p, None, rng)
                if it:
                    tr.append(it)
        it = night3.hero_item(h, "Hero", None, rng)
        if it:
            hi.append(it)
        if len(tr) > 120 and len(hi) > 20:
            break
    assert tr and hi
    m = night3.fit(tr, maxiter=30)
    m["platt"] = night3._platt([night3.predict({**m, "platt": (1, 0)}, t) for t in hi], [t["won"] for t in hi])
    p = night3.predict(m, hi[0])
    assert 0 <= p <= 1 and len(night3.model_hash(m)) == 16
    db = SimpleNamespace(path=tmp_path / "hander.db")
    monkeypatch.setattr(night3, "store_path", lambda db: tmp_path / "n3.pkl")
    assert night3.acceptance(db)["status"] == "ingen modell"
    night3.save(db, {"model": {**m, "hash": "x"}, "pred": {f"h{i}": {"kind": "syn", "p": 0.5, "won": float(i % 2), "rand": 0.5, "clu": i % 25, "ts": i} for i in range(200)}})
    A = night3.acceptance(db)
    assert A["clusters"] == 25 and A["look"] == 20 and A["status"] in ("pågår", "godkänd", "underkänd")
