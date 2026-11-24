# Leakfinder 2.72 – ändringar

14 november 2026. Mål: **maximera timlönen**. Omfattning enligt beslutet 2026-11-14 (projektloggen, efter den
oberoende granskningen av antagandena).

## Start
Packa upp i en egen mapp och starta med Mac- eller Windows-filen. Fakta räknas om automatiskt första gången (ny tabell för
betstorlek, några minuter). Originalhänderna och de frysta reglerna (13 nov) behålls.

## 1. 🌙 Nattberäkning v2 – hypotes tills den klarat acceptanstestet
- **Range från poolens frekvenser per linje** i stället för visade händer: gata × vad han mötte (ingen bet / betstorlek) ×
  position × nivå, räknat på händer före frysdatumet och hopslaget när underlaget är tunt (< 300 beslut). Bet/höjning =
  starkaste bandet (med bluffandel λ från botten), syn = bandet under, check = resten – kedjat gata för gata.
- **Ankare:** λ väljs en gång (0 / 0,1 / 0,2 / 0,3) så att all-ins före frysdatumet förutsägs bäst, och låses sedan.
- **Konvergensstyrd Monte Carlo:** equity räknas tills medelfelet ≤ 0,5 procentenheter.
- **Turjusterat EV per hand:** pott × equityändring vid varje nytt kort i heads-up-potter (förenklad AIVAT).
- **Acceptans (förregistrerad, händer efter 13 nov, klustrat per pass):** lägre fel än v1 mot faktisk all-in-equity,
  bättre fold-prognos för dina river-bets än poolens totala fold-andel, och turmedel ≈ 0. Klarar den inte → används inte.
  Status och siffror står på Exportera-sidan och i morgonrapporten.

## 2. 🎚 Betstorlek (ny sida under Spel)
- Hur stor andel av dina bets som är extrema (< 45 % eller > 85 % av potten) jämfört med poolen, per gata.
- Poolens fold/höjning per storlek heads-up mot break-even för en ren bluff **med GG:s rake** (5 %, nivåns tak uppskattat
  ur dina händer).
- Polariseringsmatris: dina bets per handgrupp × storlek med resultat i andel av potten.

## 3. 🎲 River-bluff-testet (randomiserat)
- Regel vid bordet från 14 nov: heads-up i position, det checkas till dig och du har luft → **sekundvisaren jämn = betta
  pott, udda = checka**. Programmet visar inget under spel.
- Översikten räknar lägen, din bet-andel (ska vara ~50 %), fold-andelen mot pott-bets och bet minus check.
- **Avbryt** om fold < 62 % efter ~300 lägen (eller tidigare om hela intervallet ligger under). Klart vid 500 lägen.

## 4. Regler och texter
- **Stoppregel:** 2 h (beteenderegel – EV-effekten inom samma pass är inte visad), −500 bb (bankrulleskydd), 2 min paus efter
  förlorad pott > 175 bb (räknas i efterhand, ungefärligt). Ersätter −150 bb i prio-listan, sessionsvyn och sessionsfilen.
- **Morgon/vila** märks som hypotes (se punkt 6), inte som löfte.
- **Rundowns utan suited ess:** 3-bet-regelns text säger "syna i stället"; sessionsfilen markerar 3-bets med dem (🧪 hypotes).
- **Lägre par (JJ–22) utan suited ess mot 4-bet: folda** (🧪 hypotes i sessionsfilen).
- **#11 förregistrerad:** gränsen 16 % för kåk är låst och prövas bara framåt.
- **13+ nöt-outs-jam är struken** (finns inte i programmet).
- **🔒 Framåttest av postflop-riktlinjerna:** varje riktlinje är situation + rekommenderad handling och mäts bara på händer
  efter frysdatum (följde du den, och hur gick det jämfört med när du inte följde). Observationellt – "håller framåt" är
  riktning, inte kausalt bevis.

## 5. Drift: schemalagd nattkörning
- Knapp på Exportera: **⏰ Schemalägg varje natt** (Schemaläggaren på Windows, launchd på Mac; standard 03:30–07:00).
- Varje körning: GG-vakt → säkerhetskopia av databasen (3 senaste) → nya händer → fakta → nattberäkning v2 → acceptanstest
  → **körningskvitto** (JSON) och **morgonrapport** (liten markdown-fil att läsa eller ladda upp till Claude).
- Kommandorad: `python -m plo_leak.nightly` (`--schemalagg 03:30`, `--ta-bort-schema`).
- Schemat pekar på den här versionens mapp – schemalägg igen när du installerar nästa version.

## 6. Fyrfärgslek och vila
- Sessionsfilen skriver kort i fyrfärg: K🔷 Q♠️ J☘️ 4☘️ 4♠️ 2♥️ (programmet var redan fyrfärgat).
- Sessionsvyn, sessionslistan, sessionsfilen och morgonrapporten visar 🌅 morgonpass (start 06–12), 😴 utvilad
  (≥ 8 h sedan förra passet) / ⚠ kort vila och hur länge sedan förra passet.

## Medvetet inte byggt
- Preflop-equitytabeller på GPU, egen solver och riverdrill med eget facit (strukna 14 nov – ersätts av import av
  PLO6-solverlösningar i 2.73).
- Motståndarprofiler per spelare (avstått), rakeback i timlönen (senare).

## Tester
Se `python tools/run_tests.py` – alla tidigare tester plus `tests/test_v272.py` (nattberäkning v2 inklusive en körning på en
liten databas, betstorlek, river-bluff-testet, framåttest postflop, stoppregel, hypoteser, vila/morgon, fyrfärg, backup,
kvitto och morgonrapport).

## 2.72.1 (14 nov, rättning)
- **Pågående jobb syns på alla sidor.** Djupanalys, export, nattberäkning och inläsning visas överst med förlopp och knappen
  "Visa förloppet" – även när du bytt sida och kommer tillbaka.
- **Samma jobb startas inte två gånger.** Trycker du på Djupanalys (eller export/nattkörning) medan ett sådant jobb redan
  pågår eller står i kö, kommer du till det pågående jobbet i stället för att ett nytt köas.

## 2.72.2 (14 nov, dokumentation)
* Ny fil `PROGRAMBESKRIVNING.md`: arkitektur, dataflöde, alla analyser med formler och konstanter, statistikmetoder, nattberäkning v1/v2 med acceptanstest, kända begränsningar och 12 frågor till en extern granskare. Ingen kodändring utöver versionsnumret.
