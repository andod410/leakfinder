#!/bin/bash
# Dubbelklicka för att starta PLO-läckfinnaren på Mac.
cd "$(dirname "$0")" || exit 1
echo "Startar PLO-läckfinnaren från mappen: $(pwd)"

# Stäng en äldre läckfinnare som fortfarande kör (bara om sidan på porten är vår egen).
OLD=$(lsof -ti tcp:8765 -sTCP:LISTEN 2>/dev/null)   # 2.81: bara servern som lyssnar, inte en ansluten klient
if [ -n "$OLD" ] && curl -s --max-time 2 http://127.0.0.1:8765/ | grep -q "PLO-läckfinnare"; then
  echo "En äldre version körde redan – stänger den."
  kill $OLD 2>/dev/null
  sleep 2
fi

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 eller nyare saknas."
  echo "Installera från https://www.python.org/downloads/ och dubbelklicka på den här filen igen."
  open "https://www.python.org/downloads/"
  read -r -p "Tryck Enter för att stänga."
  exit 1
fi

# Egen miljö för Mac (.venv-mac), så att samma mapp kan användas på Mac och Windows.
VENV=".venv-mac"
[ -x ".venv/bin/python" ] && VENV=".venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Förbereder första starten (tar någon minut)…"
  "$PY" -m venv "$VENV" || { read -r -p "Kunde inte skapa $VENV. Tryck Enter."; exit 1; }
fi
"$VENV/bin/python" -m pip install -q --disable-pip-version-check -r requirements.txt || { read -r -p "Installationen misslyckades. Tryck Enter."; exit 1; }
"$VENV/bin/python" -m plo_leak.web --open
