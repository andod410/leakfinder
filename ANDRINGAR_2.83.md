# Ändringar i 2.83 (2026-11-19)

**Fokus: timlön.** Topp 3, träningsrutan och prio-listan mäter nu vad felen kostar i $/h med din nuvarande felnivå.

- **Topp 3 och Träna i $/h.** Lägena rangordnas efter $/h = klara fel per 100 händer (senaste 7 dagarna) × kostnad per fel (hela urvalet, krympt mot snittet) × dina händer per timme × bb i $. Tidigare: flest fel per 100 händer, vilket alltid lyfte öppningarna och dolde dyra 3-bets och syner. Felfoldar ingår inte (okänd kostnad).
- **Ny prio-lista:** tre preflop-punkter överst med $/h just nu (senaste 30 dagarna), ordnade efter $/h 19 nov:
  1. Syna mindre mot öppning utanför BB (SB nästan aldrig, CO/BTN hälften så ofta) – ≈ $6,5/h
  2. Öppna tightare från UTG och CO (par 99–22 / två par ≤ 99 utan suited ess, högt par eller rundown: fold) – ≈ $5,9/h
  3. 3-betta inte ett par JJ–44 med bara suited ess – ≈ $2,6/h
  Därefter set check-raise, river folda mer, river-bluff-testet, paus.
- **Djupexporten:** ny kolumn `straddle` i hands.csv (straddle-händer finns inte i solvern; 11 242 st i din databas). Metodfilen heter efter versionen (METOD_2.83.txt).
- FACTS_VERSION 21 (straddle per hand) – fakta räknas om en gång vid start (≈ 1 min för 247k händer).
- 274 tester.

Obs: den förregistrerade träningsmätningen (välj lägen på urvalsveckan, mät veckorna efter) är oförändrad i upplägg; från 2.83 väljs lägena på $/h.
