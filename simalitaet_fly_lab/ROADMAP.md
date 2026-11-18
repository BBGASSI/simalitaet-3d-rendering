# ROADMAP — Weitere Entwicklungsschritte für SIMALITAET_FLY_LAB

Diese Roadmap dokumentiert konsequent nur technisch fundierte Anschlussstufen nach vollständiger Abnahme der Phasen 1 bis 7 in `Seestraße 43`.

---

## Kurzfristig (Meilenstein v0.2 — Biologische Vertiefung)
1. **Vollständiger `MaleCNS` Brain+VNC-Import (`male-cns:v1.0`):**
   - Ablösung der absteigenden Halskonnektiv-Approximation durch echte explizite VNC-Motorneuronen (`DNa02 -> VNC -> Coxa/Femur/Wing`-Motoneurone) über das bereits implementierte `ConnectomeGraphProtocol` (`fly_lab/malecns_adapter.py`).
2. **Nativ signierte / Linux-MuJoCo-Ausführung im Hybrid-Runner:**
   - Ausführen identischer Experimente gegen den optional integrierten `mujoco==3.16.0`-Pfad auf Umgebungen ohne Windows-App-Control-Blockade, um Gelenkmomente gegen unseren 0,5-ms-Kinematik-Löser numerisch zu kreuzvalidieren.
3. **Erweiterte Glomerulus-Auflösung im Antennallobus:**
   - Feingranulare Trennung von `VA2` (Diacetyl), `DM1`/`DM2` (Ethanol/Isoamylacetat), `IR64a`/`IR75a` (Essigsäure) und `Or19a`/`DC1` (Limonen) mit expliziten lokalen GABAergen Interneuronen (`LNs`).

## Mittelfristig (Meilenstein v0.3 — Ökologie & Simalität-Verbund)
4. **Mehragenten- & Pheromon-Interaktion in Seestraße 43:**
   - Aktivierung des bereits vorgesehenen `pheromones`-VOC-Kanals (`ORN_DA1` / cVA) für mehrere gleichzeitig simulierte Fliegen, Konkurrenz an `FOOD_01..FOOD_09` und soziale Aggregation.
5. **BINDI-Ereignisstrom-Kopplung (`SIMALITAET_BINDI_COMM_01`):**
   - Publikation verifizierter `ResearchLab`-Versuchsberichte als signierte `.bindi`-Nachrichten mit `SEMANTIC_SHA256`-Provenienz ohne Aufweichung des `ROT`-Schreibschutzes.
6. **Saisonale Kopplung an Wölfersheim (`Baustein 01/02`):**
   - Read-Only-Übernahme echter Außentemperaturen, Luftfeuchte und Sonnenstände aus dem Wölfersheim-Wetter-/Umweltmodell in die gekippte Wohnzimmer-Terrassentür und Dachfenster der `Seestraße 43`.

## Langfristig (Phase 8 — Optionale Luanti-3D-Visualisierung)
7. **Read-Only-Spiegelung nach `SIMALITAET_LUANTI` (nach ausdrücklicher Freigabe):**
   - Darstellung der `Seestraße 43` im Maßstab `1 Block = 0,25 m` (oder vergrößertes Makromodell für Beobachter) über einen entkoppelten, strikt einseitigen Telemetrie-Bus, sodass niemals Simulationseingriffe vom Luanti-Kern ausgehen können.
8. **Langzeit-Konsolidierungsforschung (ARM / LTM):**
   - Erst *nach* expliziter Implementierung biophysikalisch begründeter Konsolidierungspfade (z. B. `KC -> MBON -> CREB/spaced training`-Gating über Stunden) wird eine Ausweitung des Gedächtnishorizonts jenseits der aktuellen `180 s`-Kurzzeitplastizität in Experimenten untersucht.
