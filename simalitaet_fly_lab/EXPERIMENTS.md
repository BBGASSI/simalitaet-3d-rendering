# EXPERIMENTS — Forschungsfragen, Protokolle & Messergebnisse in Seestraße 43

Alle `6` Experimente + Substrat-Arena wurden deterministisch (`Δt = 10 ms`) über `run_fly_lab_suite.py` ausgeführt und vollständig in [`results/validation_fly_lab.json`](results/validation_fly_lab.json) protokolliert.

> *Hinweis zur Reproduzierbarkeit:* Die beiden hochauflösenden Auswertungs-Dashboards (`results/seestrasse_43_fly_lab_architecture_and_plumes.png` und `results/simalitaet_fly_lab_experiments_01_06.png`) werden deterministisch durch `run_fly_lab_suite.py` erzeugt (Binärgrafiken sind wegen Größeneffizienz nicht im Git-Text-PR enthalten).

---

## Übersicht der gemessenen Ergebnisse

### Experiment 1 — Reaktion auf Lichtquellen (`Phototaxis in EG_WOHN_ESS`)
- **Hypothese:** Spektrale `UV-A/Blue/Green`-Gradienten an der Süd-/West-Fensterfront aktivieren bilaterale `MeTu`-Projektionsneuronen (`457` L / `447` R) und steuern die Fliege ans Südfenster.
- **Messung (`14,0 s`, Seed `101`, Olfaktion `= 0`):**
  - **Intakt:** `mean_light_uv_exposed = 0,9713`, Endabstand zum Südfenster `WIN_EG_WOHN_S = 1,897 m`, `0` Wandkollisionen, `193.210` Spikes (`8,308 m` Pfad).
  - **Kontrolle (`vision_gain = 0,0`):** `mean_light_uv_exposed = 0,0000`, Abstand `9,251 m`, `886` Wandkollisionen (orientierungslos in `EG_FLUR` abgedriftet).
- **Bewertung:** **PASS**

### Experiment 2 — Orientierung anhand von Reizen (`Multi-Etagen-Chemotaxis OG_FLUR → EG_KUECHE`)
- **Hypothese:** Aufsteigende Ester-/Essigsäure-Fahnen aus `EG_KUECHE` leiten die Fliege durch das offene Ost-Treppenhaus nach unten ins EG und im Küchenbereich auf `FOOD_02`.
- **Messung (`32,0 s` Treppenhaus + `18,0 s` Küche):**
  - **Treppenhaus (`OG_FLUR`, Seed `202`):** Intakt steigt `1x` über das Treppenhaus ab und verbringt **`27,62 s` im EG** (`18,71 s` direkt in `EG_KUECHE`, `0` Kollisionen, `600.094` Spikes). **Kontrolle (`olfaction_gain = 0,0`):** **`0,00 s` im EG**, bleibt `32,0 s` im `OG_FLUR` auf `Z = 5,076 m`. Links-antennenläsioniert (`left_antenna_intact=False`) erreicht EG, findet aber ohne Stereo-Ortung kein Substrat (`reached_food = False`).
  - **Küche (`EG_KUECHE`, Seed `205`):** Intakt landet in **`2,10 s`** (`Pfadlänge = 1,101 m`, Tortuosität `0,873`) auf **`FOOD_02`**, frisst `15,91 s` fermentierendes Substrat (`+4,1838 mJ` aufgenommen vs. `0,0827 mJ` verbraucht, `637.905` Spikes). **Kontrolle (`olfaction_gain = 0,0`):** `reached_food = False`, driftet per Phototaxis in `EG_WOHN_ESS` (`9,2 s`).
- **Bewertung:** **PASS**

### Experiment 3 — Hindernisvermeidung & `1,5-cm`-Türspalt (`EG_SPEIS → FOOD_04`)
- **Hypothese:** Optische Expansion (`LC4/LPLC2`, `592` Neuronen) verhindert Wandkollisionen im Flug; gleichzeitig erlaubt die Sub-Voxel-Geometrie die Passage durch den realen `1,5-cm`-Türspalt unter `P_KUECHE_SPEIS_GAP`.
- **Messung (`15,0 s`, Seed `303`):**
  - **Looming intakt (`looming_gain = 1,0`):** **`2` Wandkollisionen** auf `8,32 m` Flugstrecke (`158.554` Spikes).
  - **Looming abliert (`looming_gain = 0,0`):** **`985` Wandkollisionen** (`3,724 m` Pfad, sofort an Wand/Boden gedrückt).
  - **Türspalt-Traverse (`1,5 cm` bei `Z ≤ 0,015 m`):** `EG_SPEIS` erreicht (`True`, `1` Durchgang auf `(7,32, 4,40, 0,004)`), während `Z = 0,45 m` korrekt blockiert bleibt.
- **Bewertung:** **PASS**

### Experiment 4 — Koordination von Körper und Bewegung (`NeuroMechFly` Tripod-CPG & Rüssel-Füttern)
- **Hypothese:** Im gelandeten Modus treibt der biphasische Tripod-CPG (`LF-RM-LH` vs. `RF-LM-RH`) alternierende Tarsalkontakte (`10,79 µN` Gleichgewichtskraft), Rüsselauslenkung (`joint_proboscis`) reduziert Substratmasse und liefert positive Nettoenergie.
- **Messung (`12,0 s`, Seed `404`):**
  - `Tripod A Stance-Duty = 0,623`, `Tripod B Stance-Duty = 0,625`.
  - `FOOD_02`-Fresszeit `11,99 s`, aufgenommene Energie **`3,1530 mJ`**, metabolischer Umsatz **`0,0264 mJ`** (Netto **`+3,1266 mJ`**, Hydration `+4,0358 %`), `463.559` Spikes.
- **Bewertung:** **PASS**

### Experiment 5 — Umweltänderung & Valenzkonflikt (`DA2` Geosmin `FOOD_09` vs. Durst + Kreuzlüftung)
- **Hypothese:** Im Badezimmer `OG_BAD_2` ziehen Feuchte (`HRN`) und Nordfenster nach Norden zum Waschbecken (`FOOD_09`), während Geosmin den angeborenen `DA2`-Schaltkreis (`ORN_DA2` → `DA2_lPN`) zur Umkehr aktiviert.
- **Messung (`12,0 s` Konflikt + `14,0 s` Kreuzlüftung):**
  - **`DA2` intakt (hydriert `78 %`):** Minimalabstand zu `FOOD_09` **`1,422 m`** (sofortiges Abdrehen nach Süden, `0,0 s` Kontakt).
  - **`DA2` abliert (`da2_geosmin_gain = 0,0`, durstig `40 %`):** Nähert sich dem feuchten Waschbecken bis auf **`0,517 m`** (`2,75×` näher, `39.102` Spikes).
  - **Kreuzlüftung (`ventilation_boost = 1,8`):** Verändert Plume-Ausbreitung und Flugpfad in `EG_KUECHE` (`2,648 m`, `0` Kollisionen).
- **Bewertung:** **PASS**

### Experiment 6 — Lern- & Gedächtniseffekte (`KC × DAN → MBON` & ehrliches Vergessen bis `1800 s`)
- **Hypothese:** Gepaarte Bestrafung (`PPL1-DAN` × aktive Frucht-Ester-`KCs`) invertiert die Annäherungsvalenz kurzfristig, klingt aber ohne Konsolidierung exponentiell (`τ = 180 s`) ab.
- **Messung (Seed `606`, je `8,0 s` Test auf `FOOD_02`):**
  - **Retentionskurve Valenz:** `t = 0 s: -1,6000` → `10 s: -1,5135` → `60 s: -1,1465` → `300 s: -0,3022` → `1800 s: -0,0001`.
  - **`t = 10 s` (`Plasticity ON`):** Flucht von `FOOD_02` (`0,00 s` Fresszeit, `4,43 m` Flugpfad).
  - **`t = 60 s` (`Plasticity ON`):** Weiterhin gelernte Vermeidung (`0,00 s` Fresszeit, `4,587 m`).
  - **`t = 300 s` & `1800 s`:** Gedächtnisspur unter Absprungschwelle / praktisch komplett abgeklungen (`7,99 s` Fresszeit, identisch zur naiven Kontrolle).
  - **`Plasticity FROZEN`:** Trotz gleicher Quinin-Konditionierung keine Speicherung (`7,99 s` Fresszeit).
- **Bewertung:** **PASS** (belegt Kurzzeitlernen UND explizites Fehlen von LTM).

### Substrat-Präferenz-Arena (`Seestraße 43` `EG_KUECHE`, `22,0 s`, Seed `707`)
- Erste Nahrungsaufnahme in `2,11 s` auf fermentierendem `FOOD_02` (`Pfad 1,10 m`, Tortuosität `0,873`, `19,82 s` Rüsselkontakt, `ferm_vs_fresh_index = 1,0`, `ferm_share = 1,0`, `aversive_share = 0,0`, Netto-Energiegewinn `+5,1204 mJ`).

---

## 7 Epistemische Kammern (Zusammenfassung)

1. **`RAW_DATA`:** `138.639` Neuronen / `15.091.983` Kanten / `54.492.922` Synapsen + `72.600` Voxel in `Seestraße 43`.
2. **`DEVIATION`:** Windows Application Control blockiert `mujoco._structs.pyd` & `pyarrow._fs.pyd` → sanktionskonform gelöst via `pyarrow._parquet.ParquetReader` & `NeuroMechFly`-XML-Kinematik.
3. **`REJECTED_APPROACH`:** Lineare ORN-Skalierung bei `0,35-mm`-Abstand im Fernfeld (`OG_FLUR` → `EG_KUECHE`) verworfen; ersetzt durch Weber-Fechner-Kompression.
4. **`CONFIRMED_RESULT`:** Alle `6` Experimente (`EXP_1`–`EXP_6`) reproduzierbar gegen ihre Ablationskontrollen bestätigt (`PASS`).
