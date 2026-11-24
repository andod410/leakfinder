"""Positionsnamn som spelaren ser (2.74).

Alla GG-bord i databasen är 5-max. Tolkningen ger positionerna internt koderna HJ, CO, BTN, SB, BB, där HJ är den
första positionen efter big blind. Spelaren kallar den **UTG** (under the gun). CO (cutoff) är positionen före button.

Koderna i databasen, faktatabellerna och de frysta reglerna ändras INTE – då skulle framåttestets frysta definitioner
(och deras fingeravtryck) inte längre matcha händerna. I stället byts namnet överallt där det visas: webbsidor och
JSON-svar (web.after_request), exporterade filer, sessionsfilen och morgonrapporten. Värden som skickas tillbaka från
sidorna (t.ex. ?pos=UTG eller ett regel-id med UTG) översätts till den interna koden igen (web.before_request).
"""
import re

UI = {"HJ": "UTG"}                       # intern kod -> namn som visas
_TO_UI = [(re.compile(r"\bLJ/HJ\b"), "UTG"), (re.compile(r"\bHJ\b"), "UTG")]
_FROM_UI = re.compile(r"(?<![\w+])UTG(?![\w+])")


def label(code: str) -> str:
    """Namnet på en positionskod som spelaren ser."""
    return UI.get(code, code)


def to_ui(text):
    """Byter interna positionskoder mot spelarens namn i en text (HJ -> UTG). Annat än str lämnas orört."""
    if not isinstance(text, str) or "HJ" not in text:
        return text
    for rx, rep in _TO_UI:
        text = rx.sub(rep, text)
    return text


def from_ui(text):
    """Översätter spelarens namn tillbaka till den interna koden (UTG -> HJ) i värden från sidorna."""
    if not isinstance(text, str) or "UTG" not in text:
        return text
    return _FROM_UI.sub("HJ", text)
