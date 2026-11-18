# SIMALITÄT_ECOSYSTEM — Wissenschaftlich-Technische Spezifikation

**Modulpfad:** `fly_lab/ecosystem/` (Erweiterung von `SIMALITAET_FLY_LAB` rund um Seestraße 43, Wölfersheim)  
**Zweck:** Geschlossenes, mechanistisches 3D-Räuber-Beute-Ökosystem ohne vorprogrammierte Jagdergebnisse, gekoppelt aus einer autonomen *Drosophila-melanogaster*-Population auf Basis des realen **FlyWire-v783**-Konnektoms und drei biologisch differenzierten Vogelarten aus realen Wölfersheimer **GBIF**-Nachweisen.

---

## 1. Epistemische Kennzeichnung (Evidenz- und Datenherkunft)

| Tag | Bedeutung | Beispiele im Ökosystem-Modul |
| --- | --- | --- |
| `[EMPIRICAL_CONNECTOME]` | Direkt aus den unveränderten FlyWire-v783-Dateien extrahiert (`Completeness_783.csv`, `Connectivity_783.parquet`, `Supplemental_file1_neuron_annotations.tsv`) | Induzierter Teilgraph `W_eco` mit **1.993 Neuronen** und **42.311 echten synaptischen Kanten** (`orn_ester=298`, `looming=592`, `dn_steer=4`, `dn_jump=2`, u. a.) |
| `[EMPIRICAL_GBIF_WOELFERSHEIM]` | Über strenge Read-Only-SQLite-Abfragen (`?mode=ro` + `SQLITE_DENY`) verifizierte Daten | `HOME_SEESTRASSE_43` (`osm_way_id=298358142`, `50.4030559° N, 8.8230358° E`, `146.04 m NHN`), *Cyanistes caeruleus* (`n=19`), *Parus major* (`n=20`), *Hirundo rustica* (`n=5`) |
| `[EMPIRICAL_ORNITHOLOGY]` | Literaturgestützte morphologische & aerodynamische Artunterschiede | Spannweiten (`0,18 m / 0,24 m / 0,33 m`), Massen (`11 g / 18 g / 19 g`), Streckung (`4,8 / 5,1 / 9,2`), Flugstrategien (*Foliage-Glean-Hover*, *Perch-and-Sally*, *Aerial Hawking / Prop-Nav*) |
| `[MODEL_ASSUMPTION]` | Explizite zeit- und maßstabsskalierte Rechenannahmen | Globale Synapsenskalierung `0,058` ohne Plastizität, zeitskalierte Vogel-Energiekonten (`100–160 J`, `12,5–13,5 J` pro Fliege für 90–150-s-Läufe), parametrische Garten-Kronengeometrie (`TreeCanopy`), Beer-Lambert-Laubdämpfung |

> **Grenze der Interpretation:** Es wird ausdrücklich **kein** biologisches Bewusstsein, keine vollständige Muskelmechanik der Vögel und keine synaptische Langzeitplastizität (LTM) behauptet.

---

## 2. Gemeinsame 3D-Welt Seestraße 43 (`ecosystem_world.py`)

* **Simulationsraum:** `36 m × 36 m × 18 m` (`X in [-12, 24]`, `Y in [-14, 22]`, `Z in [0, 18] m`).
* **Gebäude Seestraße 43 als reale Barriere:**
  * Haupthaus AABB: `(0, 0, 0) .. (11, 9, 8.2) m`, Nord-Anbau: `(5.5, 9, 0) .. (10, 12.5, 2.8) m`.
  * Vögel prallen physikalisch ab (`clamp_bird_outside_obstacles`) und haben **keine** Sichtlinie durch Hauswände (`0,0`).
  * Fliegen können über das offene Süd-Terrassen-/Küchenportal (`(1.9, 0.15, 1.8) ± (0.95, 0.35, 0.45) m`) in das Innen-Refugium (`SUB_INDOOR_KITCHEN`) ein- und ausfliegen; genau durch diesen Portalkegel gilt gegenseitige Sichttransparenz (`portal_ok`).
* **Laubkronen & Hecken (Beer-Lambert-Sichtdämpfung):**
  * `CANOPY_APPLE_SW`: Zentrum `(-4.5, -5.0, 4.1)`, Radien `(3.2, 3.0, 2.4) m`, `outer=0.36`, `core=0.85`, `kappa=0.65 /m`.
  * `CANOPY_PLUM_SE`: Zentrum `(15.5, -4.5, 4.5)`, Radien `(3.4, 3.2, 2.5) m`, `outer=0.34`, `core=0.82`, `kappa=0.62 /m`.
  * `SHRUB_BERRY_W`: Zentrum `(-6.0, 5.0, 1.6)`, Radien `(2.4, 3.5, 1.4) m`, `outer=0.42`, `core=0.88`, `kappa=0.72 /m`.
  * Vektorisierte Sichtmatrix `compute_los_matrix(pos_a, pos_b)` berechnet exakt Slab-AABB-Schnitt + Ellipsoid-Durchgangsweg `T = exp(-sum(kappa * d_foliage))` identisch zur Skalarfunktion `line_of_sight_transmittance`.
* **11 Artspezifische Sitzwarten (`PerchNode`) & 6 Nahrungs-/Brutsubstrate (`EcosystemSubstrate`):**
  * `SUB_INDOOR_KITCHEN`, `SUB_TERRACE_FRUIT`, `SUB_COMPOST`, `SUB_APPLE_DROP`, `SUB_PLUM_CROWN`, `SUB_BERRY_HEDGE` inkl. thermischer Aufwinde (`wind_at_vec`) über Südterrasse und Kompost.

---

## 3. Autonome FlyWire-Fliegenpopulation (`fly_population.py`)

* **Induzierter FlyWire-Teilgraph `W_eco`:** `1.993` Neurone, `42.311` echte gewichtete Synapsen (`float32` CSR-Matrix), `max_slots = 72`.
* **Batched Echtzeit-LIF-Step (`dt = 25 ms`, `2 × 12,5 ms` Substeps):**
  * Pro Tick wird der aktive Zustandssatz `W_eco @ r_s` gebündelt über alle lebenden Fliegen propagiert.
  * **Antennen-Olfaktorik:** Bilaterale EST-Konzentrationen (`±0,06 m` quer zur Flugrichtung) speisen `orn_ester[left/right]` → `DNa02` Gierlenkung.
  * **Optische Gefahrenwahrnehmung (`LC4/LPLC2 -> DNp01`):** Für jeden Vogel innerhalb `9,5 m` mit `LOS > 0,10` wird die scheinbare Winkelgröße `theta_rad` und Expansionsrate `theta_dot = (2 * r_eff * v_app) / (dist^2 + r_eff^2)` berechnet. Überschreitet `dnp01_mean > 0.22`, `lc4_mean > 0.34` oder der Looming-Reiz `> 1.25`, startet eine reale orthogonale Abwärts-/Seitwärtsflucht (`ESCAPING`, `1,55 m/s`, `0,048 mJ/s`).
  * **Lebenszyklus:** Substratfressen (`FEEDING`, Nährstoffentnahme), Aushungern (`energy_mj <= 0`), Fortpflanzung (`energy_mj >= 13.8`, `repro_cooldown_s <= 0`).
* **Ego-Perspektive (`FlyPerspectiveSample`):** Protokolliert relativen Azimut/Elevation, Winkelausdehnung (`angular_diam_deg`), `theta_dot_rad_s`, Duftvektor sowie `orn_ester`, `lc4_looming`, `dnp01_escape` und `dna02_steer_diff`.

---

## 4. Drei differenzierte Vogelarten & orakelfreie Jagd (`bird_models.py`)

| Art (`Taxon-Key`) | Strategie | Maße / Tempo (`v_cruise .. v_burst`) | Sichtfeld (`FOV / Bino / Reichweite`) | `max_canopy` | Zeitskalierte Energie (`E_max / Fang`) |
| --- | --- | --- | --- | --- | --- |
| **Blaumeise** (*Cyanistes caeruleus*, `2487879`) | `FOLIAGE_GLEAN_HOVER` (Kronen-Schwirrjäger) | `11 g`, `0,18 m`, `5,2 .. 8,8 m/s`, `hover=True`, `6,5 rad/s` | `±145° / ±19° / 8,0 m`, Kronenbonus `1,55` | `0,86` | `100 J` (`12,5 J / Fang`) |
| **Kohlmeise** (*Parus major*, `9705453`) | `PERCH_AND_SALLY` (Sitzwarte & Siedlungsrand) | `18 g`, `0,24 m`, `6,8 .. 11,2 m/s`, `hover=False`, `4,4 rad/s` | `±142° / ±17° / 10,5 m`, Bodenbonus `1,50` | `0,45` | `145 J` (`13,0 J / Fang`) |
| **Rauchschwalbe** (*Hirundo rustica*, `9515886`) | `AERIAL_HAWKING_PN` (Proportional-Navigation) | `19 g`, `0,33 m`, `9,8 .. 15,8 m/s`, `v_min=4,5`, `2,8 rad/s` | `±135° / ±24° / 15,0 m`, Himmelbonus `1,65` | `0,22` | `160 J` (`13,5 J / Fang`) |

* **Orakelfreie Detektion (`perceive_flies`):** Prüft `dist <= max_range`, Sichtkegel `cos >= cos(FOV)`, Vektor-`LOS >= 0.14`, Laubdichte-Ausschluss für `AERIAL_HAWKING_PN`, Habitatkontrast, Winkelrauschen `sigma_ang` und Salienzschwelle (`>= 0.0065`).
* **Physisches Abfangen ohne Skript-Wahrscheinlichkeit:** Ein Fang gelingt ausschließlich bei kontinuierlicher 3D-Annäherung (`_closest_approach_3d <= capture_radius_m`), `los_now >= 0.22` und Schnabelausrichtung (`dot > 0.35`). Entkommt die Fliege (z. B. durch `LC4/DNp01`-Fluchtsprung), wird ein realer Fehlschlag (`missed_strikes += 1`) ohne Energiegewinn bei vollem Burst-Verbrauch gezählt.
* **Ego-Perspektive (`BirdPerspectiveSample`):** Speichert Blickfeld-Azimut/Elevation aller sichtbaren Fliegen, Binokular-Fovea-Zugehörigkeit, Salienz des gelockten Ziels sowie `r_visual_salience`, `r_pursuit_gate`, `r_strike_motor` und `hunger_drive`.

---

## 5. Versuchsprotokoll (`simulation.py`)

1. **`ECO_EXP_1_BASELINE_150S` (`Seed=42`, `t=150 s`, Checkpoint `t=90 s`):** Vollständiges Basis-Ökosystem mit Detail-Trajektorien & Ego-Perspektiven.
2. **`ECO_EXP_2_FLY_LOOMING_ABLATION_90S` (`looming_gain=0.0`):** Isolierte Stilllegung von `LC4/LPLC2 -> DNp01` bei unveränderter Umwelt.
3. **`ECO_EXP_3_BIRD_VISION_DEGRADED_90S` (`vision_gain=0.30`):** Reduzierte Sehschärfe + erhöhtes Winkelrauschen aller Vögel.
4. **`ECO_EXP_4A_DETERMINISM_REPEAT_90S`:** Bit-exakte Wiederholung gegen Checkpoint `t=90 s` (`SHA-256`).
5. **`ECO_EXP_4B_NO_SWALLOW_GUILD_90S`:** Gilden-Perturbation ohne *Hirundo rustica* (Prüfung der Freiland-Nischenentlastung).
