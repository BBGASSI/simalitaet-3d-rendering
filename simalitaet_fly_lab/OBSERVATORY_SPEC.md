# SIMALITÄT — Sichtbares Ökosystem-Observatorium: Spezifikation

**Startkommando (lokaler Web-Server):**
```powershell
.\.venv\Scripts\python.exe run_observatory.py --port 8765 --scenario REGENZYKLUS --season SOMMER --seed 42
```
Anschließend im Browser öffnen: `http://127.0.0.1:8765`

---

## 1. Architektur & Integration in das bestehende System

Das Observatorium erweitert unmittelbar die bestehende Ökosystem-Architektur rund um **Seestraße 43 (Wölfersheim)** ohne parallele Schein-Simulation:

| Komponente | Datei (`fly_lab/ecosystem/`) | Aufgabe |
| --- | --- | --- |
| **Welt- & Okklusionskern** | `ecosystem_world.py` | 36×36×18-m-Raum, Haus Seestraße 43 (`?mode=ro` Anker), Portal-Refugium, 3 Laubkronen, 11 Sitzwarten, 6 Substrate, erweiterte GBIF-Pflanzen/Insekten (`?mode=ro`) & DWD-Referenz (`latest_env_snapshot.json`) |
| **Wetter, Hydrologie, Pflanzen & Insekten** | `environment_dynamics.py` | `WeatherAndSeasonEngine` (`REGENZYKLUS`, `TROCKEN_KONTROLLE`, `STARKREGEN`; 4 Jahreszeiten), physikalisches 18×18-`HydrologyGrid` (2-m-Zellen), 8 klickbare `PlantEntity`-Objekte, 8 klickbare Sekundärinsekten (`Bombus pascuorum`, `Carabus auratus`) |
| **Fliegenpopulation** | `fly_population.py` | Gebündeltes `FlyWire-v783`-Subkonnektom (`1.993` Neurone, `42.311` echte Synapsen), Wetterkopplung nur bei Niederschlag/Dämmerung (`0`-Drift im Trockenzustand), Echtzeit-Export von `ORN`/`LC4`/`DNp01`-Feuerraten |
| **Vogelarten** | `bird_models.py` | *Blaumeise* (`BM_01`), *Kohlmeise* (`KM_01`), *Rauchschwalbe* (`RS_01`) mit Sichtdämpfung (`rain_vis_factor`), Rauchschwalben-Schutzrast bei Starkregen (`>= 6,5 mm/h`) & erhöhtem Regenflugwiderstand |
| **Kausalität & Vorher-Nachher** | `causal_tracker.py` | `CausalTracker` (Ereignisse inkl. Vorgänger-/Nachfolger-IDs & expliziter Nicht-Reaktionen) + `ObservatoryTimeline` (1-s-Snapshots & `compute_diff(t1, t2)`) |
| **Engine & Lokaler Web-Server** | `observatory_engine.py`, `observatory_server.py`, `observatory_ui.html`, `observatory_style.css`, `observatory_app.js` | Thread-sicherer asynchroner `ThreadingHTTPServer` (`HTTP/1.1` auf `127.0.0.1`), 7 umschaltbare Infoschichten, Canvas2D-Heatmap + Kausalketten + SVG-Sparkline |

---

## 2. Sichtbare Prozesse, Einheiten & Datenherkunft

| Domäne | Messgrößen & Einheiten | Herkunfts-Tag |
| --- | --- | --- |
| **Wetter & Tageszeit** | Niederschlagsrate `[mm/h]`, Summe `[mm]`, Temperatur `[°C]`, Rel. Feuchte `[% rF]`, Bewölkung `[%]`, Wind `[m/s]`, Solar-UV `[0..1]`, komprimierte Simulationsuhr (`1,5 Sim-Min/s`) | `MODELLWERT` (Abgleich gegen `[DWD-WETTERDATEN]` `DWD_ICON_D2_LIVE` Anker) |
| **Hydrologie (18×18-Raster)** | Bodenfeuchte `[% Vol.]` (30-mm-Oberboden), Pfützentiefe `[mm]`, Oberflächenabfluss `[cm/s]`, Infiltration `[mm/h]`, Laubkronen-Interzeption (`52 %`), Dachtraufen-Zulauf | `MODELLWERT` (zeitkomprimiert `hydro_scale = 36x`) |
| **Vegetation (8 Pflanzen)** | Blattnässe `[0..1]`, physiologisch verzögerter Zell-Turgor `[0..1]` (`τ = 14 s`), Stomata-Leitfähigkeit `[0..1]`, Nektarvorrat `[mg]`, Vitalität `[0..1]` | `MODELLWERT` + `GBIF_REFERENZ` (*Prunus padus*, *Sambucus ebulus*, *Glechoma hederacea*, *Eragrostis minor*, *Avena sativa*) |
| **Lebensräume (6 Substrate)** | VOC-Duftstärke `[Rel.]`, Nährstoffvorrat `[mg]`, Regenerationsrate `[mg/s]` | `MODELLWERT` |
| **Fruchtfliegen** | Energie `[mJ]`, Fluchtmanöver `[Stk]`, Feuerraten `ORN Ester`, `LC4 Looming`, `DNp01 Escape` `[0..1]` | `FLYWIRE_V783` + `MODELLWERT` |
| **Sekundärinsekten & Vögel** | *Ackerhummeln* (`BUMBLE_01..04`, *Bombus pascuorum*), *Goldlaufkäfer* (`BEETLE_01..04`, *Carabus auratus*), *Blaumeise* (`BM_01`), *Kohlmeise* (`KM_01`), *Rauchschwalbe* (`RS_01`), Energie `[J]`, Speed `[m/s]`, Fänge/Fehlschläge `[Stk]` | `GBIF_REFERENZ` (`CC BY 4.0`) + `MODELLWERT` |

---

## 3. Interaktive Bedienung & Vorher-Nachher-Vergleich

1. **Informationsschichten (7 Toggles):** Wetter & Regen, Bodenfeuchte/Pfützen/Fluss, Vegetation, Substrate/VOC, Tiere, Veränderungs-Ringe (`Δ < 6 s`), Populations-Overlay.
2. **Klickbare Objekte:** Direkter Klick auf der Karte oder in der Seitenliste öffnet den **Objekt-Inspektor** mit Einheiten, Datenherkunfts-Badges, Zeitverlaufs-Sparkline und zugehörigen Kausalereignissen.
3. **Zeitregler & Delta-Heatmap:** Slider `0..90 s` zum Zurückspulen sowie Checkbox **Vorher-Nachher-Vergleich auf Karte** (`t1` vs. `t2`) zur Darstellung räumlicher Bodenfeuchte-/Pfützen-Differenzen.
4. **Ursache & Wirkung + Nicht-Reaktionen:** Filterbare Ereignisliste inkl. interaktivem Kausalbaum (`AUSLÖSER ↓ EREIGNIS ↓ FOLGEWIRKUNG`) sowie explizitem Filter **Ausbleibende Reaktionen** (z. B. trockener Innenboden Küche, Wurzel-Turgor-Verzögerung, Kronen-Interzeptionsschutz).
5. **Gegenprobe (Counterfactual):** `Regen vs. Trocken-Kontrolle (90 s)` vergleicht identischen `Seed=42` mit `0 mm/h` Niederschlag.
