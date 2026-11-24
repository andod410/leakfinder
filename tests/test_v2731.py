"""2.73.1: "Visa urvalet" byter bara urvalet – läckor, regler och modeller räknas inte om. "🔬 Analysera urvalet" kör analysen."""
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent


def _setup(tmp_path):
    from plo_leak.db import HandDB
    db = HandDB(tmp_path / "v.db")
    db.add_paths([HERE / "real" / "gg_plo6_samples.txt"])
    hero = db.detect_hero()
    store = db.facts(hero)
    store.sync(db, workers=1)
    return db, hero, store


def _build(db, hero, store, tmp_path, sel, **kw):
    from plo_leak import analyses
    from plo_leak.pipeline import build
    seen = {}
    orig = analyses.run

    def spy(ctx, progress=None):
        R = orig(ctx, progress)
        seen.update(ctx.timings)
        seen["_skip"] = ctx.skip_models
        return R
    analyses.run = spy
    try:
        C = build(store.load(), hero, db.get_hand, sel, use_db=True, data_sig=kw.pop("sig", store.signature()),
                  cache_dir=tmp_path / "res", as_context=True, **kw)
    finally:
        analyses.run = orig
    return C, seen


def test_view_reuses_stored_models_even_after_new_data(tmp_path):
    from plo_leak.selection import Selection
    db, hero, store = _setup(tmp_path)
    _C, s1 = _build(db, hero, store, tmp_path, Selection())
    assert s1["leaks"][0] == "räknat"
    latest = Selection(latest=20)
    # ny data (annan signatur) – en vanlig analys skulle räkna om modellerna, "Visa urvalet" gör det inte
    C, s2 = _build(db, hero, store, tmp_path, latest, view=True, sig="ny-data")
    assert s2["leaks"][0] == "sparat" and s2["ranges"][0] == "sparat" and not s2["_skip"]
    assert C["quick_info"]["view"] and C["st"].hands == 20
    _C, s3 = _build(db, hero, store, tmp_path, latest, sig="ny-data")
    assert s3["leaks"][0] == "räknat"  # utan view: modellerna räknas om på den nya datan (som förut)


def test_view_without_stored_analysis_skips_models_and_says_so(tmp_path):
    from plo_leak.selection import Selection
    db, hero, store = _setup(tmp_path)
    C, s = _build(db, hero, store, tmp_path, Selection(latest=20), view=True)
    assert s["_skip"] and "leaks" not in s
    assert C["quick_info"] == {"skipped": True, "view": True}
    _C, s2 = _build(db, hero, store, tmp_path, Selection(latest=20), view=True)
    assert s2["_skip"]  # ett visat urval sparar ingen "full analys"


def test_analyse_selection_runs_models_on_the_selection(tmp_path):
    from plo_leak.selection import Selection
    db, hero, store = _setup(tmp_path)
    _build(db, hero, store, tmp_path, Selection())
    _C, s = _build(db, hero, store, tmp_path, Selection(latest=20), model_on_selection=True)
    assert s["leaks"][0] == "räknat" and not s["_skip"]


def test_filter_bar_has_view_as_default_button_and_analyse_button():
    html = (HERE.parent / "plo_leak" / "templates" / "app.html").read_text(encoding="utf-8")
    i_view, i_an = html.index('name="mode" value="visa"'), html.index('name="mode" value="analys"')
    assert i_view < i_an  # Enter i urvalet = första knappen = Visa urvalet
    assert 'name="model_sel"' not in html


def test_form_modes_map_to_spec(monkeypatch, tmp_path):
    import os
    os.environ["PLO_LEAK_DB"] = str(tmp_path / "w.db")
    os.environ["PLO_LEAK_CACHE"] = str(tmp_path / "cache")
    from plo_leak import jobs, web
    seen = []
    monkeypatch.setattr(jobs.MANAGER, "start", lambda title, fn, spec, **k: seen.append(spec) or type("J", (), {"id": "x"})())
    c = web.app.test_client()
    c.post("/analyze", data={"mode": "visa", "latest_on": "1", "latest": "500"})
    c.post("/analyze", data={"mode": "analys", "latest_on": "1", "latest": "500"})
    c.post("/analyze", data={"mode": "analys"})
    c.post("/analyze", data={"mode": "visa", "quick": "1"})
    assert seen[0]["view"] and not seen[0]["model_sel"]
    assert not seen[1]["view"] and seen[1]["model_sel"]
    assert not seen[2]["view"] and not seen[2]["model_sel"]
    assert not seen[3]["view"] and seen[3]["quick"]  # ⚡ Nya händer fungerar som förut
