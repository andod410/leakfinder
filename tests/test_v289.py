"""2.89: urvalet gäller alltid som det är inställt, alla grafer i Dela som bild, valbara nyckeltalsrutor."""
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
T = Path(__file__).parent.parent / "plo_leak" / "templates"


def _setup(tmp_path):
    from plo_leak.db import HandDB
    db = HandDB(tmp_path / "v.db")
    db.add_paths([HERE / "real" / "gg_plo6_samples.txt"])
    hero = db.detect_hero()
    store = db.facts(hero)
    store.sync(db, workers=1)
    return db, hero, store


def test_stake_date_latest_combine_in_order(tmp_path):
    """Nivå först, sedan datum, sist de senaste N av det som är kvar."""
    from plo_leak.selection import Selection
    db, hero, store = _setup(tmp_path)
    ft = store.load()
    H = ft.H
    stake = ft.label("stake", int(np.bincount(H["stake"]).argmax()))
    days = sorted({str(np.datetime64(int(t), "s"))[:10] for t in H["ts"]})
    d0 = days[len(days) // 2] if len(days) > 1 else days[0]
    base = Selection(stake=stake, date_from=d0).mask(ft)
    k = int(base.sum())
    assert k > 0
    for n in (1, max(1, k // 2), k + 1000):
        m = Selection(stake=stake, date_from=d0, latest=n).mask(ft)
        assert int(m.sum()) == min(n, k)
        assert not (m & ~base).any()                       # bara händer som klarar nivå + datum
        idx = np.flatnonzero(base)
        assert set(np.flatnonzero(m)) == set(idx[-min(n, k):])   # de senaste av dem


def test_filters_report_count_before_latest(tmp_path):
    from plo_leak.pipeline import build
    from plo_leak.selection import Selection
    db, hero, store = _setup(tmp_path)
    ft = store.load()
    C = build(ft, hero, db.get_hand, Selection(latest=5), use_db=True, data_sig=store.signature(),
              cache_dir=tmp_path / "res", as_context=True)
    assert C["filters"]["n_all"] == ft.n and C["st"].hands == 5
    C2 = build(ft, hero, db.get_hand, Selection(), use_db=True, data_sig=store.signature(),
               cache_dir=tmp_path / "res", as_context=True)
    assert C2["filters"]["n_all"] is None


def test_submit_saves_selection_now_and_cancels_stale_auto_update(monkeypatch, tmp_path):
    os.environ["PLO_LEAK_DB"] = str(tmp_path / "w.db")
    os.environ["PLO_LEAK_CACHE"] = str(tmp_path / "cache")
    from plo_leak import jobs, watch, web
    cancelled = []

    class J:
        id = "auto1"
        status = "kör"
    web._AUTO["job"] = "auto1"
    monkeypatch.setattr(jobs.MANAGER, "get", lambda jid: J() if jid == "auto1" else None)
    monkeypatch.setattr(jobs.MANAGER, "cancel", lambda jid: cancelled.append(jid) or True)
    monkeypatch.setattr(jobs.MANAGER, "start", lambda title, fn, spec, **k: type("X", (), {"id": "x"})())
    c = web.app.test_client()
    r = c.post("/analyze", data={"mode": "visa", "stake": "0.5/1", "fran": "2026-11-01", "latest_on": "1",
                                 "latest": "15000"}, headers={"Origin": "http://localhost"})
    assert r.status_code == 302
    last = watch.load_settings(web.get_db()).get("last_spec") or {}
    assert last.get("stake") == "0.5/1" and last.get("fran") == "2026-11-01" and last.get("latest") == 15000
    assert cancelled == ["auto1"]
    web._AUTO["job"] = None


def test_page_never_reloads_over_unsent_selection():
    a = (T / "app.html").read_text(encoding="utf-8")
    assert "if(dirty)" in a and "fb.addEventListener('input'" in a and "sending" in a
    assert "av {{ '{:,}'.format(filters.n_all)" in a          # urvalsraden: N av M händer
    assert "plSending" in (T / "parts" / "charts.js").read_text(encoding="utf-8")


def test_share_has_all_overview_lines_with_rakeback(tmp_path):
    from plo_leak.pipeline import build
    from plo_leak.report import CHART_SERIES
    from plo_leak.selection import Selection
    from plo_leak.share import share_data
    db, hero, store = _setup(tmp_path)
    ft = store.load()
    C = build(ft, hero, db.get_hand, Selection(), use_db=True, data_sig=store.signature(),
              cache_dir=tmp_path / "res", as_context=True)
    D = share_data(C)
    L = D["lines"]
    keys = {k for k, *_ in CHART_SERIES}
    assert {"net", "ev", "sd", "nsd", "rake", "net_rb", "ev_rb"} <= set(L) <= keys
    T_ = D["total"]
    assert abs(L["net"]["b"][-1] - T_["net_bb"]) < 0.2 and abs(L["ev"]["m"][-1] - T_["ev_money"]) < 0.02
    assert abs(L["sd"]["b"][-1] + L["nsd"]["b"][-1] - L["net"]["b"][-1]) < 0.3
    assert abs(L["ev_rb"]["b"][-1] - (L["ev"]["b"][-1] + T_["rb_bb"])) < 0.3
    assert abs(T_["ev_rb_bb"] - (T_["ev_bb"] + T_["rb_bb"])) < 0.2
    d = (T / "pages" / "dela.html").read_text(encoding="utf-8")
    assert "dl-lines" in d and "Med rakeback" in d and "Verklig winrate" in d


def test_kpi_new_cells_and_hide_setting(tmp_path):
    os.environ["PLO_LEAK_DB"] = str(tmp_path / "k.db")
    os.environ["PLO_LEAK_CACHE"] = str(tmp_path / "cache")
    from plo_leak import watch, web
    k = (T / "parts" / "kpis.html").read_text(encoding="utf-8")
    for lab in ("All-in EV inkl. rakeback (pengar)", "Resultat inkl. rakeback (pengar)", "EV-timlön inkl. rakeback",
                "⚙ Anpassa rutor", "data-kpreset=\"enkel\"", "data-kpreset=\"allt\""):
        assert lab in k
    for key in web.KPI_KEYS:
        assert f"'{key}'" in k                              # varje ruta har en nyckel som kan döljas
    c = web.app.test_client()
    r = c.post("/api/kpi", data={"hide": json.dumps(["rake100", "okänd", "bb100_pre"])},
               headers={"Origin": "http://localhost"})
    assert r.status_code == 200 and r.get_json()["hide"] == ["rake100", "bb100_pre"]
    assert watch.load_settings(web.get_db())["kpi_hide"] == ["rake100", "bb100_pre"]


def test_kpi_template_hides_and_computes(tmp_path):
    from plo_leak.report import _template
    from types import SimpleNamespace as N
    st = N(hands=1000, net_bb=50.0, bb100=5.0, ev_bb100=3.0, ev_net_bb=30.0, ev_rake_bb=10.0, rake_paid_bb=60.0,
           net_money=50.0, ev_net_money=30.0)
    rbs = dict(n=1000, ev100_rb=5.0, ev100_rb_ci=4.0, rb100=2.0, pct=27.0, rb_money=20.0, rb_bb=20.0, per_stake=[])
    hourly = {"total": {"hours": 2.0, "hph": 500, "usd_h": 25.0, "ev_usd_h": 15.0}}
    env = _template("app.html").environment
    html = env.get_template("parts/kpis.html").render(st=st, rbs=rbs, hourly=hourly, mixed=True, leaks=[],
                                                      strict=True, kpi_hide=["rake100"], vid="v1")
    assert 'kpi kpi-off" data-k="rake100"' in html
    assert "+50.00" in html                                   # all-in EV inkl. rakeback = 30 + 20 $
    assert "+70.00" in html                                   # resultat inkl. rakeback = 50 + 20 $
    assert "+25.00 $" in html                                 # EV-timlön inkl. rb = 15 + 20/2


def test_version():
    import plo_leak
    assert plo_leak.__version__ == "2.89"
