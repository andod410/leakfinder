"""2.83: Topp 3 och prio-listan i $/h, straddle i exporten, metodfilens namn."""
import io
import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from test_v272 import _st  # noqa: E402
from test_v277 import _D  # noqa: E402


def test_cost_shrinks_towards_mean():
    from plo_leak import solverfacit
    D = {"fel": np.array([True] * 4), "act": np.array([2, 2, 1, 2]), "delta": np.array([-10.0, -10.0, -2.0, np.nan]),
         "node": np.array([0, 0, 1, 1])}
    C = solverfacit._costs(D)
    g = C["all"][0]
    assert abs(g - 22 / 3) < 1e-9 and C["all"][1] == 3
    # läge 0: två fel à 10 bb krymps mot snittet med K = 100
    assert abs(C[0][0] - (20 + 100 * g) / 102) < 1e-9 and C[0][1] == 2
    assert g < C[0][0] < 10


def test_prio_categories():
    from plo_leak.solverfacit import _cat
    assert _cat("F", 2) == "open" and _cat("root", 1) == "open" and _cat("F-F-F", 2) is None   # SB-öppning räknas inte
    assert _cat("RC5", 2) == "raise" and _cat("F-RC5", 1) == "call" and _cat("F-F-RC5", 1) == "call"
    assert _cat("F-F-RC5-F", 1) is None and _cat("F-F-F-RC4", 1) is None                    # BB-försvar
    assert _cat("F-F-RC5-F-RC15", 1) is None                                                # syn mot 3-bet efter egen öppning
    assert _cat("RC5-RC17", 1) == "call" and _cat("RC5-RC17", 2) == "raise"
    assert _cat("RC5", 0) is None


def test_training_has_usd_per_hour_and_prio_costs(monkeypatch):
    from plo_leak import solverfacit
    monkeypatch.setattr(solverfacit, "MIN_BESLUT_LAGE", 5)
    st, D = _st(), _D()
    T = solverfacit.training(st, None, days=3650, D=D)
    assert T["hph"] and T["hph"] > 0 and T["bb_usd"] > 0
    for r in T["all"]:
        assert r["usd_h"] is not None and r["usd_h"] >= 0
        exp = r["fel_play"] / T["hands"] * T["hph"] * max(r["cost_bb"], 0) * T["bb_usd"]
        assert abs(r["usd_h"] - exp) < 1e-9
    assert abs(T["total_usd_h"] - sum(r["usd_h"] for r in T["all"])) < 1e-9
    P = solverfacit.prio_costs(st, D, days=3650)
    assert P and all(P[k] >= 0 for k in ("open", "raise", "call")) and P["hph"] > 0


def test_prio_list_has_three_preflop_rows_first():
    from plo_leak.guidelines import PRIO, PRIO_COST
    assert [p[0] for p in PRIO[:3]] == ["🃏"] * 3 and set(PRIO_COST) == {0, 1, 2}
    assert PRIO[3][1].startswith("Check-raisa set")


def test_straddle_flag_in_facts():
    from plo_leak.facts import SCHEMA, FACTS_VERSION
    assert "strad" in SCHEMA["hands"] and FACTS_VERSION >= 21


def test_export_has_straddle_column_and_versioned_method_file(tmp_path):
    from plo_leak import __version__, dataexport
    import inspect
    src = inspect.getsource(dataexport)
    assert '"straddle"' in src and "METOD_2.77" not in src and 'f"METOD_{_ver}.txt"' in src
    assert __version__ >= "2.83"


def test_overview_shows_prio_usd_only_when_gg_closed(monkeypatch, tmp_path):
    import json
    from plo_leak import solverref, solverfacit, web
    from test_v276 import _fake_raw, _client
    monkeypatch.setattr(solverfacit, "MIN_BESLUT_LAGE", 5)
    c, vid, db = _client(monkeypatch, tmp_path, "nej")
    solverref.save_upload(db, json.dumps(_fake_raw()).encode())
    from plo_leak.guidelines import PRIO
    web._view(vid)["C"]["prio"] = PRIO
    html = c.get(f"/v/{vid}/oversikt").get_data(as_text=True)
    assert "Syna mindre mot öppning utanför BB" in html and "/h just nu" in html
    c2, vid2, db2 = _client(monkeypatch, tmp_path / "b", "okänd")
    solverref.save_upload(db2, json.dumps(_fake_raw()).encode())
    web._view(vid2)["C"]["prio"] = PRIO
    html2 = c2.get(f"/v/{vid2}/oversikt").get_data(as_text=True)
    assert "Syna mindre mot öppning utanför BB" in html2 and "/h just nu" not in html2
