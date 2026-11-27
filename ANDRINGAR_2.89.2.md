# Ändringar i 2.89.2 (2026-11-27)

1. **Översikt laddades om var 3:e sekund medan GG körde – rättat.**
   - Orsak: Översikt hade alltid markeringen för "sida med solverdata". Medan GG körs (eller när det inte går att
     kontrollera om GG körs) laddas sådana sidor om för att dölja solverfrekvenserna. Eftersom markeringen fanns
     kvar även när Topp 3 redan var dold, laddades sidan om igen var 3:e sekund. Det märktes till exempel när du
     fyllde i antal händer för hand.
   - Nu sätts markeringen bara när solverdata faktiskt kan visas (GG stängt och solverfilen finns), precis som
     på Solver och Träna. Startar GG medan Översikt visar solverdata laddas sidan om en gång, döljer Topp 3:s
     solverdel och slutar sedan ladda om.
   - Minutspärren från 2.89.1 gäller som förut för de automatiska uppdateringarna.
2. Tester: `tests/test_v2892.py` (markeringen med GG igång, "okänd", stängt och utan solverfil). Hela sviten: 326 godkända.
