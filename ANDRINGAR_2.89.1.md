# Ändringar i 2.89.1 (2026-11-27)

1. **Automatisk uppdatering högst en gång per minut – på Översikt och alla andra sidor.**
   - **I programmet:** när den bevakade mappen hittar nya händer startar en automatisk uppdatering bara om den
     förra automatiska uppdateringen startade för minst 60 sekunder sedan. Händer som kommer in under minuten
     tas med i nästa uppdatering (bevakningen försöker igen var 4:e sekund så länge händer saknas i analysen).
   - **På sidorna:** en öppen sida laddar om sig automatiskt tidigast 60 sekunder efter att den laddades. Är en
     nyare analys klar tidigare visas "En nyare analys är klar – sidan uppdateras om N s (högst en gång per minut)".
   - Det du gör själv påverkas inte: "Visa urvalet", "Uppdatera nu" och byte av sida sker direkt.
   - Oförändrat av säkerhetsskäl: sidorna med solverfrekvenser (Solver, Träna) döljs direkt när GG startar.
     Förloppssidan för ett jobb går vidare till rapporten direkt när jobbet är klart.
2. Tester: `tests/test_v2891.py` (minutspärren i programmet och på sidorna). Hela sviten: 323 tester godkända.
