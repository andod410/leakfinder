# Leakfinder 2.79 – ändringar (2026-11-18)

Bygger på 2.78.2. Fokus: hastighet. Alla resultat är desamma som i 2.78.2. Exporten på testdatabasen (36 273 händer) är lika utom tidsstämpeln, och de frysta fingeravtrycken är oförändrade.

## ⚡ Snabbare
| Steg | 2.78.2 | 2.79 |
|---|---|---|
| Översikt (första visning efter analys) | 1,4 s | 0,03 s |
| Solver-sidan (varje gång) | 0,34 s | 0,002 s |
| Sessioner / ett pass / sessionsfil | 0,15 / 0,2–1,1 / 0,2 s | 0,007 / 0,05–0,08 / 0,001 s |
| Analys efter nya händer | 10,5 s | 2,8 s |
| Ny programversion som inte rör analyserna | allt räknas om | återanvänds |
| Fakta, kall | 61 s | 37 s |
| Fakta, omräkning | 44 s | 13 s |
| all-in EV | 8,7 s | 2,1 s |
| Nattkörning v3, prognoser | – | ca 3× snabbare |
| Nattkörning v2 (handberäkning) | 7,95 s | 5,72 s |
| v3-träning (en anpassning) | 91 s, 313 MB | 35 s, 179 MB |

- **Förberäkning i bakgrunden**: efter varje analys räknas de vanligaste urvalen färdigt på lägsta prioritet med alla kärnor utom en, och sparas på disk.
  - Urvalen: alla spel, PLO4/5/6 var för sig, varje nivå (t.ex. 0,5/1), vanliga bord, Rush & Cash och senaste 15 000.
  - Kön stoppas direkt när du själv startar något.
  - Byta urval tar 0,01–0,03 s när det redan är beräknat.
- **Förvärmning när en analys öppnas**: Topp 3, Solver, Resultat, Träna och de tre senaste passen med graf och sessionsfil räknas i förväg.
- **Cache per analys**: varje analys sparas med ett fingeravtryck av sin egen kod. En ny programversion räknar bara om det som faktiskt ändrats.

## 🔄 Automatisk inläsning
- Den bevakade mappen kontrolleras var 4:e sekund, mot tidigare var 10:e.
- Nya händer som kom medan ett jobb pågick tappas inte längre. De läses in vid nästa kontroll.
- Sidan uppdaterar sig själv och byter först när den nya analysen är färdigvärmd.
- Ny ruta: "Bevaka även Hämtade filer".
- Senaste sidan öppnas vid start.

## 🛠 Utvecklingsläge
- Slås på under Importera → Utvecklingsläge. Då kan hela programmet köras medan GG är igång.
- **Solverns frekvenser döljs ändå alltid medan GG körs (RTA).**
- En banner visar att läget är på. Från 1 december 2026 blir den röd: GG förbjuder då tredjepartsprogram.

## 🎯 Deterministiska resultat
Faktatabellen byggs nu i fast satsordning. Tidigare berodde den på i vilken ordning processerna blev klara. Samma databas ger därför exakt samma resultat oavsett antal kärnor.

Den här ändringen gör att fakta byggs om en gång (FACTS_VERSION 17). Det enda som ändras är interna koder i insatsnivåkontrollen och ordningen i några listor. Innehållet är detsamma.

## 2.79.1
- Analysen använde bara en kärna efter faktasteget. Nu räknas framåttestets rader för nya händer i alla kärnor utom en, och river-coachen räknas i en egen process. Båda körs samtidigt med de andra analyserna.
- Testdatabasen gick från 11 till 7 s på 2 kärnor. Med 12 trådar blir vinsten större.
- Resultaten är identiska (exporten lika). River-coachen börjar nu alltid från samma slumpfrö, som en nyss startad körning. Tidigare kunde den ge något olika svar beroende på hur många analyser som körts sedan programmet startade.
- De övriga analyserna körs fortfarande i tur och ordning. De är små var för sig.
