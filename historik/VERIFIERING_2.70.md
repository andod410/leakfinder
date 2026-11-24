# Verifiering av Leakfinder 2.70

Datum: 13 november 2026. Bas: den uppladdade versionen 2.69.

## Tester

- **113/113 tester godkända** med den medföljande fristående testköraren, inklusive 19 nya regressionstester.
- Pytest-körning av hela sviten före de sista tre tillagda testfallen: 110/110 godkända. De sista testfallen ingår i den slutliga 113-körningen. Inga produktberoenden har lagts till.
- Samtliga **14 analysflikar svarar HTTP 200** på det fullständiga PLO6-underlaget, inklusive Läckor.
- **77 loggade scenarier** i den breda servergenomgången, inklusive förväntade avvisningar och avslutningspost. Analys, handlistor, sortering, filter, tränarscenarier, replayer, sessioner, filer, inställningar, LAN-/origin-skydd, mappbevakning, återstart och tömning av disponibel testdatabas har körts.
- 27 frontendloggkontroller, 21 replayerkontroller och 14 grafkontroller utan registrerade avvikelser. Dessa använder DOM-/canvas-stubbar och är **inte visuella webbläsartester**.
- Riktig lokal webbserver startas/stängs/startas igen: import/version/shutdown fungerar, processerna avslutas med kod 0.
- Mac-startfilens shellsyntax är godkänd. Installation och GUI på Mac/Windows har inte körts.

## Hela handhistoriken

| Kontroll | Resultat |
|---|---:|
| Originalhänder i separat testdatabas | 273,746 |
| Omräknade faktahänder | 273,746 |
| PLO6-händer | 209,539 |
| Största ändring av en hands faktiska USD-resultat | 0.00 |
| PLO6-handers faktiska netto | -29827.75 USD |
| PLO6-handers justerade EV i 2.70 | -41015.03 USD |
| EV i 2.70 | -11.0948 bb/100 |
| EV-differens 2.70 minus 2.69 | -92.38 USD |
| Händer med ändrat EV | 1209 |
| Nytillkomna EV-justeringar | 91 |
| Tidigare justeringar som nu konservativt lämnas som faktiskt utfall | 150 |
| Riversituationer i PLO6-coachens modellunderlag | 49091 |

EV-förändringen är en rättning av mätmetoden, **inte en realiserad vinst eller förlust av uppdateringen**. Faktiska belopp per hand är oförändrade. Skillnaderna beror bland annat på blockerade kort i sidopotter, korrekta låsningstidpunkter och konservativa undantag vid senare actions. Run-it-twice stängs inte av generellt; samma förväntan verifieras med ett uttryckligt test. En full radvis differens finns i `testprotokoll/ev_changes.csv`.

Fakta räknades om för hela databasen på ungefär 73–80 sekunder i testmiljön; efterföljande full analys med sparade resultat tog cirka 6.5 sekunder. Tiderna är miljöberoende.

## Full export

- Bakgrundsjobbet och nedladdningen slutfördes med **209 539 PLO6-händer**; delarnas handantal stämdes av.
- ZIP-storlek: 17,867,272 byte; körtid cirka 379 sekunder.
- **173,950 postflopbeslut** kontrollerades i den faktiska ZIP-filen.
- **50,145 beslut** hade explicit beräknade dragmått.
- Nya kolumner och metodfil finns. Pott efter syn stämdes av mot beslutspott + synbelopp; SPR ska vara ändligt och icke-negativt; nöt-outs ska vara en delmängd av unika träffkort. **Inga avvikelser hittades** i dessa kontroller.
- HH-export i ZIP/text, filtrerad lista, sessionsfil och sessions-ZIP har också körts.

## Viktiga begränsningar

En fjärrwebbläsare kunde inte ansluta till den lokala testservern. Därför är visuell layout, riktiga klickflöden och faktisk PNG-nedladdning inte verifierade i en riktig webbläsare. Server-/malltester och isolerade klientlogiktester anges separat för att inte överdriva täckningen.

Det här är inte en säkerhetscertifiering eller en garanti om optimal pokerstrategi. Showdownselektion, Monte Carlo-felmarginaler preflop, okända motståndarranges och uppskattad speltid finns kvar som metodbegränsningar. Fasta stoppgränser är rutiner att utvärdera framåt, inte bevisat optimala beslut.

## Ändrade filer i förhållande till 2.69

- `.pytest_cache/.gitignore`
- `.pytest_cache/CACHEDIR.TAG`
- `.pytest_cache/README.md`
- `.pytest_cache/v/cache/lastfailed`
- `.pytest_cache/v/cache/nodeids`
- `ANDRINGAR_2.70.md`
- `README.md`
- `plo_leak/__init__.py`
- `plo_leak/board.py`
- `plo_leak/dataexport.py`
- `plo_leak/db.py`
- `plo_leak/ev.py`
- `plo_leak/export.py`
- `plo_leak/facts.py`
- `plo_leak/fatigue.py`
- `plo_leak/guidelines.py`
- `plo_leak/holdout.py`
- `plo_leak/hourly.py`
- `plo_leak/postflop_rows.py`
- `plo_leak/practice.py`
- `plo_leak/report.py`
- `plo_leak/river.py`
- `plo_leak/rivercoach.py`
- `plo_leak/templates/pages/rakeback.html`
- `plo_leak/templates/pages/sessioner.html`
- `plo_leak/templates/pages/trana.html`
- `plo_leak/templates/parts/lackor.html`
- `tests/test_core.py`
- `tests/test_v270.py`
- `tools/run_tests.py`

Patchen `2.69_till_2.70.patch` visar källändringarna. Tre äldre testförväntningar har anpassats till avsiktligt ändrade säkerhetsetiketter och indragna outs-/nötråd; övriga gamla testfall behålls. Originalets råa handimport och faktisk resultatbokföring är oförändrade.
