# Leakfinder 2.74 – ändringar

15 november 2026.

## UTG i stället för HJ
GG:s PLO6 är 5-max: **UTG** (första efter big blind), **CO** (cutoff, före button), **BTN**, **SB**, **BB**. Programmet kallade
UTG för "HJ". Nu står det UTG överallt där du ser positionen:
- alla sidor (tabeller, regler, riktlinjer, handlistan, tränaren, sessioner);
- djupexporten (CSV och JSON), analysfilen till Claude, sessionsfilen och morgonrapporten.

Internt heter positionen fortfarande HJ – i databasen, faktatabellerna och de **frysta reglerna**. Det är med flit: framåttestet
mäter de regler som frystes 13 november, och om koden ändrades skulle de inte längre känna igen sina egna händer (och
fingeravtrycket `919456190dbe31c4` skulle ändras). Väljer du UTG i ett filter översätts det till HJ i bakgrunden.

Inget räknas om – ingen nattkörning eller ny analys behövs. I äldre exporter står positionen som HJ.

## Tester
169/169 med `python tools/run_tests.py` (4 nya i `tests/test_v274.py`).

Tidigare ändringar: `historik/ANDRINGAR_2.73.md` (2.73–2.73.2).
