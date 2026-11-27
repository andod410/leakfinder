"""2.89.2: Översikt laddades om var 3:e sekund medan GG körde (solvermarkeringen fanns alltid)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_overview_marker_only_when_solver_data_shown(monkeypatch, tmp_path):
    from plo_leak import solverref, solverfacit, web
    from test_v276 import _fake_raw, _client
    monkeypatch.setattr(solverfacit, "MIN_BESLUT_LAGE", 5)
    for gg, want in (("ja", False), ("okänd", False), ("nej", True)):
        (tmp_path / gg).mkdir()
        c, vid, db = _client(monkeypatch, tmp_path / gg, gg)
        solverref.save_upload(db, json.dumps(_fake_raw()).encode())
        html = c.get(f"/v/{vid}/oversikt").get_data(as_text=True)
        assert ("<span data-solver-page" in html) is want, gg


def test_overview_without_solver_file_has_no_marker(monkeypatch, tmp_path):
    from test_v276 import _client
    c, vid, db = _client(monkeypatch, tmp_path, "nej")
    html = c.get(f"/v/{vid}/oversikt").get_data(as_text=True)
    assert "<span data-solver-page" not in html


def test_version():
    import plo_leak
    assert plo_leak.__version__ == "2.89.2"
