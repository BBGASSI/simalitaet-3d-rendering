# SIMALITAET_FLY_LAB — Biologisches Referenzmodell *Drosophila melanogaster* & Testuniversum Seestraße 43

`SIMALITAET_FLY_LAB` ist das erste biologisch inspirierte Forschungsmodul innerhalb der **SIMALITÄT**. Es verbindet das reale Ganzhirn-Konnektom von *Drosophila melanogaster* (**FlyWire FAFB v783**, `138.639` Neuronen, `15.091.983` gerichtete Kanten, `54.492.922` chemische Synapsen) und die artikulierte Morphologie von **NeuroMechFly v2** (`70` Segmente, `87` Gelenke) mit dem deterministischen 3D-Wohnhaus-Testuniversum **Seestraße 43** (`13` Räume, `0,25-m`-Mikroklima-Voxel, `8` VOC-Klassen, `9` dynamische Substrate `FOOD_01`–`FOOD_09`), verankert per striktem Read-Only-Zugriff (`?mode=ro`) an `HOME_SEESTRASSE_43` in `SIMALITAET_GROSSGEMEINDE_WOELFERSHEIM`.

---

## Forschungsprinzip & ehrliche Grenzen

Das System erzeugt keinen vorprogrammierten Animationsfilm, sondern einen **geschlossenen sensorimotorischen Regelkreis** im `10-ms`-Takt:

> **Umwelt (`Seestraße 43`) → `SensorInputVector` → reales FlyWire-`v783`-Konnektom + MB-Kurzzeitplastizität → `MotorOutputVector` → NeuroMechFly-Lauf/6-DoF-Flugphysics → veränderte Weltwahrnehmung**

**Ausdrücklich nicht behauptet:**
- **Kein Bewusstsein** oder subjektives Erleben.
- **Kein Langzeitgedächtnis (LTM):** Implementiert ist ausschließlich transiente 3-Faktor-Kurzzeitplastizität im Pilzkörper (`KC × DAN → MBON`, `τ_decay = 180 s`), die bis `t = 1800 s` auf den Ausgangszustand zurückfällt (`Exp 6`).
- **Vollständige Transparenz von Modellannahmen:** Alle elektrischen LIF-Konstanten (`τ_m = 20 ms`), Weber-Fechner-Sensorkurven und Halskonnektiv-/VNC-Ausgabematrizen sind getrennt von den empirischen EM-Synapsendaten dokumentiert.

---

## Ergebnisse im Überblick (`run_fly_lab_suite.py`)

| Experiment / Test | Gemessenes Hauptergebnis (Intakt vs. Ablation) | Status |
| --- | --- | --- |
| **Exp 1: Phototaxis (`EG_WOHN_ESS`)** | `MeTu` intakt: mittl. UV-A `0,971` (Südfenster-Abstand `1,897 m`, `0` Kollisionen) vs. Vision abliert: `0,000` (`9,251 m`, `886` Kollisionen) | **PASS** |
| **Exp 2: Chemotaxis (`OG_FLUR → EG_KUECHE`)** | Treppenhaus-Abstieg `EG`-Zeit `27,62 s` vs. Olfaktion=0 `0,00 s`; Küche findet `FOOD_02` in `2,10 s` (`15,91 s` Fresszeit, `+4,1838 mJ`) | **PASS** |
| **Exp 3: Hindernisse & `1,5-cm`-Türspalt** | `LC4/LPLC2` intakt `2` Kollisionen vs. Looming abliert `985`; `EG_SPEIS` unter `1,5-cm`-Türspalt durchquert (`True`, `1x`) | **PASS** |
| **Exp 4: Körperkoordination (`NeuroMechFly`)** | Tripod Duty `A = 0,623`, `B = 0,625`; `3,153 mJ` Zuckeraufnahme vs. `0,0264 mJ` Umsatz | **PASS** |
| **Exp 5: Geosmin-`DA2` vs. Durst (`FOOD_09`)** | Minimalabstand `DA2` intakt (hydr.) `1,422 m` vs. `DA2` abliert (durstig) `0,517 m`; Kreuzlüftung `EG_KUECHE` aktiv | **PASS** |
| **Exp 6: MB-Kurzzeitlernen & Vergessen** | `t = 10 s` & `60 s`: `0,0 s` auf `FOOD_02` (Aversion) vs. `Frozen = 7,99 s`; `t = 1800 s`: vergessen (`Valenz = -0,0001`, `7,99 s`) | **PASS** |

---

## Verzeichnisstruktur

- [`fly_lab/security_guards.py`](fly_lab/security_guards.py) — SplitBrain-/ROT-Schutz & Read-Only-SQLite (`?mode=ro` + `SQLITE_DENY`)
- [`fly_lab/download_flywire.py`](fly_lab/download_flywire.py) — Reproduzierbarer FlyWire-`v783`-Download & SHA-256-Manifest
- [`fly_lab/connectome.py`](fly_lab/connectome.py) — Modul A: FlyWire-`v783`-CSR-Loader (`138.639` Neuronen) & `5.764`-Neuronen-Subgraph
- [`fly_lab/malecns_adapter.py`](fly_lab/malecns_adapter.py) — Modul A (Erweiterung): `ConnectomeGraphProtocol` & `MaleCNS v1.0`-Adapter
- [`fly_lab/seestrasse_43_world.py`](fly_lab/seestrasse_43_world.py) — Modul F: Deterministisches 3D-Haus `Seestraße 43` (`72.600` Voxel, `13` Räume, `9` Substrate)
- [`fly_lab/body_engine.py`](fly_lab/body_engine.py) — Modul C: `NeuroMechFly`-XML-Kinematik (`0,5 ms`) + 6-DoF-Flugphysik
- [`fly_lab/sensory_interface.py`](fly_lab/sensory_interface.py) — Modul D: Strenge `10-ms`-Welt→Fliege-Sensorschnittstelle
- [`fly_lab/neural_and_memory.py`](fly_lab/neural_and_memory.py) — Module B & E: LIF-Propagation & MB-Kurzzeitplastizität (`τ_decay = 180 s`)
- [`fly_lab/research_lab.py`](fly_lab/research_lab.py) — Modul G: 7 epistemische Kammern, 4 Forschungsmetriken & Experiment-Runner
- [`run_fly_lab_suite.py`](run_fly_lab_suite.py) — Reproduzierbare Gesamtausführung & Grafik-Export
- [`tests/test_fly_lab.py`](tests/test_fly_lab.py) — Automatisierte Unit- und Integrationstests (`pytest -v`)

---

## Dokumentation

1. [`WHITEPAPER_FLY_LAB.md`](WHITEPAPER_FLY_LAB.md) — Wissenschaftliche & technische Gesamtarchitektur
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — Module A–G, API-Vektoren & `Seestraße 43` Spezifikation
3. [`DATA_SOURCES.md`](DATA_SOURCES.md) — Datensätze, SHA-256-Prüfsummen & Lizenzen
4. [`EXPERIMENTS.md`](EXPERIMENTS.md) — Versuchsprotokolle, Ablationen & Messergebnisse (Exp 1–6)
5. [`VALIDATION.md`](VALIDATION.md) — Tests, Hardwareprofil (`321,34 MB` RSS), BDG-0/Luanti-Integrität
6. [`ROADMAP.md`](ROADMAP.md) — Nächste Meilensteine (`MaleCNS`, Multi-Agenten-Pheromone, Luanti Phase 8)
7. [`EINFUEHRUNG_VIRTUELLE_FLIEGE.md`](EINFUEHRUNG_VIRTUELLE_FLIEGE.md) — *„Wie bringen wir einer virtuellen Fliege bei, eine Welt wahrzunehmen?“*

---

## Reproduzierbare Ausführung (isoliertes `.venv`)

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -u run_fly_lab_suite.py
```
