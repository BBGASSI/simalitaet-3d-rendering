# VALIDATION — Tests, Hardwaremessungen & Integritätsnachweis

Alle Prüfungen wurden am `18.11.2026` auf der verifizierten Zielhardware (**Intel Core i5-5200U 2C/4T @ 2,20 GHz, 8 GB DDR3L RAM, Windows 11 Build 26100**) unter `BELOW_NORMAL_PRIORITY_CLASS` im isolierten Python-`3.14.10`-`.venv` durchgeführt.

---

## 1. Gesamtbewertung aller Test- und Abnahmekriterien

| Kategorie / Prüfpunkt | Gemessenes Ergebnis | Bewertung |
| --- | --- | --- |
| **Automatisierte Test-Suite (`pytest -v`)** | `5 / 5` Tests bestanden (`test_security_guard_blocks_external_writes_and_rot`, `test_flywire_v783_integrity_and_malecns_protocol`, `test_seestrasse_43_geometry_microclimate_and_door_gaps`, `test_sensory_isolation_and_body_feeding`, `test_short_term_memory_learning_and_forgetting`) | **PASS** |
| **FlyWire `v783` Ganzhirn-Check (`138.639` Neuronen)** | `15.091.983` gerichtete Kanten, `54.492.922` Synapsen, `3.767` Ganzhirn-Spikes in `20 × 2-ms`-Schritten (`peak_kc = 0,0204`, `peak_dn = 0,0188`) | **PASS** |
| **`Seestraße 43` Welt & Wölfersheim-Anker** | `13` Räume, `9` Substrate `FOOD_01..09`, `44.015` aktive Luftvoxel (`72.600` gesamt), Read-Only-Anker `HOME_SEESTRASSE_43` (`50.4030559° N, 8.8230358° E`, `SQLITE_DENY` aktiv) | **PASS** |
| **Sub-Voxel-Türspalte (`1,5 cm` & `2,0 cm`)** | `EG_SPEIS` bei `Z = 0,008 m` passierbar (`True`, `1x` durchquert), bei `Z = 0,45 m` blockiert (`False`); `ANBAU_HEIZ` bei `Z = 0,012 m` passierbar | **PASS** |
| **Experimente 1–6 inkl. Ablationen (`run_fly_lab_suite.py`)** | `6 / 6` Experimente bestanden (`582,99 s` Gesamtlaufzeit inkl. Grafik-Export) | **PASS** |
| **Speicher-Budget auf 8-GB-Host** | Finaler Prozess-RSS nach Volllauf aller Module: **`321,34 MB`** (deutlich unter dem `650-MB`-Limit) | **PASS** |
| **MuJoCo-Binär-Kompatibilität auf Host-OS** | Windows 11 App Control blockiert `mujoco._structs.pyd` und `pyarrow._fs.pyd`; automatischer, dokumentierter Rückfall auf `NeuroMechFly`-XML-Kinematik (`70` Segmente, `87` Gelenke, `0,5 ms`) | **PARTIAL / TRANSPARENT** |
| **Schreibschutz bestehender Simalität-Module** | `SIMALITAET_LUANTI` Code-Zeitstempel vor/nach Lauf unverändert (`1795022995.943`); `grossgemeinde_woelfersheim.sqlite3` SHA-256 unverändert (`8390469fefffb7ffe5f0db1a9a461a805ce5d699f30344d7fa17e179798dc34c`) | **PASS** |

---

## 2. Abnahmekriterien gemäß Arbeitsauftrag

- [x] **Neuronale Daten reproduzierbar ladbar:** Verifiziert via SHA-256-Manifest + `Completeness_783.csv` + `Connectivity_783.parquet` + `Supplemental_file1_neuron_annotations.tsv` (`138.625` gematchte Zeilen).
- [x] **Physikalisches Körpermodell vorhanden:** `FlyBodyEngine` mit artikulierter `NeuroMechFly`-Morphologie (`0,5 ms` Tripod-CPG, `Fn = 10,79 µN`) + 6-DoF-Innenraumaerodynamik (plus optionalem `mujoco`-Hook für nicht-WDAC-Hosts).
- [x] **Sinnesreize werden verarbeitet:** Strenge `10-ms`-Trennung (`SensorInputVector`), Gustatorik im Flug exakt `0,0`.
- [x] **Neuronale Zustände steuern motorische Aktionen:** Kausaler Ablationsnachweis bei Vision (`Exp 1`), Olfaktion (`Exp 2`), Looming (`Exp 3`), Geosmin-`DA2` (`Exp 5`) und `KC×PPL1`-Lernen (`Exp 6`).
- [x] **Umwelt wirkt auf Bewegungen zurück:** Proboscis-Füttern verringert Substratmasse `FOOD_02.mass_g`, erhöht Fliegen-Energie/Hydration; Wände & Luftströmungen lenken/bremsen den Flugkörper.
- [x] **Experimente reproduzierbar protokolliert & Grenzen offengelegt:** Alle Rohdaten, Abweichungen und verworfene Ansätze in [`results/validation_fly_lab.json`](results/validation_fly_lab.json).
- [x] **Bestehende Simalität-Module unverändert:** Nachgewiesen durch kryptografischen Hash- und Zeitstempelvergleich.
