"""2.88: avbryt-knapp, verklig winrate och rakeback bb/100, vinstkurvor som jämför lika med lika."""
import time
import numpy as np


def test_job_cancel_running_and_waiting():
    from plo_leak.jobs import JobManager
    M = JobManager()
    def slow(job):
        for i in range(500):
            job.set("steg", i, 500)
            time.sleep(0.01)
        return "klar"
    j = M.start("Test", slow)
    time.sleep(0.05)
    j2 = M.start("Test2", slow)            # väntar i kön
    assert M.cancel(j2.id) and M.cancel(j.id)
    for _ in range(300):
        if j.status == "avbruten" and j2.status == "avbruten":
            break
        time.sleep(0.01)
    assert j.status == "avbruten" and j2.status == "avbruten"
    assert j.as_dict()["cancel"] is True
    assert not M.cancel(j.id)              # redan avslutat


def test_cancel_not_swallowed_by_except_exception(tmp_path):
    from plo_leak.jobs import JobManager
    M = JobManager()
    f = tmp_path / "halv.zip"
    def job_fn(job):
        f.write_bytes(b"x")
        job.cleanup.append(str(f))
        while True:
            try:
                job.set("steg")
            except Exception:
                pass
            time.sleep(0.005)
    j = M.start("Test", job_fn)
    time.sleep(0.03)
    M.cancel(j.id)
    for _ in range(300):
        if j.status == "avbruten":
            break
        time.sleep(0.01)
    assert j.status == "avbruten" and not f.exists()


def test_cancel_route_and_ui():
    import plo_leak.web as web
    from plo_leak.jobs import MANAGER
    j = MANAGER.start("Test", lambda job: [job.set("s") or time.sleep(0.01) for _ in range(1000)])
    r = web.app.test_client().post(f"/jobb/{j.id}/avbryt", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.get_json()["ok"]
    from pathlib import Path
    import plo_leak
    T = Path(plo_leak.__file__).parent / "templates"
    assert "Avbryt" in (T / "pages" / "jobb.html").read_text(encoding="utf-8")
    assert "data-cancel" in (T / "app.html").read_text(encoding="utf-8")


def test_apply_rb_like_with_like():
    from plo_leak.report import _chart, apply_rb
    net = np.cumsum([1.0, -2.0, 3.0]); ev = np.cumsum([0.5, -1.0, 1.0])
    ch = _chart({"net": net, "ev": ev}, ts=None)
    assert ch["luck"] == round(float(net[-1] - ev[-1]), 1)
    on = apply_rb(ch, net + 1, ev + 1, True)
    S = {x["k"]: x for x in on["s"]}
    assert S["net_rb"]["on"] and S["ev_rb"]["on"] and not S["net"]["on"] and not S["ev"]["on"]
    assert S["net_rb"]["label"] == "Faktiskt resultat inkl. rakeback"
    off = apply_rb(ch, net + 1, ev + 1, False)
    assert {x["k"] for x in off["s"]} == {"net", "ev"} and all(x["on"] for x in off["s"])


def test_winrate_stats_ci_and_per_stake():
    from plo_leak.rbcurve import winrate_stats
    class FT:
        H = {"stake": np.array([0] * 300 + [1] * 250)}
        @staticmethod
        def label(col, code):
            return {0: "0.5/1", 1: "1/2"}[code]
    rng = np.random.default_rng(1)
    ev = rng.normal(0.05, 10, 550); rb = np.full(550, 0.05); net = ev + rng.normal(0, 3, 550)
    W = winrate_stats(FT, np.arange(550), ev, rb, net)
    assert W["n"] == 550 and abs(W["rb100"] - 5.0) < 1e-9 and W["ev100_rb_ci"] > 0
    assert [x["stake"] for x in W["per_stake"]] == ["0.5/1", "1/2"]
    assert abs(W["luck_bb"] - float(net.sum() - ev.sum())) < 1e-9


def test_kpi_cells_in_templates():
    from pathlib import Path
    import plo_leak
    T = Path(plo_leak.__file__).parent / "templates"
    k = (T / "parts" / "kpis.html").read_text(encoding="utf-8")
    assert "Verklig winrate (all-in EV inkl. rakeback)" in k and "Rakeback bb/100" in k
    s = (T / "pages" / "sessioner.html").read_text(encoding="utf-8")
    assert s.count("Verklig winrate") >= 2
    m = (T / "parts" / "macros.html").read_text(encoding="utf-8")
    assert "Tur i all-ins" in m


def test_version():
    import plo_leak
    assert plo_leak.__version__.startswith("2.8")
