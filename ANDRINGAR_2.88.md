# Ändringar i 2.88 (2026-11-23)

1. **Avbryt-knapp på alla tunga jobb** – analys, djupanalys, zip för sessioner, export och nattberäkning.
   Knappen finns i jobbraden överst ("⏹ Avbryt") och på förloppssidan. Jobbet stannar vid nästa förloppssteg
   (oftast inom några sekunder); ett jobb i kö avbryts direkt. Halvfärdiga exportfiler tas bort. Avbrottet går inte
   att svälja av felhantering i jobben (BaseException).
2. **Verklig winrate och rakeback som egna datacells överst** (Översikt, Resultat, sessionsvyn, vyn för flera sessioner,
   sessionsfilen): "Verklig winrate (all-in EV inkl. rakeback)" i bb/100 med 95 %-intervall och antal händer, och
   "Rakeback bb/100" med procent av raken och dollar. Under nyckeltalen: verklig winrate per nivå med intervall.
3. **Vinstkurvorna jämför lika med lika** (alla grafer: Översikt, Resultat & graf, session, flera sessioner):
   - ny linje "Faktiskt resultat inkl. rakeback",
   - knappen "Rakeback i graferna (alla linjer)": PÅ = linjerna med rakeback visas och linjerna utan rakeback är
     avslagna (kan slås på); AV = inga rakeback-linjer,
   - raden "Tur i all-ins: ±X" under varje graf (faktiskt resultat − all-in EV).
4. All-in EV oförändrad: standarddefinitionen (alla pengar insatta, inga beslut kvar). Ingen "nästan all-in".

Tester: 312/312 (7 nya i test_v288). Provkört från början till slut på riktiga händer (analys, Översikt, Resultat,
session, flera sessioner, sessionsfil, rakeback PÅ/AV).
