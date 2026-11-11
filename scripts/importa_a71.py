"""Converts the ENTSO-E export "Installed Capacity per Production Unit" (A71, Excel from the
Transparency Platform website) into data/<YYYY-MM>/A71_IT_NORD.csv, the format costruisci_dati.py reads.

    python scripts/importa_a71.py --xlsx GUI_GENERATION_INSTALLED_PERUNIT_202512312300-202612312300.xlsx --mese 2026-10

Download: transparency.entsoe.eu -> Generation -> Installed Capacity per Production Unit,
bidding zone IT-North, year 2026, Export -> XLSX.

Kept as published, one row per production unit, with the entsoe_ prefix:
    entsoe_zona, entsoe_tipo_produzione, entsoe_eic, entsoe_nome,
    entsoe_potenza_inizio_anno (MW), entsoe_localita, entsoe_tensione_kv,
    entsoe_data_esercizio, entsoe_data_dismissione
Dropped, and listed in fonti.json:
    - rows without an EIC code ("NOT_FOUND"): no production type, no capacity at the start of the year;
    - "Current Installed Capacity": the export mixes units in this column (380500 for a 380 MW unit,
      0 for units that are running), so it is not used.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

RADICE = Path(__file__).resolve().parent.parent
DATI = RADICE / "data"
TZ = "Europe/Rome"
NOME = "A71_IT_NORD"

COLONNE = {   # header in the ENTSO-E export -> column in the archive format
    "Production type": "entsoe_tipo_produzione",
    "Code": "entsoe_eic",
    "Name": "entsoe_nome",
    "Installed Capacity at the beginning of the year (MW)": "entsoe_potenza_inizio_anno",
    "Location": "entsoe_localita",
    "Voltage Connection (kV)": "entsoe_tensione_kv",
    "Commissioning Date": "entsoe_data_esercizio",
    "Decommissioning Date": "entsoe_data_dismissione",
}
SCARTATA = "Current Installed Capacity (MW)"


def leggi_export(xlsx: Path) -> tuple[pd.DataFrame, dict]:
    grezzo = pd.read_excel(xlsx, header=None, dtype=str)
    titolo = " ".join(str(v) for v in grezzo.iloc[:3, 0].dropna())
    periodo = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", titolo)
    riga_int = next(i for i in range(len(grezzo)) if grezzo.iloc[i, 0] == "Production type")
    zona = str(grezzo.iloc[riga_int - 1, 0])
    df = grezzo.iloc[riga_int + 1:].copy()
    df.columns = [str(c).strip() for c in grezzo.iloc[riga_int]]
    mancanti = [c for c in COLONNE if c not in df.columns]
    if mancanti:
        raise ValueError(f"{xlsx.name}: columns not found {mancanti}: is this the A71 export?")
    if not zona.endswith("IT-North"):
        raise ValueError(f"{xlsx.name}: bidding zone is {zona!r}, expected BZN|IT-North")
    senza_eic = int((df["Code"] == "NOT_FOUND").sum())
    df = df[df["Code"] != "NOT_FOUND"]
    out = df[list(COLONNE)].rename(columns=COLONNE)
    out["entsoe_potenza_inizio_anno"] = pd.to_numeric(out["entsoe_potenza_inizio_anno"], errors="coerce")
    inizio = pd.Timestamp(pd.to_datetime(periodo.group(1), dayfirst=True)).tz_localize(TZ) if periodo else None
    out.insert(0, "entsoe_zona", zona)
    if inizio is not None:
        out.insert(0, "ts_italia", inizio)
        out.insert(0, "ts_utc", inizio.tz_convert("UTC"))
    info = {"righe_tolte_senza_eic": senza_eic, "periodo": periodo.group(0) if periodo else None,
            "colonne_tolte": [SCARTATA] if SCARTATA in df.columns else []}
    return out.reset_index(drop=True), info


def aggiorna_fonti(cartella: Path, righe: int, info: dict, xlsx: Path) -> None:
    p = cartella / "fonti.json"
    fonti = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"file": []}
    voce = {
        "file": f"{NOME}.csv", "dataset": "A71", "zona": "IT_NORD", "fonte": "ENTSOE",
        "descrizione": "Capacità installata per unità di produzione, inizio anno [MW]",
        "risoluzione": "P1Y", "righe": righe, "righe_attese": None, "completo": True,
        "colonne_tolte": info["colonne_tolte"], "righe_tolte_senza_eic": info["righe_tolte_senza_eic"],
        "versione_archivio": None, "origine": f"export del sito ENTSO-E: {xlsx.name} ({info['periodo']})",
    }
    fonti["file"] = [f for f in fonti.get("file", []) if f.get("file") != voce["file"]] + [voce]
    p.write_text(json.dumps(fonti, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xlsx", required=True, type=Path, help="ENTSO-E A71 export (.xlsx)")
    ap.add_argument("--mese", required=True, help="month folder in data/, YYYY-MM")
    a = ap.parse_args(argv)
    cartella = DATI / a.mese
    if not cartella.is_dir():
        print(f"ERROR: {cartella} not found: export the month first")
        return 1
    try:
        df, info = leggi_export(a.xlsx)
    except (ValueError, StopIteration) as e:
        print(f"ERROR: {e}")
        return 1
    df.to_csv(cartella / f"{NOME}.csv", index=False)
    aggiorna_fonti(cartella, len(df), info, a.xlsx)
    tot = df.groupby("entsoe_tipo_produzione")["entsoe_potenza_inizio_anno"].agg(["count", "sum"])
    print(f"ok {len(df)} units written to data/{a.mese}/{NOME}.csv "
          f"({info['righe_tolte_senza_eic']} rows without EIC dropped)")
    print(tot.to_string(float_format=lambda v: f"{v:,.0f}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
