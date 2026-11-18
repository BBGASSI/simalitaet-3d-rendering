# DATA_SOURCES — Datenquellen, Versionen, Prüfsummen & Lizenzen

Alle in `SIMALITAET_FLY_LAB` verwendeten biologischen und geografischen Datensätze stammen aus öffentlich zugänglichen Forschungs- und Behördenquellen, werden durch SHA-256-Prüfsummen im [`results/dataset_manifest.json`](results/dataset_manifest.json) verifiziert und strikt lizenzkonform eingesetzt.

---

## 1. Biologische Primärdatensätze (lokal verifiziert & ausgeführt)

| Datensatz / Datei | Version / Quelle | Umfang | Lizenz | SHA-256 |
| --- | --- | --- | --- | --- |
| **`Completeness_783.csv`** | FlyWire FAFB **v783** via [philshiu/Drosophila_brain_model](https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/main/Completeness_783.csv) (Dorkenwald et al., *Nature* 2024; Shiu et al., *Nature* 2024) | `3.327.347` Bytes (`138.639` Neuronen-IDs) | **CC BY 4.0** (FlyWire) / **MIT** (Wrapper-Skripte) | `bbb847a4cc2caaa7a16349722d220c087317b946d148d4d592d94d250617a311` |
| **`Connectivity_783.parquet`** | FlyWire FAFB **v783** gerichteter Synapsengraph (Shiu et al., *Nature* 634, 210–219, 2024; Archival DOI `10.5281/zenodo.10676866`) | `100.804.642` Bytes (`15.091.983` gerichtete Kanten, `54.492.922` chemische Synapsen) | **CC BY 4.0** | `efeb23fb99098e9c390f6869969b2a121a2ee92c833cfc45ecb2c1d8e1af0347` |
| **`Supplemental_file1_neuron_annotations.tsv`** | FlyWire Hierarchische Zelltyp- & Neurotransmitter-Annotationen via [flyconnectome/flywire_annotations](https://raw.githubusercontent.com/flyconnectome/flywire_annotations/main/supplemental_files/Supplemental_file1_neuron_annotations.tsv) (Schlegel et al., *Nature* 634, 139–152, 2024) | `31.720.298` Bytes (`139.248` Zeilen; `138.625` direkt auf `Completeness_783` abgebildet) | **CC BY 4.0** | `b214970b55d2fbe0853bba536fdcb9e28730f4eb7ab06f600491df795da683cd` |

*Hinweis zu großen Rohdaten auf GitHub:* Die 135,8 MB Cache-Dateien im Ordner `cache/flywire_v783/` sind über `.gitignore` aus dem Git-Repository ausgeschlossen und werden beim lokalen Setup über `fly_lab/download_flywire.py` mit automatischer Retry-Logik und SHA-256-Prüfung reproduzierbar bezogen.

---

## 2. Biomechanik- & Physik-Referenzen

| Projekt / Paket | Rolle in `SIMALITAET_FLY_LAB` | Version | Lizenz | Hinweis zur Host-Kompatibilität (Windows 11) |
| --- | --- | --- | --- | --- |
| **NeuroMechFly v2 / `flygym`** | Referenz-Morphologie der *Drosophila melanogaster* (`flygym1_deepfly3d_rollyawpitch.xml`, `70` anatomische Segmente, `87` Gelenke inkl. Coxa-Femur-Tibia-Tarsus, Flügel & Halteren; Wang-Chen et al., *Nature Methods* 2024) | `2.1.1` | **Apache-2.0** | XML-Morphologie wird direkt aus dem installierten Paket geparst |
| **MuJoCo** | Optionale Mehrkörper-Physik-Engine | `3.16.0` | **Apache-2.0** | Auf diesem Windows-11-Host blockiert die Betriebssystem-Anwendungssteuerungsrichtlinie (Windows App Control) das Laden von `mujoco._structs.pyd` und `pyarrow._fs.pyd`. `SIMALITAET_FLY_LAB` umgeht keine OS-Sicherheitsrichtlinien, sondern nutzt sanktionskonform `pyarrow._parquet.ParquetReader` für Parquet sowie den deterministischen 0,5-ms-Hexapoden-Kinematik- und Tarsalkontakt-Löser auf Basis der NeuroMechFly-XML-Geometrie (`body_engine.py`). Auf nicht-blockierenden Linux/macOS/Windows-Systemen steht der optionale `mujoco`-Pfad weiterhin dokumentiert bereit. |

---

## 3. Sekundärer Konnektom-Adapter (`MaleCNS`)

| Datensatz | Rolle | Lizenz | Status |
| --- | --- | --- | --- |
| **`MaleCNS` (`male-cns:v1.0`)** | Alternativer vereinheitlichter Gehirn+Bauchmark-(VNC)-Datensatz von HHMI Janelia / Berg et al. ([neuprint.janelia.org](https://neuprint.janelia.org/?dataset=male-cns:v1.0)) | **CC BY 4.0** | Schema- & Schnittstellen-kompatibel über `ConnectomeGraphProtocol` in `fly_lab/malecns_adapter.py` (inkl. verifiziertem 6-Neuronen-VNC-Referenztest); vollständiger NeuPrint-Massenexport erfordert separates Projekt-Token/Archiv. |

---

## 4. Geodätische & räumliche Simalität-Verankerung (strikt Read-Only)

| Quelle | Inhalt | Zugriffsmethode | Lizenz |
| --- | --- | --- | --- |
| **`SIMALITAET_GROSSGEMEINDE_WOELFERSHEIM` (`grossgemeinde_woelfersheim.sqlite3`)** | Kanonischer Gebäudeanker **`HOME_SEESTRASSE_43`** (`osm_way_id = 298358142`, Ortsteil Wölfersheim, `50.4030559° N, 8.8230358° E`, `146.04 m NHN`, `qbdp_addr = QBDP:WOELFERSHEIM_GROSSGEMEINDE/L6/pddddd.p`) im Kontext der `43,11 km²` / `8.469` Gebäude / `618` POIs / 5 Ortsteile | URI `?mode=ro` + `SQLITE_DENY`-Authorizer | OpenStreetMap **ODbL 1.0**, HVBG Hessen **dl-de/zero-2-0**, Zensus 2022 **dl-de/by-2-0** |
| **`SIMALITAET_BAUSTEIN_01_BIODIVERSITAET` (`simalitaet_biodiversitaet.sqlite3`)** | Ökologischer Saison-/Artkontext Wölfersheim | URI `?mode=ro` + `SQLITE_DENY`-Authorizer | **CC BY 4.0** (GBIF / DWD Open Data) |

---

## 5. Software-Bibliotheken (`.venv`, Python `3.14.10`)

- `numpy 2.5.5` (BSD-3-Clause)
- `scipy 1.18.1` (BSD-3-Clause) — Sparse-CSR-Matrix-Propagation (`138.639 x 138.639`)
- `pyarrow 26.0.1` (Apache-2.0) — Parquet-Lader via `pyarrow._parquet.ParquetReader`
- `matplotlib 3.11.2` / `pillow 12.3.0` (PSF/HPND) — Verifikationsgrafiken
- `pytest 9.2.0` (MIT) — Automatisierte Tests
