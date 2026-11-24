"""Kör hela testsviten utan pytest: python tools/run_tests.py  (2.80: huvudvakt, capsys och setenv)."""
import contextlib
import importlib
import inspect
import io
import os
import pathlib
import sys
import tempfile
import traceback

root = pathlib.Path(__file__).resolve().parents[1]


class MonkeyPatch:
    def __init__(self):
        self.items = []
        self.env = []

    def setattr(self, obj, name, value):
        original = inspect.getattr_static(obj, name) if isinstance(obj, type) else getattr(obj, name)
        self.items.append((obj, name, original))
        setattr(obj, name, value)

    def setenv(self, name, value):
        self.env.append((name, os.environ.get(name)))
        os.environ[name] = str(value)

    def delenv(self, name, raising=True):
        self.env.append((name, os.environ.get(name)))
        os.environ.pop(name, None)

    def undo(self):
        for obj, name, value in reversed(self.items):
            setattr(obj, name, value)
        for name, value in reversed(self.env):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class CapSys:
    def __init__(self):
        self.buf = io.StringIO()

    def readouterr(self):
        out = self.buf.getvalue()
        self.buf.seek(0)
        self.buf.truncate()
        return type("R", (), {"out": out, "err": ""})()


def main() -> int:
    sys.path.insert(0, str(root))
    os.environ.setdefault("PLO_CTX_CACHE", "0")
    os.environ.setdefault("PLO_PRECOMPUTE", "0")
    os.environ.setdefault("PLO_ALLOW_NO_ORIGIN", "1")
    failed = total = 0
    for path in sorted((root / "tests").glob("test_*.py")):
        module = importlib.import_module("tests." + path.stem)
        for name in sorted(n for n in dir(module) if n.startswith("test_")):
            f = getattr(module, name)
            if not callable(f):
                continue
            total += 1
            mp = MonkeyPatch()
            cap = CapSys()
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
                kwargs = {}
                for param in inspect.signature(f).parameters:
                    if param == "tmp_path":
                        kwargs[param] = pathlib.Path(td)
                    elif param == "monkeypatch":
                        kwargs[param] = mp
                    elif param == "capsys":
                        kwargs[param] = cap
                # samma som tests/conftest.py: den riktiga solverfilen i privat/ läses aldrig av testerna
                from plo_leak import solverref
                mp.setattr(solverref, "BUNDLED", pathlib.Path(td) / "finns-inte.json")
                mp.setattr(solverref, "BUNDLED_EXTRA", pathlib.Path(td) / "finns-inte-extra.json")
                try:
                    with contextlib.redirect_stdout(cap.buf):
                        f(**kwargs)
                    print("OK   ", path.stem + "." + name)
                except Exception:
                    failed += 1
                    print("FEL  ", path.stem + "." + name)
                    traceback.print_exc()
                finally:
                    mp.undo()
    print(f"{total - failed}/{total} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
