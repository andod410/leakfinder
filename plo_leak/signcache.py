"""2.81: signerade cachefiler (granskningen: lokala cachefiler läses med pickle, som kan köra kod).

Varje cachefil som programmet skriver får en HMAC-SHA256 med en hemlig nyckel som skapas en gång per installation
(~/.plo_leak_cache/.nyckel, bara läsbar för dig). En fil som inte är signerad med nyckeln – t.ex. kopierad från en annan
dator eller planterad – läses aldrig med pickle: den räknas som saknad och byggs om från dina handhistoriker.
Cachemappen får rättigheterna 700 (bara du) på Mac/Linux.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

MAGIC = b"PLOSIG1\n"
_KEY: dict = {}


def _root() -> Path:
    return Path(os.environ.get("PLO_LEAK_CACHE", Path.home() / ".plo_leak_cache"))


def key() -> bytes:
    root = _root()
    k = _KEY.get(str(root))
    if k:
        return k
    p = root / ".nyckel"
    try:
        root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(root, 0o700)
        except OSError:
            pass
        if p.exists():
            k = p.read_bytes()
        if not k or len(k) < 32:
            k = secrets.token_bytes(32)
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(k)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, p)
    except OSError:
        k = k or hashlib.sha256(str(root).encode()).digest()
    _KEY[str(root)] = k
    return k


def sign(data: bytes) -> bytes:
    return MAGIC + hmac.new(key(), data, hashlib.sha256).digest() + data


def verify(blob: bytes) -> bytes | None:
    """Data om signaturen stämmer, annars None."""
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 32:
        return None
    mac, data = blob[len(MAGIC):len(MAGIC) + 32], blob[len(MAGIC) + 32:]
    return data if hmac.compare_digest(mac, hmac.new(key(), data, hashlib.sha256).digest()) else None


def dumps(obj) -> bytes:
    import pickle
    return sign(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


def loads(blob: bytes):
    """Läser en signerad pickle. Osignerad eller fel signatur -> ValueError (anroparen behandlar det som cachemiss)."""
    import pickle
    data = verify(blob)
    if data is None:
        raise ValueError("osignerad eller ändrad cachefil – läses inte")
    return pickle.loads(data)
