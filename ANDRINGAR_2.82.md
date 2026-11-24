# Leakfinder 2.82 – ändringar (2026-11-19)

## 5 nya solverlägen
Hämtade manuellt 19 nov från PLO Mastermind. De ligger i `privat/solver_extra.json` och följer aldrig med i kodpaketet. Lägena är de fem som kostat mest bland dem som saknades.

| Läge | Du sitter | Solvern (fold/syn/höj) | Du (testdatan) | Klara fel |
|---|---|---|---|---|
| UTG öppnar, BTN synar | BB | 71/22/6 | 62/33/5 | 2 av 141 |
| CO öppnar, SB synar | BB | 64/28/8 | 59/34/7 | 2 av 152 |
| CO öppnar, BTN synar | SB | 89/5/6 | 66/27/6 | 18 av 248 |
| UTG öppnar, BTN synar | SB | 90/5/5 | 69/26/5 | 12 av 211 |
| UTG öppnar, CO 3-bettar | BTN | 96/2/2 | 80/18/3 | 9 av 74 |

- Lägena ingår i solverfacit (klara fel och tveksamma), Topp 3, träningsrutan, sessionsfilen och Träna starthänder (🧮). Knapparna heter squeeza eller 4-betta.
- Fakta byggs om en gång (FACTS_VERSION 20).
- Solvern har nu 31 lägen.
