# SIMALITÄT — Ökosystem-Observatorium: Validierungs- & Abnahmebericht

**Datum:** 2026-11-19  
**Entwicklungsbranch:** `feature/simalitaet-observatory-01` (abgeleitet von `feature/simalitaet-ecosystem-01`)  
**Ausführungsnachweise:** `run_observatory_validation.py`, `pytest -v`, Live-Browser-Abnahme auf `http://127.0.0.1:8765`

---

## 1. Gesamturteil: Tests, Performance & Integrität

| Prüfpunkt | Gemessener Wert | Kriterium | Status |
| --- | --- | --- | --- |
| Automatisierte Testsuite (`pytest -v`) | **15 passed** (`5` Fly-Lab + `4` Ecosystem + `6` Observatory) in `186,24 s` | `100 % PASS`, `0 FAIL`, `0 SKIP` | **PASS** |
| Regenzyklus 90 s (`run_observatory_validation.py`) | **54,09 s** (`15,03 ms/Tick`), Peak RSS **323,39 MB** | `< 25 ms/Tick`, `< 650 MB` | **PASS** |
| Bit-exakter Determinismus (`SHA-256`, `Seed=42`) | Identisch: `cc7cd88bae2ace2e565340f9309a76df6d893587d71149f825f35aca44b6bd07` | Regenlauf 1 == Regenlauf 2 | **PASS** |
| Schutzintegrität (`protected_core_integrity.intact`) | **`True`** (Vorher == Nachher für Luanti, SQLite-DBs, DWD-JSON) | Keine unerlaubten Schreibzugriffe | **PASS** |
| Live-Web-Observatorium (`http://127.0.0.1:8765`) | Alle 3 Abnahme-Durchgänge ohne Konsolenfehler / HTTP-Fehler | Echtzeit-Lauf, Klicks, Diff, Kausalketten | **PASS** |

---

## 2. Kausale Gegenprobe: Regenzyklus vs. Trocken-Kontrolle (`t = 90 s`, `Seed = 42`)

| Kenngröße (mit Einheit) | `REGENZYKLUS` | `TROCKEN_KONTROLLE` | Mechanistische Wirkung |
| --- | --- | --- | --- |
| Niederschlagssumme | **2,642 mm** (`Peak 11,8 mm/h`) | `0,0 mm` | Kontrollierter Sommerschauer (t=28..64 s) |
| Südterrasse Bodenfeuchte | **19,84 % Vol.** | `10,33 % Vol.` | +9,51 % Vol. Infiltration auf Platten |
| Südterrasse Pfützentiefe | **14,61 mm** | `0,0 mm` | Niederschlag > Infiltration (3,3 mm/h) |
| Kompost & Beet Bodenfeuchte | **29,76 % Vol.** | `10,33 % Vol.` | Hohe Durchlässigkeit (12,5 mm/h) + VOC-Anstieg |
| Apfelbaum (SW) Turgor-Index | **0,952** | `0,6914` | Verzögerte Wurzelwasseraufnahme (`τ = 14 s`) |
| **Innenboden Küche (`SOIL_INDOOR_FLOOR`)** | **0,0 % Vol.** (`0,0 mm` Pfütze) | `0,0 % Vol.` | **Explizite Nicht-Reaktion** (Dach-/Hausbarriere) |
| Lebende Freiland-Fliegen (t=90 s) | **30** (`29` Fänge) | `18` (`30` Fänge) | Kompost-Aktivität + Schutzdynamik nach Regenende |
| Zustandshash (`SHA-256`) | `cc7cd88bae2a...` | `7e34f9fb8222...` | Messbare Divergenz durch Regenkaskade |

---

## 3. Verifizierte Ereignis- & Kausalketten (`82` Ereignisse, davon `3` Nicht-Reaktionen)

* Beispiel einer live im UI (`observatory_live_causal_chain.png`) untersuchten 5-stufigen Kausalkette (`EVT_0059`):
  1. `EVT_0012` (`t=18,0 s`): Wetterwechsel `KLAR → BEWOELKT`
  2. `EVT_0017` (`t=28,5 s`): Wetterwechsel `BEWOELKT → REGEN`
  3. `EVT_0037` (`t=35,0 s`): Niederschlags-Peak `6,4 mm/h` (`Abkühlung 20,6 °C`)
  4. `EVT_0048` (`t=37,0 s`): Südterrasse `puddle_depth_mm: 0 → 1,25 mm`
  5. `EVT_0059` (`t=44,0 s`): Goldlaufkäfer (*Carabus auratus*) `AVOIDING_PUDDLE: 0 → 1` (Ausweichbewegung bei `> 5,0 mm` Pfütze)
* Beispiel einer indirekten Beute-Kaskade (`EVT_0082`, `t=89,0 s`): `KLAR → BEWOELKT → REGEN → Kompost Bodenfeuchte +4,0 % Vol. → Kompost VOC +0,42 → CPA-Fang von Fliege #81 durch KM_01`.
* **Dokumentierte Nicht-Reaktionen (`is_non_reaction = True`):**
  1. `EVT_0043` (`SOIL_INDOOR_FLOOR`): `0,0 % Vol.` Bodenfeuchte & `0,0 mm` Pfütze während Regen-Peak.
  2. `EVT_0046` (`SUB_INDOOR_KITCHEN`): konstante VOC-Duftstärke (`2,80`) & geschützte Innenfliegen.
  3. `EVT_0051` (`SOIL_APPLE_HOLLOW`): verzögerte/gepufferte Pfützenbildung unter der Apfelbaumkrone (`52 %` Interzeption) trotz gleichzeitiger Pfützenbildung auf der offenen Südterrasse.

---

## 4. Read-Only-Datenherkunft & Schutzintegrität (`pre == post`)

* **`SIMALITAET_LUANTI`:** `817` Dateien, `luanti_code_latest_mtime = 1795022995.943` (`verify_3d_visual_rendering.py`) — unverändert.
* **`grossgemeinde_woelfersheim.sqlite3`:** `8390469fefffb7ffe5f0db1a9a461a805ce5d699f30344d7fa17e179798dc34c` — unverändert (`?mode=ro` + `SQLITE_DENY`).
* **`simalitaet_biodiversitaet.sqlite3`:** `0fd92cebe7c18b8ade38263979acb27217662fe81f3dfcc18d447786d8b49c67` — unverändert (`19/20/5` Vögel + `9` erweiterte GBIF-Pflanzen/Insekten).
* **`latest_env_snapshot.json` (`DWD_ICON_D2_LIVE`):** `160e1ccb99dc7acf2fb6e4819c67936b57f0181d3076a012c5d399ca74876bf6` — unverändert (`2026-11-18T18:00`, `9,5 °C`, `81 % rF`, `13,5 km/h`).

*Hinweis zu Bilddateien:* Die Analyse-Grafik (`results/observatory_rain_cycle_analysis.png`) sowie die drei Live-Browser-Screenshots (`results/observatory_live_rain_peak.png`, `results/observatory_live_causal_chain.png`, `results/observatory_live_before_after_diff.png`) sind lokal im Projekt- und Artefaktverzeichnis abgelegt; auf GitHub liegen alle Quellcodes, UI-Dateien, Tests, Spezifikationen und die kompakte Validierungs-JSON (`16.513` Bytes).
