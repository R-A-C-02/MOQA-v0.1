"""Tests for scripts/costruisci_dati.py and for the content of data/.  Run: python -m pytest -q"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "scripts"))
import costruisci_dati as cd  # noqa: E402

TZ = "Europe/Rome"
INI, FIN = pd.Timestamp("2026-10-01", tz=TZ), pd.Timestamp("2026-11-01", tz=TZ)


def griglia(freq="15min"):
    ts = pd.date_range(INI.tz_convert("UTC"), FIN.tz_convert("UTC"), freq=freq, inclusive="left")
    return pd.DataFrame({"ts_utc": ts, "ts_italia": ts.tz_convert(TZ)})


def scrivi(cartella, nome, df):
    df.to_csv(cartella / f"{nome}.csv", index=False)


def serie(cartella, nome, colonna, valore, freq="15min"):
    df = griglia(freq)
    df[colonna] = valore
    scrivi(cartella, nome, df)


def riga_a80(mrid, versione, stato, psr, unita, inst, inizio, fine, disp):
    return dict(entsoe_mrid=mrid, entsoe_versione=versione, entsoe_stato_documento=stato, entsoe_psr=psr,
                entsoe_unita=unita, entsoe_impianto=unita, entsoe_impianto_eic="EIC-" + unita,
                entsoe_potenza_installata=inst, entsoe_periodo_inizio=inizio, entsoe_periodo_fine=fine,
                entsoe_potenza_disponibile=disp)


@pytest.fixture
def mese(tmp_path):
    """A synthetic October 2026 in the archive format, with known answers."""
    c = tmp_path / "2026-10"
    c.mkdir()
    df = griglia()
    df["gme_prezzo"] = [100.0, 104.0, 108.0, 112.0] * (len(df) // 4)                  # hourly mean = 106
    scrivi(c, "GME_MGP_NORD", df)
    serie(c, "A44_FR", "entsoe_prezzo", 90.0)
    serie(c, "A44_CH", "entsoe_prezzo", 110.0, "1h")
    serie(c, "A65_IT_NORD", "entsoe_carico", 20000.0)
    df = griglia()
    df["entsoe_fossil_gas"], df["entsoe_solar"], df["entsoe_wind_onshore"] = 6000.0, 3000.0, 100.0
    df["entsoe_hydro_run_of_river_and_pondage"], df["entsoe_hydro_water_reservoir"] = 2500.0, 1500.0
    df["entsoe_biomass"], df["entsoe_geothermal"], df["entsoe_waste"] = 700.0, 300.0, 200.0   # must-run
    scrivi(c, "A75_IT_NORD", df)
    t = pd.Timestamp("2026-01-01", tz=TZ)
    scrivi(c, "A68_IT_NORD", pd.DataFrame([{"ts_utc": t.tz_convert("UTC"), "ts_italia": t, "entsoe_fossil_gas": 21000.0,
                                            "entsoe_hydro_water_reservoir": 7000.0, "entsoe_hydro_pumped_storage": 3500.0,
                                            "entsoe_fossil_hard_coal": 0.0}]))
    serie(c, "A11_CH-IT_NORD", "entsoe_flusso_fisico", 3500.0, "1h")
    serie(c, "A11_IT_NORD-CH", "entsoe_flusso_fisico", 500.0, "1h")
    serie(c, "A11_FR-IT_NORD", "entsoe_flusso_fisico", 2000.0)
    serie(c, "A11_IT_NORD-IT_CNOR", "entsoe_flusso_fisico", 2500.0)                     # export only
    serie(c, "A61_CH-IT_NORD", "entsoe_capacita_prevista_da", 4000.0, "1h")
    serie(c, "A61_FR-IT_NORD", "entsoe_capacita_prevista_da", 3000.0, "1h")
    serie(c, "A61_IT_NORD-CH", "entsoe_capacita_prevista_da", 1800.0, "1h")
    scrivi(c, "A80_IT_NORD", pd.DataFrame([
        riga_a80("e1", 1, "A05", "B04", "CCGT A", 400, "2026-10-01T00:00Z", "2026-10-03T00:00Z", 0.0),
        riga_a80("e1", 2, "A05", "B04", "CCGT A", 400, "2026-10-02T00:00Z", "2026-10-03T00:00Z", 0.0),
        riga_a80("e2", 1, "A09", "B04", "CCGT B", 800, "2026-10-01T00:00Z", "2026-10-31T00:00Z", 0.0),
        riga_a80("e3", 1, "A05", "B12", "IDRO C", 250, "2026-10-02T00:00Z", "2026-10-02T00:30Z", 50.0),
        riga_a80("e4", 1, "A05", "B04", "CCGT A", 400, "2026-10-02T00:00Z", "2026-10-02T06:00Z", 200.0),
        riga_a80("e5", 1, "A05", "B20", "CCGT OTHER", 760, "2026-09-20T00:00Z", "2026-10-05T00:00Z", 0.0),
    ]))
    giorni = pd.bdate_range("2026-10-01", "2026-10-30").tz_localize(TZ)
    for nome, v in (("TV_PSV", 70.0), ("TV_EUA", 85.0)):
        scrivi(c, nome, pd.DataFrame({"ts_utc": giorni.tz_convert("UTC"), "ts_italia": giorni, "tv_close": v}))
    return tmp_path


def tabella(payload):
    df = pd.DataFrame(payload["righe"], columns=payload["colonne"])
    df["n"] = df.groupby(["giorno", "ora"]).cumcount()          # 25/10: the 02:00 hour appears twice
    return df.set_index(["giorno", "ora", "n"])


def test_un_record_per_ora_del_mese(mese):
    p = cd.costruisci("2026-10", mese)
    assert len(p["righe"]) == 31 * 24 + 1                       # October has 745 hours in Italian time
    assert p["righe"][0][:2] == ["2026-10-01", 0] and p["righe"][-1][:2] == ["2026-10-31", 23]


def test_prezzi(mese):
    t = tabella(cd.costruisci("2026-10", mese))
    assert (t["prezzo_nord"] == 106.0).all()                    # mean of the four quarter-hours
    assert (t["prezzo_vicini"] == 100.0).all()                  # mean of France (90) and Switzerland (110)


def test_domanda_e_produzione_in_gw(mese):
    t = tabella(cd.costruisci("2026-10", mese))
    assert (t["carico"] == 20.0).all() and (t["residuo"] == 20.0 - 3.0 - 0.1).all()
    assert (t["idro_fluente"] == 2.5).all() and (t["altre_mr"] == 1.2).all()


def test_frontiere(mese):
    t = tabella(cd.costruisci("2026-10", mese))
    assert (t["flusso_CH"] == 3.0).all() and (t["flusso_FR"] == 2.0).all()
    assert (t["import_netto"] == 5.0).all()
    assert (t["export_cnor"] == 2.5).all()                      # out of NORD to Centre-North
    assert (t["cap_import"] == 7.0).all() and (t["cap_export"] == 1.8).all()


def test_capacita_disponibile(mese):
    t = tabella(cd.costruisci("2026-10", mese))
    assert t.loc[("2026-10-01", 12, 0), "gas_disp"] == 21.0     # e1 v1 superseded, e2 cancelled
    # 02/10 02:00 Italian = 00:00Z: CCGT A in e1 (400) and e4 (200) -> counted once, 400 MW
    assert t.loc[("2026-10-02", 2, 0), "gas_disp"] == pytest.approx(21.0 - 0.4)
    # IDRO C: 200 MW unavailable for half of the hour -> 100 MW
    assert t.loc[("2026-10-02", 2, 0), "idro_disp"] == pytest.approx(10.5 - 0.1)
    assert (t["carbone_disp"] == 0).all()


def test_indisponibilita_per_gruppo(mese):
    t = tabella(cd.costruisci("2026-10", mese))
    r = t.loc[("2026-10-02", 2, 0)]
    assert r["indisp_gas"] == pytest.approx(0.4) and r["indisp_idro"] == pytest.approx(0.1)
    # a unit declared "Other" (B20) is shown, but not subtracted from the gas fleet
    assert r["indisp_altro"] == pytest.approx(0.76) and r["gas_disp"] == pytest.approx(21.0 - 0.4)
    assert (t.loc[("2026-10-06", 12, 0), ["indisp_gas", "indisp_idro", "indisp_carbone", "indisp_altro"]] == 0).all()


def test_eventi_del_mese(mese):
    p = cd.costruisci("2026-10", mese)
    ev = {(e["unita"], e["mw_max"]) for e in p["eventi"]}
    # e1 v2 (latest), e3, e4, e5; e2 cancelled (A09)
    assert ev == {("CCGT OTHER", 760.0), ("CCGT A", 400.0), ("IDRO C", 200.0), ("CCGT A", 200.0)}
    assert [e["mw_max"] for e in p["eventi"]] == sorted((e["mw_max"] for e in p["eventi"]), reverse=True)
    altro = next(e for e in p["eventi"] if e["unita"] == "CCGT OTHER")
    assert altro["gruppo"] == "altro" and altro["fonte"] == "Other"
    inizio_mese = int(pd.Timestamp("2026-10-01", tz=TZ).timestamp())
    assert altro["periodi"][0][0] == inizio_mese                # clipped to the month
    assert len(p["ore_utc"]) == len(p["righe"])


def test_senza_a80(mese):
    (mese / "2026-10" / "A80_IT_NORD.csv").unlink()
    p = cd.costruisci("2026-10", mese)
    t = tabella(p)
    assert p["eventi"] is None and t["indisp_gas"].isna().all() and (t["gas_disp"] == 21.0).all()


def test_combustibili_e_file_scritti(mese):
    p = cd.costruisci("2026-10", mese)
    assert p["combustibili"]["default"]["psv"] == 70.0 and len(p["combustibili"]["giornalieri"]) == 22
    assert p["installata_gw"] == {"gas": 21.0, "idro": 10.5, "carbone": 0.0}
    calc = pd.read_csv(mese / "2026-10" / "calc_orario.csv", nrows=1)
    assert all(c == "ts_italia" or c.startswith("calc_") for c in calc.columns)
    js = (mese / "moqa_dati.js").read_text(encoding="utf-8")
    assert js.splitlines()[1].startswith("window.MOQA_REALE = ")


def test_senza_capacita_installata(mese):
    (mese / "2026-10" / "A68_IT_NORD.csv").unlink()
    t = tabella(cd.costruisci("2026-10", mese))
    assert t["gas_disp"].isna().all()                           # the page keeps the panel value


def a71(cartella, righe):
    t = pd.Timestamp("2026-01-01", tz=TZ)
    scrivi(cartella, "A71_IT_NORD", pd.DataFrame([
        {"ts_utc": t.tz_convert("UTC"), "ts_italia": t, "entsoe_zona": "BZN|IT-North", "entsoe_tipo_produzione": tipo,
         "entsoe_eic": "EIC-" + unita, "entsoe_nome": unita, "entsoe_potenza_inizio_anno": mw} for tipo, unita, mw in righe]))


def test_a71_al_posto_di_a68(mese):
    """Without A68 the installed capacity is the sum of the A71 units; the technology of each A80
    unavailability is the A71 type of the same EIC, whatever the A80 message declares."""
    c = mese / "2026-10"
    (c / "A68_IT_NORD.csv").unlink()
    a71(c, [("Fossil Gas", "CCGT A", 400.0), ("Fossil Gas", "CCGT B", 800.0), ("Fossil Gas", "CCGT OTHER", 760.0),
            ("Fossil Gas", "CCGT D", 18040.0), ("Hydro Water Reservoir", "IDRO C", 250.0),
            ("Hydro Pumped Storage", "POMPAGGIO E", 1000.0), ("Hydro Run-of-river and pondage", "FLUENTE F", 300.0),
            ("Other", "BESS G", 200.0)])
    p = cd.costruisci("2026-10", mese)
    assert p["installata_gw"] == {"gas": 20.0, "idro": 1.25, "carbone": 0.0} and p["fonte_installata"] == "A71"
    t = tabella(p)
    r = t.loc[("2026-10-02", 2, 0)]
    # CCGT OTHER is declared B20 in A80 but listed as Fossil Gas in A71: now subtracted from gas
    assert r["indisp_gas"] == pytest.approx(0.4 + 0.76) and r["indisp_altro"] == 0
    assert r["gas_disp"] == pytest.approx(20.0 - 0.4 - 0.76) and r["idro_disp"] == pytest.approx(1.25 - 0.1)
    altro = next(e for e in p["eventi"] if e["unita"] == "CCGT OTHER")
    assert (altro["gruppo"], altro["fonte"], altro["psr_a80"]) == ("gas", "Gas", "B20")


def test_a71_senza_eic_in_comune(mese):
    """A80 units missing from A71 keep the type declared in the message."""
    a71(mese / "2026-10", [("Fossil Gas", "ALTRA UNITA", 500.0)])
    r = tabella(cd.costruisci("2026-10", mese)).loc[("2026-10-02", 2, 0)]
    assert r["indisp_gas"] == pytest.approx(0.4) and r["indisp_altro"] == pytest.approx(0.76)


def test_senza_mgp_si_ferma(mese):
    (mese / "2026-10" / "GME_MGP_NORD.csv").unlink()
    with pytest.raises(ValueError):
        cd.costruisci("2026-10", mese)


def test_cartella_mancante(tmp_path):
    with pytest.raises(FileNotFoundError):
        cd.costruisci("2026-10", tmp_path)


# --------------------------------------------------------------------------- data/ in the repo
PREFISSI_PUBBLICI = ("ts_utc", "ts_italia", "gme_", "entsoe_", "tv_", "calc_")


def test_pronto_per_pubblicare():
    """Fails until data/ holds a real export: run esporta_v01.py (or costruisci_dati.py) first."""
    p = RADICE / "data" / "moqa_dati.js"
    assert p.is_file(), "data/moqa_dati.js is missing: run python scripts/costruisci_dati.py --mese YYYY-MM"
    js = p.read_text(encoding="utf-8")
    payload = json.loads(js[js.index("{"): js.rstrip().rstrip(";").rindex("}") + 1])
    assert payload.get("zona") == "NORD", "data/moqa_dati.js is not the NORD file: rebuild it"
    cartella = RADICE / "data" / payload["mese"]
    assert cartella.is_dir(), f"data/{payload['mese']}/ is missing"
    for f in cartella.glob("*.csv"):
        colonne = pd.read_csv(f, nrows=0).columns
        fuori = [c for c in colonne if not c.startswith(PREFISSI_PUBBLICI)]
        assert not fuori, f"{f.name}: columns outside the public prefixes {fuori}"


# --------------------------------------------------------------------------- scripts/importa_a71.py
def test_importa_a71(tmp_path):
    """The ENTSO-E A71 export becomes A71_IT_NORD.csv: rows without EIC and the current-capacity column dropped."""
    openpyxl = pytest.importorskip("openpyxl")
    import importa_a71 as ia
    wb = openpyxl.Workbook()
    ws = wb.active
    intest = ["Production type", "Code", "Name", "Installed Capacity at the beginning of the year (MW)",
              "Current Installed Capacity (MW)", "Location", "Voltage Connection (kV)", "Commissioning Date",
              "Decommissioning Date"]
    for riga in (["Installed Capacity per Production Unit"], ["01/01/2026 - 01/01/2027"], [],
                 ["BZN|IT-North"] * 9, intest,
                 [None, "NOT_FOUND", "NOT_FOUND", None, "0", "NOT_FOUND", "150", "15/09/2026", None],
                 ["Fossil Gas", "26W-TEST-0000001", "IM_TESTUP_PROVA_1", "380", "380500", "001", "380", "20/12/2022", None]):
        ws.append(riga)
    wb.save(tmp_path / "a71.xlsx")
    df, info = ia.leggi_export(tmp_path / "a71.xlsx")
    assert len(df) == 1 and info["righe_tolte_senza_eic"] == 1 and info["colonne_tolte"] == [ia.SCARTATA]
    assert df.loc[0, "entsoe_potenza_inizio_anno"] == 380 and df.loc[0, "entsoe_tipo_produzione"] == "Fossil Gas"
    assert str(df.loc[0, "ts_italia"]) == "2026-01-01 00:00:00+01:00"
    assert all(c in ("ts_utc", "ts_italia") or c.startswith("entsoe_") for c in df.columns)


# --------------------------------------------------------------------------- i18n/en.js
def test_dizionario_inglese():
    """Every English text uses only the number slots of its Italian key, and the page loads the file."""
    import re
    js = (RADICE / "i18n" / "en.js").read_text(encoding="utf-8")
    diz = json.loads(js[js.index("= {") + 2: js.rstrip().rstrip(";").rindex("}") + 1])
    assert len(diz) > 400
    for it, en in diz.items():
        assert set(re.findall(r"\{\d+\}", en)) <= set(re.findall(r"\{\d+\}", it)), it
    assert '<script src="i18n/en.js"></script>' in (RADICE / "index.html").read_text(encoding="utf-8")
