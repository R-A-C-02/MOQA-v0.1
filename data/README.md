# data/

- `2026-10/` — raw monthly files for the Northern Italy (NORD) zone (GME, ENTSO-E, TradingView), one per dataset and zone, as published. `fonti.json` lists versions and row counts.
- `2026-10/calc_orario.csv` — hourly table calculated from the raw files (`calc_` columns).
- `moqa_dati.js` — the same table in the format `index.html` reads.

Rebuild with `python scripts/costruisci_dati.py --mese 2026-10`. Sources and units: see the main [README](../README.md#data).
