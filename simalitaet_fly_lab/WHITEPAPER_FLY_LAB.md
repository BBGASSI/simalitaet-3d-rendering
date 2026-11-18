# WHITEPAPER — SIMALITAET_FLY_LAB: Verkörperte biologische Verhaltensforschung auf Basis realer Konnektom-Daten

**Projekt:** SIMALITÄT / `SIMALITAET_FLY_LAB (Seestraße 43)`  
**Stand:** 18. November 2026  
**Primäres Konnektom:** FlyWire FAFB `v783` (`138.639` Neuronen, `15.091.983` gerichtete Kanten, `54.492.922` chemische Synapsen)  
**Testuniversum:** Seestraße 43 (`HOME_SEESTRASSE_43` in Wölfersheim, `13` Räume, `72.600` Voxel à `0,25 m`)

---

## 1. Wissenschaftliche Zielsetzung

Klassische Agenten-Demos trennen Grafik und Kognition oft nur kosmetisch oder ersetzen echte Sensorik durch direkten Weltzugriff („Orakel-Koordinaten“). `SIMALITAET_FLY_LAB` verfolgt das entgegengesetzte Prinzip: **vollständige physikalisch-sensorische Entkopplung**.

Das biologische Referenzmodell (*Drosophila melanogaster*) sieht die 3D-Welt **Seestraße 43** ausschließlich über einen im `10-ms`-Takt erneuerten `SensorInputVector` und wirkt ausschließlich über physische Flug-, Lauf- und Fressaktoren (`MotorOutputVector`) auf sie zurück. Dadurch lassen sich reale Konnektom-Pfade (`ORN → ALPN → KC/LH → MBON/DN`) direkt an identischen Umweltbedingungen messen und gegen gezielte Ablationen testen.

---

## 2. Methodische Synthese

1. **Empirische Konnektom-Basis (`FlyWire v783` + `MaleCNS`-Protokoll):**
   Die gerichtete Synapsengewichtsmatrix `W_full` (`138.639 × 138.639` in `scipy.sparse.csr_matrix`) wird direkt aus den Originaldaten von Dorkenwald et al. (2024), Schlegel et al. (2024) und Shiu et al. (2024) geladen. Über das `138.639`-Neuronen-Netzwerk laufen sowohl ein vollständiger Ganzhirn-Spike-Check (`3.767` Spikes in `20 × 2-ms`-Schritten) als auch Echtzeit-Geschlossenkreis-Läufe über den induzierten `5.764`-Neuronen-Subgraphen (`134.066` reale unmodifizierte Synapsenkanten).
2. **Deterministisches Wohnhaus-Mikroklima (`Seestraße 43`):**
   Auf Basis der konkreten Wohnhaus-Konstruktion (`11,0 × 9,0 m` + `4,5 × 3,5 m` Heizungsanbau, `EG`/`OG`/`DG` mit `38°`-Satteldach und durchgehendem `2,4 × 3,8 m` Ost-Treppenhaus) löst Modul F Temperatur (`17,6–26,5 °C`), Feuchte (`36–98 %`), thermische Konvektion, Spektrallicht (`UV-A`, `Blau`, `Grün`) sowie `8` gekoppelte VOC-Fahnen aus `9` biologischen Substraten (`FOOD_01`–`FOOD_09`) mit wanddichten Leitwertgrenzen inkl. `1,5-cm`-Speisekammerspalt und `2,0-cm`-Heizraumspalt.
3. **Hybride Biomechanik (`NeuroMechFly v2` + 6-DoF-Flug):**
   Unter Wahrung der Windows-11-Anwendungssteuerungsrichtlinie (die `mujoco._structs.pyd` auf dem Testsystem blockiert) werden die `70` Segmente und `87` Gelenke der installierten `NeuroMechFly`-XML-Morphologie (`flygym 2.1.1`) direkt geparst und mit einem `0,5-ms`-Tripod-CPG-Tarsalkontaktlöser sowie 6-DoF-Innenraumaerodynamik kombiniert.

---

## 3. Epistemische Grenzziehung (`EMPIRICAL` vs. `ASSUMPTION`)

Die Forschungsarchitektur folgt den **7 epistemischen Kammern** (`RAW_DATA`, `HYPOTHESIS`, `PREDICTION`, `OBSERVATION`, `DEVIATION`, `CONFIRMED_RESULT`, `REJECTED_APPROACH`):

- **Was empirisch gesichert ist (`CONFIRMED_SOFTWARE_PROPERTY`):** Unter reproduzierbaren Bedingungen bewirken reale bilaterale FlyWire-Schaltkreise und unsere Modellannahmen konsistente Verhaltensunterschiede gegenüber Ablationen (`Phototaxis`, `Treppenhaus-Chemotaxis`, `LC4/LPLC2-Kollisionsvermeidung`, `1,5-cm`-Türspaltpassage, `DA2`-Geosmin-Vermeidung, transiente `KC×PPL1`-Kurzzeitplastizität).
- **Was explizit verworfen oder korrigiert wurde (`REJECTED_APPROACH`):** Lineare ORN-Skalierung bei `0,35-mm`-Abstand versagte im Fernfeld (`OG_FLUR` zu `EG_KUECHE` Faktor `1.300`) und wurde durch logarithmische Weber-Fechner-Kompression ersetzt; ebenso wurde eine Überdominanz peripherer Wohnzimmerfenster über küchennahe Duftfahnen durch realistisches Hunger-Duft-Gating der Phototaxis korrigiert.
- **Was ausdrücklich NICHT beansprucht wird:** Es liegt **kein Bewusstsein**, **keine echte in-vivo-Verifizierung an lebenden Tieren** und **kein Langzeitgedächtnis (LTM)** vor (`Exp 6` belegt vollständiges Vergessen bei `t = 1800 s`, `Valenz = -0,0001`).

---

## 4. Integration in den Simalität-Verbund

Durch `FlyLabSecurityGuard` (`ROT`-Lock, schreibgeschützte URI-SQLite-Adapter mit `SQLITE_DENY`) bleibt die bestehende Welt **`SIMALITAET_LUANTI`** vollständig unberührt (`luanti_code_latest_mtime = 1795022995.943` vor und nach dem Gesamtlauf identisch) und die Datenbank **`grossgemeinde_woelfersheim.sqlite3`** kryptografisch unverändert (`SHA-256: 8390469fefffb7ffe5f0db1a9a461a805ce5d699f30344d7fa17e179798dc34c`).
