# Ändringar i 2.86 (2026-11-21)

**Tolv nya solverlägen (56 totalt).** Hämtade 20 nov kväll (7) och 21 nov fm (5):
- UTG öppnade: CO 3-bettar och BTN 4-bettar · SB 3-bettar och BB synar · BTN 3-bettar och SB synar.
- SB: UTG öppnade, du synade, BB squeezar och UTG synar · UTG öppnar, CO synar och BTN squeezar.
- BB: UTG öppnar och CO 3-bettar · BTN 3-bettar · CO 3-bettar och BTN synar · CO synar och BTN squeezar · CO synar · BTN och SB synar · CO, BTN och SB synar.
- FACTS_VERSION 24, så fakta räknas om en gång vid start.

**All-in EV inkl. rakeback i sessionsgraferna.** Sessionssidan och "valda sessioner tillsammans" har en tredje kurva: all-in EV plus rakeback per hand, räknad som handens rake × procentsatserna från Översikt. Valda sessioner visar också en ruta med beloppet. Sessionsfilen till Claude har en ny rad, "All-in EV inkl. rakeback". Standardvärdena följer nu mätningarna 19–21 nov: GEMs 17,7 %, leaderboard och freeroll 8,8 % på 0.5/1 och 9,5 % på 1/2, totalt cirka 26,5 %. Värden som redan sparats på Översikt gäller före standardvärdena.

**Paus efter stor förlust: 15 min i stället för 2.** Förlorad pott > 175 bb: spela klart pågående händer, sitt ute från alla bord och gå från skärmen i 15 min. Kom tillbaka med hälften så många bord. Kontrollen i efterhand räknar nu med 15 min. Skälet är 21 nov: efter den stora potten steg VPIP från 31 till 41 %, och väntat resultat blev −$549 på 317 händer.

285 tester.
