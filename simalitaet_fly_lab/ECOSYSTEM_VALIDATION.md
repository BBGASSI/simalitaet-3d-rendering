# SIMALITÄT_ECOSYSTEM — Validierungs- & Evidenzbericht

**Datum:** 2026-11-18  
**Branch-Kontext:** `feature/simalitaet-ecosystem-01` (abgeleitet von `feature/simalitaet-fly-lab-01`)  
**Ausführungsnachweis:** `run_ecosystem_suite.py` (`BELOW_NORMAL_PRIORITY_CLASS`) & `pytest -v`

---

## 1. Gesamturteil & Hardware-/Integritätsprüfung

| Prüfpunkt | Messwert | Kriterium / Grenze | Status |
| --- | --- | --- | --- |
| Automatisierte Testsuite (`pytest -v`) | **9 passed** (`4` Ökosystem + `5` Fly-Lab-Regression in `50,74 s`) | `100 % PASS`, `0 SKIP`, `0 FAIL` | **PASS** |
| Rechenzeit pro 25-ms-Tick (`ECO_EXP_1_BASELINE_150S`) | **13,492 ms/Tick** (`80,953 s` für `150 s`) | `< 25,000 ms/Tick` (schneller als Echtzeit) | **PASS** |
| Peak Working-Set-Speicher (RSS) | **332,22 MB** | `< 650 MB` | **PASS** |
| Bit-exakter Determinismus (`Eco-Exp 1 @ 90s` == `Eco-Exp 4a @ 90s`) | **`True`** (`SHA-256 = edd7f208...e2dcf0c2`) | Identischer Endzustand über alle Individuen | **PASS** |
| Kompakte Ergebnisdatei `validation_ecosystem_summary.json` | **32.716 Bytes** (`results/validation_ecosystem_summary.json`) | `< 40 KB` | **PASS** |
| Schutzintegrität (`protected_code_and_db_intact`) | **`True`** (Vorher == Nachher) | Unveränderte Luanti-Welt & SQLite-DBs | **PASS** |

---

## 2. Read-Only-Verifikation der empirischen Datenquellen

### Wölfersheim & GBIF (`[EMPIRICAL_GBIF_WOELFERSHEIM]`)

* **Hausanker `HOME_SEESTRASSE_43` (`?mode=ro` + `SQLITE_DENY`):** `osm_way_id=298358142`, `lat_deg=50.4030559`, `lon_deg=8.8230358`, `alt_nhn_m=146.04`, `verified_ro=true`.
* **Verifizierte GBIF-Vorkommen (`CC_BY_4_0`):**
  * **Blaumeise** (*Cyanistes caeruleus*, Taxon `2487879`): **19** Nachweise (`2021-01-09` bis `2025-08-06`, `SIEDLUNGSRAUM`, `avg_dist_lake_m=255.1`).
  * **Kohlmeise** (*Parus major*, Taxon `9705453`): **20** Nachweise (`2021-01-09` bis `2025-08-06`, `SIEDLUNGSRAUM`, `avg_dist_lake_m=274.4`).
  * **Rauchschwalbe** (*Hirundo rustica*, Taxon `9515886`): **5** Nachweise (`2021-05-15` bis `2023-05-13`, `COARSE_CORRIDOR`, `avg_dist_lake_m=369.7`).

### FlyWire `v783` Populations-Teilgraph (`[EMPIRICAL_CONNECTOME]`)

* **Induzierte Substruktur `W_eco`:** **1.993 Neurone**, **42.311 reale gewichtete synaptische Kanten** (`orn_ester=298`, `orn_geosmin=39`, `pn_ester=12`, `pn_geosmin=11`, `vision_spectral=120`, `looming=592`, `jo_mechano=100`, `kc=160`, `dan_reward=307`, `dan_punish=16`, `mbon_gaba_glut=44`, `mbon_ach=52`, `lhln=120`, `dn_steer=4`, `dn_forward=2`, `dn_backward=4`, `dn_jump=2`, `motor_feeding=110`).

---

## 3. Gemessene Ergebnisse — Basis-Ökosystem (`150 s`, `Seed=42`)

### Fliegenpopulation (`ECO_EXP_1_BASELINE_150S`)

* **Populationsverlauf:** Start `34` -> **50** Geburten, **28** reale CPA-Fänge durch Vögel, **0** verhungert -> **56 lebende Fliegen** am Ende.
* **Räumliche Endverteilung:** `indoor = 12` (Küchen-Refugium hinter Hausbarriere), `canopy = 7` (Laubschutz), `open_air = 37`.
* **Neuronale & Verhaltens-Aktivität:** **75.754.041** reale FlyWire-LIF-Spikes (`mean_energy = 9,764 mJ`), **811** ausgelöste `LC4/LPLC2 -> DNp01`-Fluchtmanöver.
* **Zustandshash (`t=150 s`):** `10bcdd64426b21e01bab35cb05a58ea2ce1ba09b4578cd047175d899319fd509`.

### Vogelarten (`ECO_EXP_1_BASELINE_150S`)

| Art (`Bird ID`) | Fänge (`catches`) | Fehlschläge (`misses`) | Trefferquote | Detektionen | Energie Ende / Max (`Netto`) | Flugweg | Zonen (`Krone / Rand / Luftraum`) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Blaumeise (`BM_01`)** | **8** | **2** | 80,0 % | 5.011 | `97,87 / 100,0 J` (`+45,93 J`) | 79,7 m | **`97,6 %` / `1,5 %` / `0,9 %`** |
| **Kohlmeise (`KM_01`)** | **10** | **11** | 47,6 % | 4.482 | `76,84 / 145,0 J` (`-11,16 J`) | 448,2 m | `0,9 %` / **`91,7 %`** / `7,5 %` |
| **Rauchschwalbe (`RS_01`)** | **10** | **3** | 76,9 % | 3.690 | `146,60 / 160,0 J` (`+48,60 J`) | 569,1 m | `0,6 %` / `19,1 %` / **`80,3 %`** |

* Alle drei Arten zeigen echte Fänge **und** echte Fehlschläge (`exhausted_events = 0`) sowie eine klare emergente Nischentrennung zwischen Baumkrone (`BM_01`: 97,6 %), Siedlungsrand/Terrasse/Kompost (`KM_01`: 91,7 %) und freiem Luftraum (`RS_01`: 80,3 %).

---

## 4. Kausale Ablationen & Determinismus (`t = 90 s`, `Seed = 42`)

| Experiment | Modifikation | Fluchten (`LC4/DNp01`) | Fänge (Δ vs Basis 90s) | Lebende Fliegen (`open_air`) | Kernaussage |
| --- | --- | --- | --- | --- | --- |
| **Basis (`t=90s`)** | Intaktes System | **628** | **23** (`BM:6, KM:9, RS:8`) | **52** (`36`) | Referenz (`SHA-256 = edd7f208...c2`) |
| **Eco-Exp 2** | Fliegen-Looming aus (`0.0`) | **0** | **27** (`+4`: `BM:6, KM:12, RS:9`) | **67** (`23`) | Keine Fluchtmanöver mehr; +4 Fänge (+ ungestörteres Fressen -> mehr Nachwuchs) |
| **Eco-Exp 3** | Vogel-Visus `30 %` (`0.30`) | **329** | **18** (`-5`: `BM:7, KM:9, RS:2`) | **70** (`36`) | Rauchschwalben-Fänge brechen auf `2` ein (`E = 40,42 J`, Kohlmeise `60,59 J`) |
| **Eco-Exp 4a** | Determinismus-Wiederholung | **628** | **23** (`BM:6, KM:9, RS:8`) | **52** (`36`) | Exakter Hash `edd7f208...e2dcf0c2` (**PASS**) |
| **Eco-Exp 4b** | Ohne Rauchschwalbe | **168** | **15** (`BM:6, KM:9`) | **68** (`38`, `+2`) | Luftraumfliegen nehmen ohne Luftprädator zu (`38` vs `36`) |

---

## 5. Sieben Epistemische Kammern (Zusammenfassung)

1. **`RAW_DATA`:** RO-DB-Anker (`19 / 20 / 5` GBIF-Nachweise) + FlyWire `v783` (`1.993 n / 42.311 e`).
2. **`HYPOTHESIS`:** Mechanistische Jagd- & Nischendifferenzierung über Morphologie, FOV/LOS & 3D-CPA.
3. **`PREDICTION`:** Kausale Effekte von Looming-Ablation, Visus-Reduktion & Gildenwegfall vorab definiert.
4. **`OBSERVATION`:** `75.754.041` Spikes, `50` Geburten, `28` Fänge, stabile Haus-Refugium-Population (`12`), Nischen `97,6 % / 91,7 % / 80,3 %`.
5. **`DEVIATION` (`[MODEL_ASSUMPTION]`):** Zeitskalierte Vogel-Energiekonten (`100–160 J`), statische Synapse `0,058` ohne LTM, parametrische Baumkronengeometrie, explizit kein Bewusstseinsanspruch.
6. **`CONFIRMED_RESULT`:** Bit-exakter `SHA-256`, `13,492 ms/Tick` (`< 25 ms`), `332,22 MB` RSS, alle 3 Ablationen kausal nachgewiesen.
7. **`REJECTED_APPROACH`:** Skriptierte `p_catch`-Wahrscheinlichkeiten, globale Orakel-Fliegenkoordinaten im Vogel, ungeschnittenes Skalar-LOS (`37,0 ms/Tick`) sowie frühe weite Blaumeisen-Patrouille (`rx=5,5 m`) mit aktiver Kronenabstoßung (`0` Fänge im Vorläufertest).

---

## 6. Schutzintegrität (Vorher == Nachher)

* **`SIMALITAET_LUANTI`:** `817` Dateien, `luanti_code_latest_mtime = 1795022995.943` (`verify_3d_visual_rendering.py`) — unverändert.
* **`grossgemeinde_woelfersheim.sqlite3`:** SHA-256 `8390469fefffb7ffe5f0db1a9a461a805ce5d699f30344d7fa17e179798dc34c` — unverändert.
* **`simalitaet_biodiversitaet.sqlite3`:** SHA-256 `0fd92cebe7c18b8ade38263979acb27217662fe81f3dfcc18d447786d8b49c67` — unverändert.
* **`Audit Events`:** ausschließlich `SQLITE_RO_OPEN:grossgemeinde_woelfersheim.sqlite3` und `SQLITE_RO_OPEN:simalitaet_biodiversitaet.sqlite3`.

*Hinweis zur GitHub-Publikation:* Die drei binären PNG-Dashboards (`results/ecosystem_world_3d_and_niches.png`, `results/ecosystem_perspectives_and_neural.png`, `results/ecosystem_population_dynamics_and_experiments.png`) werden aufgrund der Web-Editor-Beschränkung lokal sowie im Bericht-Artefakt geführt; alle Quellmodule, Tests, Spezifikationen und kompakten Validierungsergebnisse befinden sich vollständig auf dem Branch `feature/simalitaet-ecosystem-01`.
