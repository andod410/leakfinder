"""2.74: positionen HJ (första efter big blind i 5-max) visas och exporteras som UTG – internt oförändrad."""
from types import SimpleNamespace


def test_text_mapping_both_ways():
    from plo_leak.positions import from_ui, label, to_ui
    assert to_ui("HJ: spela bara topp 32 % (öppna när det är foldat till dig)").startswith("UTG:")
    assert to_ui("Släng svaga händer från LJ/HJ") == "Släng svaga händer från UTG"
    assert to_ui("cut|rfi|HJ") == "cut|rfi|UTG" and from_ui("cut|rfi|UTG") == "cut|rfi|HJ"
    assert to_ui("hj_sa_low") == "hj_sa_low" and to_ui(None) is None and to_ui("CO BTN SB BB") == "CO BTN SB BB"
    assert from_ui("UTG") == "HJ" and from_ui("UTG+1") == "UTG+1" and label("HJ") == "UTG" and label("CO") == "CO"


def test_frozen_rule_hash_is_unchanged_by_display_names():
    from plo_leak.forward import rules_hash
    r = {"id": "cut|rfi|HJ", "type": "cutoff", "spot": "rfi", "pos": "HJ", "thr": 1.0, "weights": [1]}
    assert rules_hash({"rules": [r]}) == rules_hash({"rules": [dict(r)]})
    assert r["pos"] == "HJ"  # inget skrivs om i reglerna


def test_web_shows_utg_and_maps_it_back(tmp_path):
    import os
    os.environ.setdefault("PLO_LEAK_DB", str(tmp_path / "w.db"))
    os.environ.setdefault("PLO_LEAK_CACHE", str(tmp_path / "cache"))
    from flask import Response, request
    from plo_leak import web
    with web.app.test_request_context("/hander?pos=UTG&q=forlust", method="POST", data={"focus": "cut|rfi|UTG"}):
        web._positions_in()
        assert request.args.get("pos") == "HJ" and request.args.get("q") == "forlust"
        assert request.form.get("focus") == "cut|rfi|HJ"
        out = web._positions_out(Response("<p>HJ: öppna inte händer med suited ess · CO · BTN</p>", mimetype="text/html"))
        js = web._positions_out(Response('{"pos": "HJ"}', mimetype="application/json"))
        csv = web._positions_out(Response("pos\nHJ", mimetype="text/csv"))
    html = out.get_data(as_text=True)
    assert "UTG: öppna inte" in html and "HJ" not in html
    assert js.get_data(as_text=True) == '{"pos": "UTG"}'
    assert csv.get_data(as_text=True) == "pos\nHJ"  # bara HTML/JSON skrivs om här (filer får namnet när de skrivs)


def test_exported_csv_uses_utg():
    from plo_leak.dataexport import METOD, _csv
    out = _csv([["OM1", "HJ", "HJ: spela bara topp 32 %", 1.5]], ["hand_id", "pos", "rule", "x"]).decode()
    assert "OM1,UTG,UTG: spela bara topp 32 %,1.5" in out
    assert "POSITIONER (2.74)" in METOD
