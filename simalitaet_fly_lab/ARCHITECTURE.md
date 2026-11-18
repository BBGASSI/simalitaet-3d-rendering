# ARCHITECTURE — Modulgrenzen, Schnittstellen & Testuniversum Seestraße 43

`SIMALITAET_FLY_LAB` erzwingt eine harte architektonische Trennung zwischen der **geometrischen Umwelt (`Seestraße 43`)**, dem **biologischen Agenten (Module A–E)**, dem **World Adapter (Modul F)**, dem **Research Lab (Modul G)** und den **vorgelagerten Simalität-Datenbanken**.

```text
+-------------------------------------------------------------------+
| Vorgelagerte Simalität (STILLGELEGT / READ-ONLY ?mode=ro)        |
| - SIMALITAET_GROSSGEMEINDE_WOELFERSHEIM (HOME_SEESTRASSE_43)      |
| - SIMALITAET_BAUSTEIN_01_BIODIVERSITAET (Habitat/Saison)          |
| - SIMALITAET_LUANTI (UNVERÄNDERT, ROT-Schreibsperre aktiv)        |
+---------------------------------+---------------------------------+
                                  | Read-Only Geodaten-Anker
                                  v
+-------------------------------------------------------------------+
| Modul F: Seestrasse43World (fly_lab/seestrasse_43_world.py)       |
| 13 Räume | 11x9m + Anbau 4,5x3,5m | EG/OG/DG (38° Dach) | 72.600  |
| Voxel (0,25m): T(x,y,z), v_air(x,y,z), H(x,y,z), L(UV,B,G), 8 VOC |
| 9 dynamische Nahrungs-/Substratquellen (FOOD_01 .. FOOD_09)       |
+-----------------+----------------------------------+--------------+
                  |                                  ^
   SensorInputVector (dt=10ms)              MotorOutputVector
   - Stereo C & dC/dt (8 VOC)               - Flug: F_thrust, tau_p/r/y
   - Facettenaugen (UV/B/G, Flow)           - Lauf: v_fwd, omega, jump
   - JO Wind, T_local, is_landed            - Proboscis: Rüssel-Ext.
   - Gustatorik (nur Kontakt!)             - Landung: request_landing
                  v                                  |
+-------------------------------------------------------------------+
| Modul D: Sensory -> Modul A/B/E: FlyWire v783 + MB-Kurzzeitlernen |
| -> Modul C: Body Engine (NeuroMechFly-XML 0,5ms Walk + 6-DoF Flug)|
+-------------------------------------------------------------------+
                  | Telemetrie pro 10-ms-Schritt
                  v
+-------------------------------------------------------------------+
| Modul G: FlyResearchLab (7 Epistemische Kammern & 4 Metriken)     |
+-------------------------------------------------------------------+
```

---

## 1. Module A bis G im Überblick

| Modul | Datei | Aufgabe & Verantwortlichkeit |
| --- | --- | --- |
| **Schutzschicht** | [`fly_lab/security_guards.py`](fly_lab/security_guards.py) | SplitBrain-kompatible Schreib-Whitelist (nur `SIMALITAET_FLY_LAB`), ROT-Lock, `?mode=ro` + `SQLITE_DENY`-Authorizer, `BELOW_NORMAL_PRIORITY_CLASS`, RSS-Monitoring & Vorher/Nachher-Integritätsprüfung von `SIMALITAET_LUANTI` und Wölfersheim. |
| **Modul A (Connectome Loader)** | [`fly_lab/connectome.py`](fly_lab/connectome.py), [`fly_lab/malecns_adapter.py`](fly_lab/malecns_adapter.py), [`fly_lab/download_flywire.py`](fly_lab/download_flywire.py) | Reproduzierbarer Download, SHA-256-Prüfung, Import aller `138.639` FlyWire-v783-Neuronen und `15.091.983` gerichteten Kanten in `scipy.sparse.csr_matrix`, bilaterales Pool-Mapping (`ORN`, `ALPN`, `KC`, `PAM`, `PPL1`, `MBON`, `MeTu`, `LC4/LPLC2`, `JO`, `TRN`, `HRN`, `GRN`, `DNa01/02`, `DNp09`, `MDN`, `DNp01`), Extraktion eines `5.764`-Neuronen-Subgraphen aus echten Kanten sowie `ConnectomeGraphProtocol` für `MaleCNS`. |
| **Modul B (Neural Engine)** | [`fly_lab/neural_and_memory.py`](fly_lab/neural_and_memory.py) | Hybrid-LIF-Simulation (`tau_m = 20 ms`, `V_rest = -52 mV`, `V_thresh = -45 mV`, `5 x 2 ms` Substeps pro `10 ms` Weltschritt), Weber-Fechner-ORN-Transduktion, Hunger-/Durst-Gating und expliziter Ganzhirn-Test auf allen `138.639` Neuronen. |
| **Modul C (Body Engine)** | [`fly_lab/body_engine.py`](fly_lab/body_engine.py) | Liest die NeuroMechFly-v2-XML-Morphologie (`70` Körpersegmente, `87` Gelenke), simuliert im `WalkMode` (`is_landed=True`) den Tripod-CPG (`LF-RM-LH` vs `RF-LM-RH`) mit viskoelastischen Tarsalkontakten (`0,5 ms`), steuert `proboscis_extension` (Masseabbau am Substrat) und `trigger_jump`, sowie im `FlightMode` (`is_landed=False`) 6-DOF-Flug mit Luftstromkopplung und Kollisionsgleiten durch schmale Türspalte. |
| **Modul D (Sensory Interface)** | [`fly_lab/sensory_interface.py`](fly_lab/sensory_interface.py) | Erzeugt alle `10 ms` den unveränderlichen `SensorInputVector`: Stereo-Antennen-Konzentration + `dC/dt` über `8` VOC-Klassen, `UV-A/Blue/Green` je Auge, Kontrastkanten & `6`-Strahl-Looming/Optical-Flow, `v_local` (Johnston-Organ), `T_local`, `H_local`, `is_landed` sowie Kontakt-Gustatorik (`sugar, acid, water, bitter`, strikt `0` im Flug). |
| **Modul E (Learning & Memory)** | [`fly_lab/neural_and_memory.py`](fly_lab/neural_and_memory.py) | `MushroomBodyShortTermMemory`: 3-Faktor-Plastizität (`KC x PAM/PPL1-DAN -> MBON`) mit exponentiellem Vergessen (`tau_decay = 180 s`), `Plasticity ON/FROZEN`-Ablationsschalter, strikt ohne Langzeitgedächtnis-Behauptung. |
| **Modul F (World Adapter)** | [`fly_lab/seestrasse_43_world.py`](fly_lab/seestrasse_43_world.py) | Konstruiert die deterministische 3D-Umwelt `Seestraße 43`, verknüpft den Wölfersheim-Anker read-only und löst das gekoppelte `72.600`-Voxel-Feld (`44 x 50 x 33`, `Δ = 0,25 m`) wanddicht über explizite Portal-Leitwerte. |
| **Modul G (Research Lab)** | [`fly_lab/research_lab.py`](fly_lab/research_lab.py) | Führt reproduzierbare Experimente mit Seeds & Ablationen durch, berechnet alle 4 geforderten Seestraße-43-Forschungsmetriken und dokumentiert Beobachtungen, Abweichungen und verworfene Ansätze in 7 epistemischen Kammern. |

---

## 2. Architektur von Seestraße 43 (`Seestrasse43World`)

- **Haupthaus:** `X ∈ [0,0, 11,0] m`, `Y ∈ [0,0, 9,0] m`
- **Rückwärtiger Heizungsanbau (`ANBAU_HEIZ`):** `X ∈ [5,5, 10,0] m` (`4,5 m`), `Y ∈ [9,0, 12,5] m` (`3,5 m`, `15,75 m²`)
- **Geschosse:**
  - **EG:** `Z = 0,0 .. 2,8 m` (lichte Höhe `2,6 m`) — `EG_FLUR` (`14,5 m²`), `EG_KUECHE` (`16,0 m²`), `EG_WOHN_ESS` (`36,0 m²`), `EG_BAD_1` (`6,5 m²`), `EG_SPEIS` (`5,0 m²`), `ANBAU_HEIZ` (`15,75 m²`)
  - **OG:** `Z = 2,8 .. 5,6 m` (lichte Höhe `2,5 m`) — `OG_FLUR` (`12,0 m²`), `OG_SCHLAF` (`20,0 m²`), `OG_ARBEIT` (`16,0 m²`), `OG_GAST` (`15,0 m²`), `OG_BAD_2` (`12,5 m²`)
  - **DG:** `Z = 5,6 .. 8,2 m` (`1,1 m` Kniestock, `38°` Satteldach) — `DG_STUDIO` (`42,0 m²`), `DG_ABSTELL` (`18,0 m²`)
- **Ost-Treppenhaus (`TREPPENHAUS`):** Durchgehender offener Schacht `2,4 m × 3,8 m` (`X ∈ [8,35, 10,75]`, `Y ∈ [4,95, 8,75]`) ohne Türen im Treppenauge.
- **Sub-Voxel-Türspalte (`PortalSpec`):**
  - `P_KUECHE_SPEIS_GAP`: `EG_KUECHE ↔ EG_SPEIS`, Spaltmaß **`1,5 cm`** (`Z ≤ 0,015 m`)
  - `P_FLUR_HEIZ_GAP`: `EG_FLUR ↔ ANBAU_HEIZ`, Spaltmaß **`2,0 cm`** (`Z ≤ 0,020 m`)
  Wände und geschlossene Geschossdecken besitzen einen Flächenleitwert von `0,0`, sodass Luft und Duftstoffe ausschließlich über definierte Portale, Treppenauge und Türspalte zirkulieren.

---

## 3. Epistemische Trennung

| Kategorie | Inhalt |
| --- | --- |
| **`[EMPIRICAL_CONNECTOME]`** | Sämtliche Zell-IDs, Synapsenzahlen, Neurotransmitter-Vorzeichen und Subgraph-Gewichte `W_sub` / `W_full` stammen unverändert aus FlyWire `v783`. |
| **`[MODEL_ASSUMPTION]`** | Gleichförmige LIF-Konstanten nach Shiu et al. (2024), Weber-Fechner-Sensortransduktion, effektive `0,045 m` Antennenggradient-Skalierung für Voxel-Fahnen und die Dekodierung von `DN`-Aktivitäten auf `F_thrust`, `tau_yaw` und CPG-Geschwindigkeit. |
| **`[MEMORY_BOUNDARY]`** | ausschließlich transiente Kurzzeitplastizität im Pilzkörper (`tau_decay = 180 s`); nach `30 Minuten` abgeklungen; kein Nachweis von Langzeitgedächtnis oder Bewusstsein. |
