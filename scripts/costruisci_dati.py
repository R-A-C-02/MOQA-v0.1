"""Builds data/moqa_dati.js (read by index.html) from the raw monthly files in data/<YYYY-MM>/.
Northern Italy (NORD).

    python scripts/costruisci_dati.py --mese 2026-10

Input: one CSV per dataset and zone, exactly as stored in the MOQA archive (ts_utc, ts_italia and
raw columns with the gme_ / entsoe_ / tv_ prefix, EUR/MWh and MW):
    GME_MGP_NORD                      MGP price, NORD zone
    A44_FR, A44_CH                    day-ahead prices of France and Switzerland ("neighbours' price")
    A65_IT_NORD                       actual load
    A75_IT_NORD                       actual generation per production type
    A68_IT_NORD                       installed capacity per production type (start of the year)
    A71_IT_NORD                       installed capacity per production unit (start of the year): used when
                                      A68 is missing, and to read the technology of each A80 unit
    A11_<x>-IT_NORD, A11_IT_NORD-<x>  physical flows         (x = CH, FR, AT, SI, IT_CNOR)
    A61_<x>-IT_NORD, A61_IT_NORD-<x>  day-ahead forecast transfer capacity
    A80_IT_NORD                       unavailability of generation units (all versions of the events)
    TV_PSV, TV_EUA                    daily front-month bars (PSV gas, EU carbon)

Output:
    data/<YYYY-MM>/calc_orario.csv    hourly table, every column calculated (calc_ prefix)
    data/moqa_dati.js                 the same table as window.MOQA_REALE for the page, plus the list of
                                      REMIT unavailability events of the month (section 8)

No network access: everything is rebuilt from the CSV files in data/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RADICE = Path(__file__).resolve().parent.parent
DATI = RADICE / "data"
TZ = "Europe/Rome"
ORA = pd.Timedelta(hours=1)
ESTERO = ("CH", "FR", "AT", "SI")                   # foreign borders of NORD; IT_CNOR = Centre-North zone

MUST_RUN = ("biomass", "waste", "geothermal", "other", "other_renewable", "marine", "energy_storage",
            "fossil_oil", "fossil_oil_shale", "fossil_peat", "fossil_coal_derived_gas")
CARBONE = ("fossil_hard_coal", "fossil_brown_coal_lignite")
# Production type -> group. gas, idro and carbone are subtracted from the installed capacity of the
# model; everything else (run-of-river, "Other", biomass...) is shown as "altro" and not subtracted.
GRUPPI_PSR = {"B04": "gas", "B02": "carbone", "B05": "carbone", "B10": "idro", "B12": "idro"}
# A71 names the production type in words: same codes as A80 (ENTSO-E PSR types)
PSR_A71 = {"Biomass": "B01", "Fossil Brown coal/Lignite": "B02", "Fossil Coal-derived gas": "B03",
           "Fossil Gas": "B04", "Fossil Hard coal": "B05", "Fossil Oil": "B06", "Fossil Oil shale": "B07",
           "Fossil Peat": "B08", "Geothermal": "B09", "Hydro Pumped Storage": "B10",
           "Hydro Run-of-river and pondage": "B11", "Hydro Water Reservoir": "B12", "Marine": "B13",
           "Nuclear": "B14", "Other renewable": "B15", "Solar": "B16", "Waste": "B17", "Wind Offshore": "B18",
           "Wind Onshore": "B19", "Other": "B20", "Energy storage": "B25"}
GRUPPI = ("gas", "idro", "carbone", "altro")
FONTI_PSR = {"B01": "Biomassa", "B02": "Lignite", "B03": "Gas da carbone", "B04": "Gas", "B05": "Carbone",
             "B06": "Olio", "B07": "Olio di scisto", "B08": "Torba", "B09": "Geotermico", "B10": "Pompaggio",
             "B11": "Idro fluente", "B12": "Idro a bacino", "B13": "Marino", "B14": "Nucleare",
             "B15": "Altre rinnovabili", "B16": "Solare", "B17": "Rifiuti", "B18": "Eolico offshore",
             "B19": "Eolico onshore", "B20": "Other", "B25": "Accumulo"}
COLONNE = ["carico", "solare", "eolico", "idro_fluente", "altre_mr", "residuo",
           "gas_prod", "idro_bacino_prod", "pompaggio_prod",
           "prezzo_nord", "prezzo_fr", "prezzo_ch", "prezzo_vicini",
           "import_netto", "export_cnor", "cap_import", "cap_export",
           "gas_disp", "idro_disp", "carbone_disp",
           *(f"indisp_{g}" for g in GRUPPI),
           *(f"flusso_{x}" for x in (*ESTERO, "IT_CNOR")), *(f"capimp_{x}" for x in ESTERO)]
DEFAULT_COMBUSTIBILI = {"psv": 70.0, "eua": 85.0, "api2": 124.0, "fx": 1.15}


# ----------------------------------------------------------------------------- reading
def leggi_csv(cartella: Path, nome: str) -> pd.DataFrame | None:
    p = cartella / f"{nome}.csv"
    if not p.is_file():
        return None
    df = pd.read_csv(p, low_memory=False)
    if df.empty:
        return None
    if "ts_utc" in df:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    return df


def oraria(df: pd.DataFrame | None, colonna: str, ore: pd.DatetimeIndex) -> pd.Series:
    """Hourly mean on the UTC grid of the month (15-minute and hourly series alike)."""
    if df is None or colonna not in df:
        return pd.Series(np.nan, index=ore)
    s = df.set_index("ts_utc")[colonna].astype(float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.resample("1h").mean().reindex(ore)


def netto(dentro: pd.Series, fuori: pd.Series) -> pd.Series:
    """into NORD - out of NORD, where at least one side exists (a missing side counts as zero)."""
    out = dentro.fillna(0) - fuori.fillna(0)
    return out.where(dentro.notna() | fuori.notna())


def somma(serie: list[pd.Series]) -> pd.Series:
    return pd.concat(serie, axis=1).sum(axis=1, min_count=1)


# ----------------------------------------------------------------------------- blocks
def produzione(cartella: Path, ore) -> dict[str, pd.Series]:
    df = leggi_csv(cartella, "A75_IT_NORD")
    col = lambda c: oraria(df, f"entsoe_{c}", ore)
    vuota = pd.Series(np.nan, index=ore)
    if df is None:
        return {k: vuota for k in ("solare", "eolico", "idro_fluente", "altre_mr", "gas_prod",
                                   "idro_bacino_prod", "pompaggio_prod")}
    return {
        "solare": col("solar"),
        "eolico": somma([col("wind_onshore"), col("wind_offshore")]),
        "idro_fluente": col("hydro_run_of_river_and_pondage"),
        "altre_mr": somma([col(c) for c in MUST_RUN]),
        "gas_prod": col("fossil_gas"),
        "idro_bacino_prod": col("hydro_water_reservoir"),
        "pompaggio_prod": col("hydro_pumped_storage"),
    }


def unita_a71(cartella: Path) -> pd.DataFrame | None:
    """A71 production units with a known EIC code and production type; adds calc_psr (PSR code)."""
    df = leggi_csv(cartella, "A71_IT_NORD")
    if df is None or "entsoe_eic" not in df:
        return None
    df = df.dropna(subset=["entsoe_eic"]).copy()
    df["calc_psr"] = df["entsoe_tipo_produzione"].map(PSR_A71)
    df["entsoe_potenza_inizio_anno"] = pd.to_numeric(df["entsoe_potenza_inizio_anno"], errors="coerce")
    return df


def installata(cartella: Path, a71: pd.DataFrame | None = None) -> tuple[dict[str, float | None], str | None]:
    """Installed capacity [MW] at the start of the year and its source.

    ENTSO-E A68 (per production type) when present; otherwise the sum of the A71 units (per production
    unit, >= 100 MW: the same perimeter as the A80 unavailability).
    """
    df = leggi_csv(cartella, "A68_IT_NORD")
    if df is not None:
        r = df.sort_values("ts_utc").iloc[-1]
        v = lambda c: float(r[f"entsoe_{c}"]) if f"entsoe_{c}" in r and pd.notna(r[f"entsoe_{c}"]) else 0.0
        return ({"gas": v("fossil_gas") or None,
                 "idro": (v("hydro_water_reservoir") + v("hydro_pumped_storage")) or None,
                 "carbone": sum(v(c) for c in CARBONE)}, "A68")
    if a71 is not None and not a71.empty:
        mw = a71.groupby(a71["calc_psr"].map(GRUPPI_PSR))["entsoe_potenza_inizio_anno"].sum()
        return ({"gas": float(mw.get("gas", 0)) or None, "idro": float(mw.get("idro", 0)) or None,
                 "carbone": float(mw.get("carbone", 0))}, "A71")
    return {"gas": None, "idro": None, "carbone": None}, None


def a80_valide(cartella: Path, a71: pd.DataFrame | None = None) -> pd.DataFrame | None:
    """A80 rows that count: latest revision of each event, cancelled or withdrawn documents (A09, A13) dropped.

    Adds calculated columns: calc_unita (unit name, or the plant EIC when the name is empty),
    calc_indisp_mw = installed (nominalP) - available, never negative, and calc_psr, the production type
    used by the model: the A71 type of the same plant (matched on the EIC code) when A71 is available,
    otherwise the type declared in the A80 message. In the NORD several CCGTs are declared in A80 with
    type B09 (geothermal) or with no type, while A71 lists them as Fossil Gas.
    """
    df = leggi_csv(cartella, "A80_IT_NORD")
    if df is None:
        return None
    ultima = df.groupby("entsoe_mrid")["entsoe_versione"].transform("max")
    df = df[(df["entsoe_versione"] == ultima) & ~df["entsoe_stato_documento"].isin(["A09", "A13"])]
    df = df.dropna(subset=["entsoe_periodo_inizio", "entsoe_periodo_fine", "entsoe_potenza_disponibile"]).copy()
    nome = df["entsoe_unita"] if "entsoe_unita" in df else df["entsoe_impianto"]
    df["calc_unita"] = nome.where(nome.notna() & (nome.astype(str) != ""), df["entsoe_impianto_eic"]).astype(str)
    df["calc_indisp_mw"] = (pd.to_numeric(df["entsoe_potenza_installata"], errors="coerce").fillna(0)
                            - pd.to_numeric(df["entsoe_potenza_disponibile"], errors="coerce")).clip(lower=0)
    df["calc_psr"] = df["entsoe_psr"]
    if a71 is not None and "entsoe_impianto_eic" in df:
        tipo = dict(zip(a71["entsoe_eic"], a71["calc_psr"]))
        df["calc_psr"] = df["entsoe_impianto_eic"].map(tipo).fillna(df["entsoe_psr"])
    df["calc_gruppo"] = df["calc_psr"].map(GRUPPI_PSR).fillna("altro")
    df["calc_a"] = pd.to_datetime(df["entsoe_periodo_inizio"], utc=True)
    df["calc_b"] = pd.to_datetime(df["entsoe_periodo_fine"], utc=True)
    return df


def indisponibilita(df: pd.DataFrame | None, ore) -> dict[str, pd.Series]:
    """Unavailable capacity [MW] per group (gas, idro, carbone, altro), hourly, from the valid A80 rows.

    Time-weighted within the hour. One unit in several events at the same time: the largest value counts.
    """
    n = len(ore)
    out = {g: pd.Series(0.0, index=ore) for g in GRUPPI}
    if df is None or df.empty:
        return out
    ha = ((df["calc_a"] - ore[0]) / ORA).to_numpy(dtype=float).clip(0, n)
    hb = ((df["calc_b"] - ore[0]) / ORA).to_numpy(dtype=float).clip(0, n)
    per_evento: dict[tuple, np.ndarray] = {}
    for key, mw, a, b in zip(zip(df["calc_gruppo"], df["calc_unita"], df["entsoe_mrid"]),
                             df["calc_indisp_mw"].to_numpy(dtype=float), ha, hb):
        if np.isnan(mw) or b <= a:
            continue
        v = per_evento.setdefault(key, np.zeros(n))
        h = np.arange(int(np.floor(a)), int(np.ceil(b)))
        v[h] += mw * (np.minimum(b, h + 1) - np.maximum(a, h))
    per_unita: dict[tuple, np.ndarray] = {}
    for (g, u, _), v in per_evento.items():
        per_unita[(g, u)] = v if (g, u) not in per_unita else np.maximum(per_unita[(g, u)], v)
    for (g, _), v in per_unita.items():
        out[g] = out[g] + v
    return out


def _ora_italiana(v) -> str | None:
    t = pd.to_datetime(v, utc=True, errors="coerce")
    return None if pd.isna(t) else t.tz_convert(TZ).strftime("%Y-%m-%d %H:%M")


def eventi(df: pd.DataFrame | None, ore) -> list[dict]:
    """One entry per (event, unit) unavailable for at least part of the month, largest first.

    periodi: [start, end, MW] in epoch seconds (UTC), clipped to the month, equal neighbours merged:
    the page uses them to list the events active in the loaded hour.
    """
    if df is None or df.empty:
        return []
    t0, t1 = ore[0], ore[-1] + ORA
    out = []
    for (mrid, unita), g in df.groupby(["entsoe_mrid", "calc_unita"], sort=False):
        g = g.sort_values("calc_a")
        dentro = g[(g["calc_b"] > t0) & (g["calc_a"] < t1) & (g["calc_indisp_mw"] > 0)]
        if dentro.empty:
            continue
        periodi: list[list] = []
        for a, b, mw in zip(dentro["calc_a"].clip(lower=t0), dentro["calc_b"].clip(upper=t1), dentro["calc_indisp_mw"]):
            a, b, mw = int(a.timestamp()), int(b.timestamp()), round(float(mw), 1)
            if periodi and periodi[-1][1] == a and periodi[-1][2] == mw:
                periodi[-1][1] = b
            else:
                periodi.append([a, b, mw])
        r = g.iloc[0]
        cella = lambda c: (None if c not in g or pd.isna(r[c]) or str(r[c]) == "" else str(r[c]))
        inizio = g["entsoe_inizio"].min() if "entsoe_inizio" in g else g["calc_a"].min()
        fine = g["entsoe_fine"].max() if "entsoe_fine" in g else g["calc_b"].max()
        causa = cella("entsoe_causa_testo")
        psr, psr_a80 = cella("calc_psr"), cella("entsoe_psr")
        out.append({
            "unita": unita,
            "psr": psr,
            "fonte": FONTI_PSR.get(psr or "", psr or "—"),
            "psr_a80": psr_a80,                                   # type as declared in the A80 message
            "fonte_a80": FONTI_PSR.get(psr_a80 or "", psr_a80 or "—"),
            "gruppo": r["calc_gruppo"],
            "tipo": cella("entsoe_tipo_nome"),
            "installata": None if pd.isna(pd.to_numeric(r["entsoe_potenza_installata"], errors="coerce"))
                          else round(float(r["entsoe_potenza_installata"]), 1),
            "mw_max": round(float(dentro["calc_indisp_mw"].max()), 1),
            "inizio": _ora_italiana(inizio),
            "fine": _ora_italiana(fine),
            "pubblicato": _ora_italiana(g["entsoe_pubblicazione"].max()) if "entsoe_pubblicazione" in g else None,
            "versione": int(r["entsoe_versione"]),
            "causa": None if causa is None else (causa if len(causa) <= 140 else causa[:139] + "…"),
            "periodi": periodi[:500],
        })
    out.sort(key=lambda e: (-e["mw_max"], e["unita"]))
    return out


def combustibili(cartella: Path) -> dict:
    giornalieri: dict[str, dict] = {}
    for nome, chiave in (("TV_PSV", "psv"), ("TV_EUA", "eua")):
        df = leggi_csv(cartella, nome)
        if df is None or "tv_close" not in df:
            continue
        giorni = pd.to_datetime(df["ts_italia"].astype(str).str[:10])
        for g, v in zip(giorni.dt.strftime("%Y-%m-%d"), df["tv_close"]):
            if pd.notna(v):
                giornalieri.setdefault(g, {})[chiave] = round(float(v), 4)
    default = dict(DEFAULT_COMBUSTIBILI)
    for chiave in ("psv", "eua"):
        ultimi = [giornalieri[g][chiave] for g in sorted(giornalieri) if chiave in giornalieri[g]]
        if ultimi:
            default[chiave] = ultimi[-1]
    return {"default": default, "giornalieri": dict(sorted(giornalieri.items()))}


# ----------------------------------------------------------------------------- main
def costruisci(mese: str, dati: Path = DATI) -> dict:
    cartella = dati / mese
    if not cartella.is_dir():
        raise FileNotFoundError(f"{cartella} not found: export the month first")
    ini = pd.Timestamp(f"{mese}-01").tz_localize(TZ)
    fin = ini + pd.offsets.MonthBegin(1)
    ore = pd.date_range(ini.tz_convert("UTC"), fin.tz_convert("UTC"), freq="1h", inclusive="left")

    t: dict[str, pd.Series] = {}
    t["prezzo_nord"] = oraria(leggi_csv(cartella, "GME_MGP_NORD"), "gme_prezzo", ore)
    if t["prezzo_nord"].isna().all():
        raise ValueError(f"{cartella}: GME_MGP_NORD.csv missing or empty")
    t["prezzo_fr"] = oraria(leggi_csv(cartella, "A44_FR"), "entsoe_prezzo", ore)
    t["prezzo_ch"] = oraria(leggi_csv(cartella, "A44_CH"), "entsoe_prezzo", ore)
    t["prezzo_vicini"] = pd.concat([t["prezzo_fr"], t["prezzo_ch"]], axis=1).mean(axis=1)
    t["carico"] = oraria(leggi_csv(cartella, "A65_IT_NORD"), "entsoe_carico", ore)
    t.update(produzione(cartella, ore))
    t["residuo"] = t["carico"] - t["solare"].fillna(0) - t["eolico"].fillna(0)

    for x in (*ESTERO, "IT_CNOR"):
        t[f"flusso_{x}"] = netto(oraria(leggi_csv(cartella, f"A11_{x}-IT_NORD"), "entsoe_flusso_fisico", ore),
                                 oraria(leggi_csv(cartella, f"A11_IT_NORD-{x}"), "entsoe_flusso_fisico", ore))
    for x in ESTERO:
        t[f"capimp_{x}"] = oraria(leggi_csv(cartella, f"A61_{x}-IT_NORD"), "entsoe_capacita_prevista_da", ore)
    t["import_netto"] = somma([t[f"flusso_{x}"] for x in ESTERO])
    t["export_cnor"] = -t["flusso_IT_CNOR"]
    t["cap_import"] = somma([t[f"capimp_{x}"] for x in ESTERO])
    t["cap_export"] = somma([oraria(leggi_csv(cartella, f"A61_IT_NORD-{x}"), "entsoe_capacita_prevista_da", ore)
                            for x in ESTERO])

    a71 = unita_a71(cartella)
    a80 = a80_valide(cartella, a71)
    (inst, fonte_inst), indisp = installata(cartella, a71), indisponibilita(a80, ore)
    for g in ("gas", "idro", "carbone"):
        t[f"{g}_disp"] = (inst[g] - indisp[g]).clip(lower=0) if inst[g] is not None else pd.Series(np.nan, index=ore)
    for g in GRUPPI:
        t[f"indisp_{g}"] = indisp[g] if a80 is not None else pd.Series(np.nan, index=ore)

    tab = pd.DataFrame({c: t[c] for c in COLONNE}, index=ore)
    tab.index = tab.index.tz_convert(TZ)
    tab = tab.dropna(how="all")
    tab.add_prefix("calc_").to_csv(cartella / "calc_orario.csv", index_label="ts_italia", float_format="%.3f")

    prezzi = {"prezzo_nord", "prezzo_fr", "prezzo_ch", "prezzo_vicini"}
    gw = tab.copy()
    for c in COLONNE:
        if c not in prezzi:
            gw[c] = gw[c] / 1000                        # MW -> GW for the page
    righe = [[ts.strftime("%Y-%m-%d"), int(ts.hour)] +
             [None if pd.isna(r[c]) else round(float(r[c]), 2 if c in prezzi else 3) for c in COLONNE]
             for ts, r in gw.iterrows()]
    comb = combustibili(cartella)
    payload = {
        "generato": pd.Timestamp.now(tz=TZ).strftime("%Y-%m-%d %H:%M"),
        "mese": mese,
        "zona": "NORD",
        "fonte": "GME (MGP) ed ENTSO-E Transparency Platform",
        "fonte_gas": {"A68": "capacità installata ENTSO-E A68 meno le indisponibilità REMIT A80",
                      "A71": "capacità installata a inizio anno delle unità ENTSO-E A71 meno le indisponibilità REMIT A80",
                      }.get(fonte_inst, "valore del pannello (capacità installata non disponibile)")
                     if inst["gas"] is not None else "valore del pannello (capacità installata non disponibile)",
        "fonte_installata": fonte_inst,
        "tecnologia_fermate": "A71 (stesso EIC)" if a71 is not None else "dichiarata nel messaggio A80",
        "fonte_combustibili": ("PSV ed EUA: chiusure giornaliere del front-month (TradingView)"
                               if comb["giornalieri"] else "PSV ed EUA: valori predefiniti"),
        "installata_gw": {k: (None if v is None else round(v / 1000, 2)) for k, v in inst.items()},
        "colonne": ["giorno", "ora"] + COLONNE,
        "righe": righe,
        "ore_utc": [int(ts.timestamp()) for ts in gw.index],     # start of each row, epoch seconds
        "combustibili": comb,
        "eventi": eventi(a80, ore) if a80 is not None else None,  # None: A80 file missing
    }
    js = ("/* generated by scripts/costruisci_dati.py from data/" + mese + "/ - do not edit by hand */\n"
          "window.MOQA_REALE = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n")
    (dati / "moqa_dati.js").write_text(js, encoding="utf-8")
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mese", required=True, help="month to build, YYYY-MM")
    a = ap.parse_args(argv)
    try:
        p = costruisci(a.mese)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}")
        return 1
    i = {c: k for k, c in enumerate(p["colonne"])}
    vuote = [c for c in p["colonne"][2:] if all(r[i[c]] is None for r in p["righe"])]
    print(f"ok {len(p['righe'])} hours, from {p['righe'][0][0]} to {p['righe'][-1][0]}")
    print(f"ok gas available: {p['fonte_gas']}; fuels: {len(p['combustibili']['giornalieri'])} days")
    ev = p["eventi"]
    if ev is None:
        print("REMIT: A80_IT_NORD.csv missing, section 8 stays empty")
    else:
        altro = [e for e in ev if e["gruppo"] == "altro"]
        riclassificati = [e for e in ev if e["psr"] != e["psr_a80"]]
        print(f"ok REMIT: {len(ev)} unavailability events in the month, {len(altro)} with a type the model "
              f"does not subtract (shown as 'altro'); technology from {p['tecnologia_fermate']}, "
              f"{len(riclassificati)} events with a type different from the one declared in A80")
    if vuote:
        print("empty columns (file missing in data/" + a.mese + "): " + ", ".join(vuote))
    print("Written data/moqa_dati.js and data/" + a.mese + "/calc_orario.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
