# Ändringar i 2.84 (2026-11-19)

**Fem nya solverlägen (36 totalt).** Hämtade manuellt 19 nov; de fem lägen utan solver där du förlorat mest mot fold (247k händer):

| Läge | Du F/S/H | Solvern F/S/H |
|---|---|---|
| SB: UTG öppnar, CO 3-bettar | 82/15/3 | 96/1/3 |
| SB: CO öppnar, BTN 3-bettar | 84/14/3 | 97/1/3 |
| BB: UTG öppnar, CO och BTN synar | 50/46/4 | 79/15/6 |
| BTN öppnade, SB synar, BB squeezar | 3/93/4 | 60/34/6 |
| CO öppnade, SB synar, BB squeezar | 8/87/5 | 58/35/7 |

- Lägena finns i Solver & träning, Topp 3 ($/h) och prio-listan (kallsyn av 3-bet räknas till "syna mindre", 4-bet mot squeeze till 3-bet-raden; syn mot squeeze efter egen öppning och BB-försvar räknas inte).
- Solverfilen `privat/solver_extra.json` har 22 extralägen. FACTS_VERSION 22 – fakta räknas om en gång vid start.
- Metodfilens rubrik följer programversionen automatiskt.
- 276 tester.
