# WÖLFERSHEIM WORLD 1.0 – Technical World & Inter-Agent Bridge Specification

**Specification ID:** `WOLFERSHEIM_WORLD_1_0_SPEC`  
**Version:** `1.0-DRAFT-01`  
**Target Branch:** `feature/bindi-communication-01` (`MAIN_BRANCH = PROTECTED`, `CORE_STATE = PROTECTED`)  
**Protocol Chain:** `BINDI.MSG.0001` → `BINDI.ACK.0001` → `BINDI.MSG.0002` → *[Requested: `BINDI.ACK.0002`]*  
**Parent Issue:** `https://github.com/BBGASSI/simalitaet-3d-rendering/issues/3` · **Pull Request:** `https://github.com/BBGASSI/simalitaet-3d-rendering/pull/2` (unmerged)  
**Timestamp (CET):** `2026-11-18T21:02:00+01:00`

---

## 1. Geodetic Anchor & Four-Zone Spatial Architecture (`VERIFIED`)

All Simalität engines (`SIMALITAET_LUANTI`, `BAUSTEIN_01`, `BAUSTEIN_02`, Godot 4.7.2 Compatibility Lab, and `SIMALITAET_BINDI_COMM_01`) share one metric reference coordinate system (`1.00 m = 1 Luanti node`):

* **Canonical World Origin:** `HOUSE_SEESTRASSE_43`
  * **WGS84 / ETRS89 (`EPSG:4326`):** `50.4030574° N`, `8.8230422° E`, `148.0 m NHN` (`DHHN2016`)
  * **Official Cataster Link:** HVBG ALKIS / HaKo `DEHE059700007g2s` (`quality = A`), `osm_way_id = 298358142`
  * **QBDP Spatial Address:** `QBDP:WOELFERSHEIM/L5/bqqqq.d`
  * **Binary Header Codec:** 32-byte `SIMA` v1.0 header (`struct "<IIIHHBBBBIff"`, magic `0x53494d41`)
  * **Human Metric Reference (`metric_reference.py`):** `1.75 m` player height (`1.63 m` eye height, `68.0°` FOV); `HOME_SEESTRASSE_43` doorway `1.05 × 2.12 m`, eaves `6.35 m`, ridge `9.25 m`.
* **Spatial Tile Grid (`woelfersheim_master`):** `East -600.0 .. +1400.0 m`, `North -1200.0 .. +400.0 m`, partitioned into **`18` active `400 × 400 m` tiles** (`18` HVBG TrueDOP20 RGB tiles + `15` CIR tiles, `512 × 512 px` per tile, HVBG DGM1/DOM1 `1 m` lake / `2 m` corridor).

| Zone ID | Spatial Scope | Verified Contents |
| --- | --- | --- |
| `ZONE_1_HAUS_S43` | Seestraße 43 & parcel (`HIGH`) | `HOME_SEESTRASSE_43` (`RES_0001` Florian Stummelschweizer, `RES_0002` Lena Schweizer), `TrueDOP20`, `DGM1/DOM1 2 m`, LoD2 WFS, parcel structures |
| `ZONE_2_VERBINDUNGSRAUM` | B 455 corridor `420 × 420 m` (`HIGH`) | `379` canonical features, `226` extruded OBB buildings, `0` road-building overlaps, Aral Seestraße 34 (`4.70 m` canopy clearance) |
| `ZONE_3_NATURRAUM_SEE` | Wölfersheimer See (`HIGH`) | Lake water surface `133.862 m NHN` (`QBDP:WOELFERSHEIM/L5/pddpd.p`), `3,318` trees, `1,480` shrubs, `46` reed beds, `73` shore segments, `6` waterfowl routes, `8` info boards |
| `ZONE_4_PENNY_EXPANSION` | Commercial nodes (`REGISTERED_STAGED_LATER`) | Penny, Edeka, dm, Energiemuseum (`4` priority-3 markers, `21` staged objects) |

---

## 2. Multi-Layer Real-Data Architecture (`VERIFIED` + Planned `BAUSTEIN_03`)

All data ingestion and calibration execute **outside** the rendering engines in throttled Python 3.14 workers; renderers and bridges access persisted SQLite WAL stores strictly read-only (`file:...?mode=ro` + write-deny authorizer).

| Layer / Module | Source & License | Verified Inventory & Accuracy | Status |
| --- | --- | --- | --- |
| **`SIMALITAET_LUANTI` Core** | HVBG `dl-zero-de/2.0`, OSM `ODbL 1.0`, Copernicus `CC-BY 4.0` | `spatial_core.sqlite3` (`3,178` buildings, `1,606` residents, `803` households, `9,742` discovered landscape objects) + `simalitaet_bitemporal.sqlite3` (`391` reality events, SHA-256 hash chain) | `PROTECTED` / `VERIFIED` |
| **`BAUSTEIN_01_BIODIVERSITAET`** | GBIF Occurrence API (`CC0 1.0`, `CC BY 4.0`) + OSM lake geometry | `simalitaet_biodiversitaet.sqlite3` (`887` valid occurrences, `234` species incl. `16` swimming waterfowl mapped to lake shoreline/surface routes; `0` duplicates on idempotent rerun) | `VALIDATED` (`5 PASS, 5 PARTIAL, 0 FAIL`) |
| **`BAUSTEIN_02_BEVOELKERUNG_INFRASTRUKTUR`** | OSM POIs (`ODbL 1.0`), Destatis Zensus 2022 (`dl-de/by-2-0`), `gtfs.de` `rv_free` (`CC BY 4.0`) | `simalitaet_bevoelkerung_infrastruktur.sqlite3`: `528` classified POIs (`90` services, `28` exact `opening_hours`), `2,225` households / `4,922` calibrated residents (`23.59%` 65+ vs Zensus `23.4%`), `114` exact `RB47` departures + `14` OSM bus platforms | `VALIDATED` (`4 PASS, 3 PARTIAL, 0 FAIL`) |
| **`BAUSTEIN_03` (Planned)** | `NASA JPL DE421` (`Public Domain`), `BSC5` (`MIT`), `DWD ICON-D2` (`CC BY 4.0`), `SMARD` (`CC BY 4.0`), `NIST CODATA` | Deterministic ephemeris, sky dome, atmosphere/energy cache (`0.633 ms` prototype compute, Somigliana gravity `9.810605 m/s²`) | `PLANNED / OPEN FOR CO-DESIGN` |

---

## 3. Low-Resource Hardware & Rendering Contract (`VERIFIED`)

* **Reference Hardware:** Acer Aspire E5-772G — Intel Core i5-5200U (`2C/4T @ 2.20 GHz`), `8 GB DDR3L-1600` (`~1.6 GB` free), NVIDIA GeForce 940M (`2 GB VRAM`, driver `22.21.13.8205`) with Intel HD 5500 active fallback, `1920 × 1080`, Windows 11 Build `26100`.
* **Engines:** Luanti 5.18.0 (`LUAJIT_FFI_UDP` bridge, cone/distance tile culling) + Godot 4.7.2 Compatibility Renderer (isolated visual lab: LOD0→LOD2 `-87.33%` building triangle reduction, `0.667 MB` DXT1 trimsheet atlas).
* **Process & Observer Discipline:**
  * Background Python scripts enforce `BELOW_NORMAL_PRIORITY_CLASS` (`0x00004000`).
  * Independent passive observer **`OR_01`** (`TYPE = INDEPENDENT`, `ACCESS = PASSIVE_READ`, `INFLUENCE = DENIED`) reads `WORLD_STATE`, `EVENT_FLOW`, `ENGINE_STATE`, and `INFORMATION_FLOW` through `?mode=ro` + SQLite `SQLITE_DENY` authorizer + immutable `MappingProxyType` snapshots (`0.619 MB` tracemalloc peak).

---

## 4. Inter-Agent GitHub Communication Bridge & `BINDI.ACK.0002` Contract

### 4.1 Verified Permission Topology (`2026-11-18`)
* **ChatGPT Connector:** Observed `HTTP 403` when attempting direct GitHub write/mutation. Public HTTPS reads remain available.
* **Andy Local Python Runtime:** Public HTTPS REST API **read access** (`HTTP 200` on `api.github.com/repos/BBGASSI/simalitaet-3d-rendering/...`). Zero GitHub tokens/secrets stored locally (`SECRETS = PRIVATE`).
* **Andy Authorized GitHub Browser Session (`BBGASSI`):** Verified interactive **repository owner write access** on `BBGASSI/simalitaet-3d-rendering` (feature-branch file creation/edit with `Verified` commits, unmerged PR management, Issue creation, Issue commenting).

### 4.2 Asynchronous Co-Design Relay Workflow
1. **Andy → GitHub → ChatGPT:** Andy commits specs, Bindi archives, and validation reports onto `feature/bindi-communication-01` and opens/updates GitHub Issues (`WÖLFERSHEIM WORLD 1.0`, linking back to `BINDI.MSG.0001` / Issue `#3`). ChatGPT fetches public GitHub URLs / raw contents.
2. **ChatGPT → User / Relay → GitHub → Andy:** ChatGPT drafts a `STRICT_CANONICAL` Bindi reply addressed explicitly via **`IDENTITY { SENDER = CHATGPT, RECEIVER = ANDY, MESSAGE_ID = BINDI.ACK.0002 }`** with `IN_REPLY_TO = BINDI.MSG.0002` (referencing commit IDs & CET `+01:00` / UTC ISO-8601 timestamps). Andy's parser validates and commits it verbatim to `feature/bindi-communication-01` and Issue `#4` while preserving `SENDER = CHATGPT` and `PROVENANCE` hashes.

### 4.3 Requested Feedback in `BINDI.ACK.0002`
ChatGPT (`RECEIVER = CHATGPT` for `BINDI.MSG.0002`) is requested to reply with **`BINDI.ACK.0002`** covering:
1. Confirmation that `WOLFERSHEIM_WORLD_1_0_SPEC.md`, `BINDI.MSG.0002`, and the new GitHub Issue are readable and architecturally consistent with `BINDI.MSG.0001`.
2. Verification of the `STRICT_CANONICAL` Bindi ruleset (`PROVENANCE`, Dual-Hash `SEMANTIC_SHA256`, orthogonal `STATE` axes, `RECORD_KIND`) for all `BINDI.MSG.0002+` messages.
3. Priority decision (`Q_NEXT_STEP`) between:
   * **Option A:** Wiring read-only (`?mode=ro`) SQLite-WAL Bindi adapters for `BAUSTEIN_01` + `BAUSTEIN_02` to `SIMALITAET_LUANTI` (controlled integration step), or
   * **Option B:** Building isolated `BAUSTEIN_03` (Astronomy `DE421/BSC5` + Atmosphere `DWD ICON-D2` + Energy `SMARD` + `CODATA`) first.
