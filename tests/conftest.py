import os as _os_2783

_os_2783.environ.setdefault("PLO_PRECOMPUTE", "0")  # 2.79: ingen bakgrundskö under testerna (test_v2783 provar den)
_os_2783.environ.setdefault("PLO_CTX_CACHE", "0")   # 2.79: äldre tester spionerar på analyses.run – urvalscachen provas i test_v2783


import pytest as _pytest_277


@_pytest_277.fixture(autouse=True)
def _no_bundled_solver(monkeypatch, tmp_path):
    """2.77.2: testerna ska aldrig läsa den riktiga solverfilen i privat/."""
    from plo_leak import solverref
    monkeypatch.setattr(solverref, "BUNDLED", tmp_path / "finns-inte.json")


@_pytest_277.fixture(autouse=True)
def _no_bundled_extra(monkeypatch, tmp_path):
    from plo_leak import solverref
    monkeypatch.setattr(solverref, "BUNDLED_EXTRA", tmp_path / "finns-inte-extra.json")

_os_2783.environ.setdefault("PLO_ALLOW_NO_ORIGIN", "1")  # 2.81: testklienten skickar ingen Origin-rubrik
