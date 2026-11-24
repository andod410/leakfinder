# Ändringar i 2.89 (2026-11-23)

1. **Urvalet gäller alltid som det är inställt.** Nivå, datum och "senaste N" kombineras i den ordningen:
   först nivån, sedan datumet, sist de senaste N händerna av det som är kvar. Finns färre än N visas alla efter datumet.
   - Sidan laddar aldrig om sig när en automatisk uppdatering blir klar medan du har ändrat urvalet utan att
     skicka det. I stället visas: "En nyare analys är klar. Ditt ändrade urval behålls …".
   - Urvalet sparas som "senaste urval" så fort du trycker på knappen (förut först när jobbet var klart). En
     automatisk uppdatering som startar under tiden använder alltså ditt nya urval.
   - En automatisk uppdatering som väntar eller kör med det gamla urvalet avbryts när du skickar ett urval.
   - Urvalsraden under rubriken visar hela urvalet, till exempel
     "$0.5/$1 · urval från 2026-11-01 · senaste 15 000 → 15 000 av 17 1xx händer · första hand 2026-11-04 – …".
2. **Dela som bild: alla grafer från Översikt kan väljas.**
   - Linjerna är faktiskt resultat, all-in EV, med och utan showdown, betald rake, faktiskt resultat inkl. rakeback
     och all-in EV inkl. rakeback. Varje linje har en egen kryssruta, och valet sparas.
   - Rakeback räknas med procentsatserna från Översikt.
   - Rutorna överst på bilden: "Utan rakeback" eller "Med rakeback". Med rakeback visas resultat inkl. rakeback,
     all-in EV inkl. rakeback och verklig winrate med rakeback i bb/100.
3. **Nyckeltalsrutorna** (Översikt och Resultat):
   - Nya rutor: "All-in EV inkl. rakeback (pengar)" ($ och bb), "Resultat inkl. rakeback (pengar)" och
     "EV-timlön inkl. rakeback".
   - "⚙ Anpassa rutor": en kryssruta per ruta, samt snabbvalen **Enkel** (verklig winrate, resultat och all-in EV
     inkl. rakeback, händer, timlön) och **Allt**.
   - Valet sparas i programmets inställningar, så att det gäller efter omstart och i alla flikar. Dolda rutor räknas
     fortfarande, så sessionsfilen och exporten är oförändrade.

Tester: 8 nya i test_v289. Provkört på riktiga händer: analys, urval med nivå + datum + senaste N, Översikt,
Resultat, Sessioner, Dela som bild, och att dölja en ruta.
