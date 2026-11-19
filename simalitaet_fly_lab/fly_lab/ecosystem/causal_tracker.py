# -*- coding: utf-8 -*-
"""
Kausales Ereignis-Tracking (inkl. ausbleibender Reaktionen) und Zeitreihen-Differenzierung
für das SIMALITÄT Ökosystem-Observatorium.

Jedes Ereignis verweist über `cause_event_ids` direkt auf vorausgehende Auslöser
in der laufenden Simulation und trennt explizit Modellwerte, externe DWD-Wetterdaten,
GBIF-Artreferenzen und FlyWire-v783-Aktivitäten.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class CausalEvent:
    event_id: str
    sim_time_s: float
    sim_clock_str: str
    category: str               # "WEATHER", "HYDROLOGY", "VEGETATION", "HABITAT", "INSECT", "BIRD", "NON_REACTION"
    entity_id: str
    entity_label: str
    metric_name: str
    old_value: Any
    new_value: Any
    unit: str
    delta_str: str
    cause_event_ids: List[str]
    mechanism: str
    data_origin: str            # "MODELLWERT", "FLYWIRE_V783", "GBIF_REFERENZ", "DWD_REFERENZ"
    is_non_reaction: bool = False


class CausalTracker:
    """Erkennt reale Zustandsübergänge & Nicht-Reaktionen und verknüpft kausale Ketten."""

    def __init__(self) -> None:
        self.events: List[CausalEvent] = []
        self._event_map: Dict[str, CausalEvent] = {}
        self._seq: int = 0
        self.reset()

    def reset(self) -> None:
        self.events.clear()
        self._event_map.clear()
        self._seq = 0

        self.last_regime: Optional[str] = None
        self.rain_start_id: Optional[str] = None
        self.rain_peak_id: Optional[str] = None
        self.clear_id: Optional[str] = None
        self.cloud_id: Optional[str] = None

        self.soil_base_pct: Dict[str, float] = {}
        self.soil_moist_evt: Dict[str, str] = {}
        self.puddle_active: Dict[str, bool] = {}
        self.puddle_evt: Dict[str, str] = {}
        self.runoff_active: Dict[str, bool] = {}

        self.plant_turgor_base: Dict[str, float] = {}
        self.plant_wet_active: Dict[str, bool] = {}
        self.plant_wet_evt: Dict[str, str] = {}
        self.plant_turgor_evt: Dict[str, str] = {}
        self.plant_nectar_min_in_rain: Dict[str, float] = {}
        self.plant_nectar_rebound_done: Dict[str, bool] = {}

        self.terrace_voc_diluted: bool = False
        self.terrace_voc_evt: Optional[str] = None
        self.compost_boosted: bool = False
        self.compost_evt: Optional[str] = None

        self.bumble_sheltering: bool = False
        self.bumble_evt: Optional[str] = None
        self.beetle_moist_active: bool = False
        self.beetle_puddle_avoid_active: bool = False
        self.beetle_evt: Optional[str] = None

        self.fly_base_open_share: Optional[float] = None
        self.fly_rain_shifted: bool = False
        self.fly_shift_evt: Optional[str] = None
        self.fly_dispersed_post: bool = False

        self.swallow_sheltered: bool = False
        self.swallow_resumed: bool = False

        # Merker für explizite Nicht-Reaktionen
        self.nr_indoor_floor_logged: bool = False
        self.nr_indoor_kitchen_logged: bool = False
        self.nr_root_lag_logged: bool = False
        self.nr_canopy_shield_logged: bool = False

        # Jüngste veränderte Objekt-IDs pro Zeitstempel [(t_s, entity_id), ...]
        self.entity_last_changed_s: Dict[str, float] = {}

    def _emit(
        self,
        sim_time_s: float,
        clock_str: str,
        category: str,
        entity_id: str,
        entity_label: str,
        metric_name: str,
        old_val: Any,
        new_val: Any,
        unit: str,
        delta_str: str,
        causes: Sequence[Optional[str]],
        mechanism: str,
        data_origin: str = "MODELLWERT",
        is_non_reaction: bool = False,
    ) -> str:
        self._seq += 1
        eid = f"EVT_{self._seq:04d}"
        valid_causes = [c for c in causes if c is not None and c in self._event_map]
        ev = CausalEvent(
            event_id=eid,
            sim_time_s=round(float(sim_time_s), 2),
            sim_clock_str=clock_str,
            category=category,
            entity_id=entity_id,
            entity_label=entity_label,
            metric_name=metric_name,
            old_value=old_val,
            new_value=new_val,
            unit=unit,
            delta_str=delta_str,
            cause_event_ids=valid_causes,
            mechanism=mechanism,
            data_origin=data_origin,
            is_non_reaction=is_non_reaction,
        )
        self.events.append(ev)
        self._event_map[eid] = ev
        if not is_non_reaction:
            self.entity_last_changed_s[entity_id] = round(float(sim_time_s), 2)
        return eid

    def observe_step(
        self,
        sim_time_s: float,
        weather: Any,
        soil_zones: List[Any],
        plants: List[Any],
        substrates: List[Any],
        other_insects: List[Any],
        fly_zones: Dict[str, int],
        birds: List[Any],
        bird_events: List[Dict[str, Any]],
    ) -> None:
        clk = weather.clock_str

        # 1. Wetter-Übergänge
        if self.last_regime is None:
            self.last_regime = weather.regime
            self._emit(
                sim_time_s, clk, "WEATHER", "WORLD_WEATHER", "Lokalklima Seestraße 43",
                "regime", "INIT", weather.regime, "Zustand", f"{weather.temperature_c:.1f} °C",
                [], f"Startzustand {weather.season} ({weather.scenario}) bei {weather.cloud_cover_pct:.0f} % Bewölkung.",
                "MODELLWERT",
            )
        elif weather.regime != self.last_regime:
            old_r = self.last_regime
            self.last_regime = weather.regime
            causes = [self.cloud_id if weather.regime == "REGEN" else (self.rain_peak_id or self.rain_start_id)]
            eid = self._emit(
                sim_time_s, clk, "WEATHER", "WORLD_WEATHER", "Lokalklima Seestraße 43",
                "regime", old_r, weather.regime, "Zustand", f"{weather.rain_mm_h:.1f} mm/h",
                causes,
                f"Wetterwechsel von {old_r} nach {weather.regime} (Bewölkung {weather.cloud_cover_pct:.0f} %, rF {weather.humidity_pct:.0f} %).",
                "MODELLWERT",
            )
            if weather.regime == "BEWOELKT":
                self.cloud_id = eid
            elif weather.regime == "REGEN":
                self.rain_start_id = eid
            elif weather.regime in ("AUFKLAREND", "KLAR") and self.rain_start_id is not None:
                self.clear_id = eid

        if weather.rain_mm_h >= 6.0 and self.rain_peak_id is None and self.rain_start_id is not None:
            self.rain_peak_id = self._emit(
                sim_time_s, clk, "WEATHER", "WORLD_WEATHER", "Lokalklima Seestraße 43",
                "rain_mm_h", 0.5, round(weather.rain_mm_h, 1), "mm/h", f"+{weather.rain_mm_h - 0.5:.1f} mm/h",
                [self.rain_start_id],
                f"Kräftiger Niederschlags-Peak ({weather.rain_mm_h:.1f} mm/h) mit Abkühlung auf {weather.temperature_c:.1f} °C.",
                "MODELLWERT",
            )

        # 2. Bodenfeuchte, Pfützen, Abfluss + Nicht-Reaktionen
        for z in soil_zones:
            if z.zone_id not in self.soil_base_pct:
                self.soil_base_pct[z.zone_id] = z.soil_moisture_pct
                self.puddle_active[z.zone_id] = False
                self.runoff_active[z.zone_id] = False
                continue

            if z.is_indoor:
                if weather.rain_mm_h >= 6.0 and not self.nr_indoor_floor_logged:
                    self.nr_indoor_floor_logged = True
                    self._emit(
                        sim_time_s, clk, "NON_REACTION", z.zone_id, z.label_de,
                        "soil_moisture_pct", 0.0, 0.0, "% Vol.", "0.0 % Vol.",
                        [self.rain_peak_id or self.rain_start_id],
                        "Ausbleibende Reaktion: Solides Dach- & Mauerwerk Seestraße 43 schirmt den Küchenboden vollständig gegen Regen ab (0,0 mm Pfütze).",
                        "MODELLWERT", is_non_reaction=True,
                    )
                continue

            base_m = self.soil_base_pct[z.zone_id]
            if z.zone_id not in self.soil_moist_evt and (z.soil_moisture_pct - base_m) >= 4.0 and self.rain_start_id:
                eid = self._emit(
                    sim_time_s, clk, "HYDROLOGY", z.zone_id, z.label_de,
                    "soil_moisture_pct", round(base_m, 1), z.soil_moisture_pct, "% Vol.",
                    f"+{z.soil_moisture_pct - base_m:.1f} % Vol.",
                    [self.rain_start_id],
                    f"Infiltrierender Niederschlag erhöht Bodenfeuchte in {z.label_de} über +{z.soil_moisture_pct - base_m:.1f} % Vol.",
                    "MODELLWERT",
                )
                self.soil_moist_evt[z.zone_id] = eid

            if not self.puddle_active[z.zone_id] and z.puddle_depth_mm >= 1.2 and self.rain_start_id:
                self.puddle_active[z.zone_id] = True
                peid = self._emit(
                    sim_time_s, clk, "HYDROLOGY", z.zone_id, z.label_de,
                    "puddle_depth_mm", 0.0, z.puddle_depth_mm, "mm", f"+{z.puddle_depth_mm:.1f} mm",
                    [self.soil_moist_evt.get(z.zone_id), self.rain_peak_id or self.rain_start_id],
                    f"Niederschlagsrate übersteigt Bodeninfiltration ({z.infiltration_mm_h:.1f} mm/h) -> Oberflächenpfütze ({z.puddle_depth_mm:.1f} mm).",
                    "MODELLWERT",
                )
                self.puddle_evt[z.zone_id] = peid
            elif self.puddle_active[z.zone_id] and z.puddle_depth_mm < 0.25 and weather.rain_mm_h < 0.2:
                self.puddle_active[z.zone_id] = False
                self._emit(
                    sim_time_s, clk, "HYDROLOGY", z.zone_id, z.label_de,
                    "puddle_depth_mm", ">=1.2", z.puddle_depth_mm, "mm", "versickert/verdunstet",
                    [self.clear_id, self.puddle_evt.get(z.zone_id)],
                    f"Nach Regenende versickert und verdunstet das Oberflächenwasser in {z.label_de}.",
                    "MODELLWERT",
                )

            if not self.runoff_active[z.zone_id] and z.flow_speed_cms >= 0.45:
                self.runoff_active[z.zone_id] = True
                self._emit(
                    sim_time_s, clk, "HYDROLOGY", z.zone_id, z.label_de,
                    "flow_speed_cms", 0.0, z.flow_speed_cms, "cm/s", f"+{z.flow_speed_cms:.2f} cm/s",
                    [self.puddle_evt.get(z.zone_id), self.rain_start_id],
                    f"Hangabwärtiger Oberflächenabfluss ({z.flow_speed_cms:.2f} cm/s) entlang der Mikro-Topographie.",
                    "MODELLWERT",
                )

        # Nicht-Reaktion: Kronen-Interzeption schützt Apfelbaum-Mulde bei einsetzendem Regen vor sofortiger Pfütze
        terr_z = next((z for z in soil_zones if z.zone_id == "SOIL_TERRACE_SOUTH"), None)
        apple_z = next((z for z in soil_zones if z.zone_id == "SOIL_APPLE_HOLLOW"), None)
        if (
            terr_z and apple_z and not self.nr_canopy_shield_logged
            and terr_z.puddle_depth_mm >= 1.5 and apple_z.puddle_depth_mm < 0.6
        ):
            self.nr_canopy_shield_logged = True
            self._emit(
                sim_time_s, clk, "NON_REACTION", apple_z.zone_id, apple_z.label_de,
                "puddle_depth_mm", 0.0, apple_z.puddle_depth_mm, "mm", "abgepuffert (<0.6 mm)",
                [self.puddle_evt.get("SOIL_TERRACE_SOUTH"), self.rain_start_id],
                "Ausbleibende Pfützenbildung unter Apfelbaumkrone trotz Pfützen auf offener Südterrasse: Laubkrone fängt 52 % des Tropfenfalls ab.",
                "MODELLWERT", is_non_reaction=True,
            )

        # 3. Pflanzenreaktionen (Blattnässe, verzögerter Turgor, Nektar-Rebound)
        for pl in plants:
            if pl.plant_id not in self.plant_turgor_base:
                self.plant_turgor_base[pl.plant_id] = pl.turgor_index
                self.plant_wet_active[pl.plant_id] = False
                self.plant_nectar_min_in_rain[pl.plant_id] = pl.nectar_mg
                self.plant_nectar_rebound_done[pl.plant_id] = False
                continue

            if not self.plant_wet_active[pl.plant_id] and pl.foliage_wetness >= 0.35 and self.rain_start_id:
                self.plant_wet_active[pl.plant_id] = True
                self.plant_nectar_min_in_rain[pl.plant_id] = pl.nectar_mg
                weid = self._emit(
                    sim_time_s, clk, "VEGETATION", pl.plant_id, pl.label_de,
                    "foliage_wetness", 0.0, pl.foliage_wetness, "Index [0..1]", f"+{pl.foliage_wetness:.2f}",
                    [self.rain_start_id],
                    f"Sofortige Benetzung der Blattoberflächen an {pl.label_de} ({pl.species_ref}).",
                    "MODELLWERT",
                )
                self.plant_wet_evt[pl.plant_id] = weid
            elif self.plant_wet_active[pl.plant_id] and weather.rain_mm_h >= 1.0:
                self.plant_nectar_min_in_rain[pl.plant_id] = min(self.plant_nectar_min_in_rain[pl.plant_id], pl.nectar_mg)
            elif self.plant_wet_active[pl.plant_id] and weather.rain_mm_h < 0.2 and pl.foliage_wetness <= 0.18:
                self.plant_wet_active[pl.plant_id] = False
                self._emit(
                    sim_time_s, clk, "VEGETATION", pl.plant_id, pl.label_de,
                    "foliage_wetness", ">=0.35", pl.foliage_wetness, "Index [0..1]", "abgetrocknet",
                    [self.clear_id, self.plant_wet_evt.get(pl.plant_id)],
                    f"Abtrocknung des Blattwerks an {pl.label_de} durch Wind & Sonnenlicht.",
                    "MODELLWERT",
                )

            # Nicht-Reaktion: Wurzel-Turgor-Verzögerung zu Regenbeginn
            if (
                pl.plant_id == "PLANT_APPLE_TREE" and not self.nr_root_lag_logged
                and pl.foliage_wetness >= 0.45 and (pl.turgor_index - self.plant_turgor_base[pl.plant_id]) < 0.025
            ):
                self.nr_root_lag_logged = True
                self._emit(
                    sim_time_s, clk, "NON_REACTION", pl.plant_id, pl.label_de,
                    "turgor_index", round(self.plant_turgor_base[pl.plant_id], 3), pl.turgor_index, "Index [0..1]", "< +0.025 (Lag)",
                    [self.plant_wet_evt.get(pl.plant_id), self.rain_start_id],
                    "Ausbleibende Sofortreaktion im Zell-Turgor trotz nasser Blätter: Wasseraufnahme über Wurzelzone folgt mit physiologischer Verzögerung.",
                    "MODELLWERT", is_non_reaction=True,
                )

            t0 = self.plant_turgor_base[pl.plant_id]
            if pl.plant_id not in self.plant_turgor_evt and (pl.turgor_index - t0) >= 0.055:
                soil_cause = self.soil_moist_evt.get("SOIL_APPLE_HOLLOW" if pl.pos[0] < 0 else "SOIL_COMPOST_EAST")
                teid = self._emit(
                    sim_time_s, clk, "VEGETATION", pl.plant_id, pl.label_de,
                    "turgor_index", round(t0, 3), pl.turgor_index, "Index [0..1]", f"+{pl.turgor_index - t0:.3f}",
                    [soil_cause, self.rain_start_id],
                    f"Verzögerte Wurzelwasseraufnahme steigert Turgor und Vitalität an {pl.label_de} ({pl.local_soil_moisture_pct:.1f} % Vol. Bodenfeuchte).",
                    "MODELLWERT",
                )
                self.plant_turgor_evt[pl.plant_id] = teid

            if (
                not self.plant_nectar_rebound_done[pl.plant_id]
                and weather.rain_mm_h < 0.3 and self.clear_id is not None
                and pl.max_nectar_mg >= 10.0
                and (pl.nectar_mg - self.plant_nectar_min_in_rain[pl.plant_id]) >= 0.9
            ):
                self.plant_nectar_rebound_done[pl.plant_id] = True
                self._emit(
                    sim_time_s, clk, "VEGETATION", pl.plant_id, pl.label_de,
                    "nectar_mg", round(self.plant_nectar_min_in_rain[pl.plant_id], 2), pl.nectar_mg, "mg",
                    f"+{pl.nectar_mg - self.plant_nectar_min_in_rain[pl.plant_id]:.2f} mg",
                    [self.plant_turgor_evt.get(pl.plant_id), self.clear_id],
                    f"Nektarschub nach Regenende durch hohen Turgor ({pl.turgor_index:.2f}) und Aufklaren.",
                    "MODELLWERT",
                )

        # 4. Lebensraum-/Substrat-Rückkopplung
        for sub_s in substrates:
            if sub_s.substrate_id == "SUB_TERRACE_FRUIT":
                if not self.terrace_voc_diluted and sub_s.voc_strength <= 0.78 * sub_s._base_voc_strength and self.rain_start_id:
                    self.terrace_voc_diluted = True
                    self.terrace_voc_evt = self._emit(
                        sim_time_s, clk, "HABITAT", sub_s.substrate_id, sub_s.label_de,
                        "voc_strength", sub_s._base_voc_strength, sub_s.voc_strength, "Duft-Stärke",
                        f"{sub_s.voc_strength - sub_s._base_voc_strength:.2f}",
                        [self.rain_start_id],
                        "Regen wäscht Duftfahne am offenen Terrassentisch aus (Attraktivität für Fliegen sinkt).",
                        "MODELLWERT",
                    )
                elif self.terrace_voc_diluted and weather.rain_mm_h < 0.2 and sub_s.voc_strength >= 0.95 * sub_s._base_voc_strength:
                    self.terrace_voc_diluted = False
                    self._emit(
                        sim_time_s, clk, "HABITAT", sub_s.substrate_id, sub_s.label_de,
                        "voc_strength", "<=1.7", sub_s.voc_strength, "Duft-Stärke", "erholt",
                        [self.clear_id, self.terrace_voc_evt],
                        "Terrassen-Obstteller verdunstet nach Regenende wieder volle Duftfahne.",
                        "MODELLWERT",
                    )
            elif sub_s.substrate_id == "SUB_COMPOST":
                if not self.compost_boosted and sub_s.voc_strength >= 1.12 * sub_s._base_voc_strength:
                    self.compost_boosted = True
                    self.compost_evt = self._emit(
                        sim_time_s, clk, "HABITAT", sub_s.substrate_id, sub_s.label_de,
                        "voc_strength", sub_s._base_voc_strength, sub_s.voc_strength, "Duft-Stärke",
                        f"+{sub_s.voc_strength - sub_s._base_voc_strength:.2f}",
                        [self.soil_moist_evt.get("SOIL_COMPOST_EAST"), self.rain_start_id],
                        "Feuchtewärme im Komposter verstärkt mikrobielle Gärung, Duftgradient und Substrat-Regeneration.",
                        "MODELLWERT",
                    )
            elif sub_s.substrate_id == "SUB_INDOOR_KITCHEN":
                if weather.rain_mm_h >= 6.0 and not self.nr_indoor_kitchen_logged:
                    self.nr_indoor_kitchen_logged = True
                    self._emit(
                        sim_time_s, clk, "NON_REACTION", sub_s.substrate_id, sub_s.label_de,
                        "voc_strength", sub_s._base_voc_strength, sub_s.voc_strength, "Duft-Stärke", "0.00 (stabil)",
                        [self.rain_peak_id or self.rain_start_id],
                        "Ausbleibende Reaktion im Innen-Refugium Küche: Indoor-Substrat & dortige Fliegen bleiben vom Außenregen vollständig unberührt.",
                        "MODELLWERT", is_non_reaction=True,
                    )

        # 5. Insektenreaktionen (Hummeln, Goldlaufkäfer, FlyWire-Fliegen)
        bumbles = [i for i in other_insects if i.guild == "BUMBLEBEE"]
        beetles = [i for i in other_insects if i.guild == "GROUND_BEETLE"]
        n_bshelt = sum(1 for b in bumbles if b.state == "SHELTERING_RAIN")
        if bumbles and not self.bumble_sheltering and n_bshelt >= 2:
            self.bumble_sheltering = True
            self.bumble_evt = self._emit(
                sim_time_s, clk, "INSECT", "GUILD_BUMBLEBEE", "Ackerhummeln (Bombus pascuorum)",
                "SHELTERING_RAIN", 0, n_bshelt, "Individuen", f"+{n_bshelt} im Schutz",
                [self.rain_start_id, self.plant_wet_evt.get("PLANT_FLOWER_BED_SW")],
                f"Bei Regen > 1,5 mm/h suchen {n_bshelt}/{len(bumbles)} Ackerhummeln Schutz unter Hecke/Baumkronen.",
                "GBIF_REFERENZ",
            )
        elif bumbles and self.bumble_sheltering and n_bshelt == 0 and weather.rain_mm_h < 0.8:
            self.bumble_sheltering = False
            self._emit(
                sim_time_s, clk, "INSECT", "GUILD_BUMBLEBEE", "Ackerhummeln (Bombus pascuorum)",
                "FORAGING_NECTAR", 0, len(bumbles), "Individuen", "Nektarsuche aktiv",
                [self.clear_id, self.bumble_evt],
                "Nach Regenende nehmen alle Ackerhummeln den Bestäubungsflug am Blühstreifen wieder auf.",
                "GBIF_REFERENZ",
            )

        n_cmoist = sum(1 for c in beetles if c.state == "FORAGING_MOIST")
        n_cpud = sum(1 for c in beetles if c.state == "AVOIDING_PUDDLE")
        if beetles and not self.beetle_moist_active and n_cmoist >= 2:
            self.beetle_moist_active = True
            self.beetle_evt = self._emit(
                sim_time_s, clk, "INSECT", "GUILD_BEETLE", "Goldlaufkäfer (Carabus auratus)",
                "FORAGING_MOIST", 0, n_cmoist, "Individuen", f"+{n_cmoist} feucht-aktiv",
                [self.soil_moist_evt.get("SOIL_COMPOST_EAST"), self.rain_start_id],
                "Erhöhte Bodenfeuchte (>= 14,5 % Vol.) steigert die Lauf- & Jagdaktivität der Goldlaufkäfer auf Kompost und Wiese.",
                "GBIF_REFERENZ",
            )
        if beetles and not self.beetle_puddle_avoid_active and n_cpud >= 1:
            self.beetle_puddle_avoid_active = True
            self._emit(
                sim_time_s, clk, "INSECT", "GUILD_BEETLE", "Goldlaufkäfer (Carabus auratus)",
                "AVOIDING_PUDDLE", 0, n_cpud, "Individuen", "Pfützen-Ausweichbewegung",
                [self.puddle_evt.get("SOIL_TERRACE_SOUTH"), self.puddle_evt.get("SOIL_APPLE_HOLLOW")],
                "Tiefe Oberflächenpfützen (> 5,0 mm) verdrängen Goldlaufkäfer aktiv auf höheres Terrain.",
                "GBIF_REFERENZ",
            )

        tot_out = max(1, fly_zones.get("canopy", 0) + fly_zones.get("open_air", 0))
        open_share = fly_zones.get("open_air", 0) / tot_out
        if self.fly_base_open_share is None:
            self.fly_base_open_share = open_share
        elif (
            not self.fly_rain_shifted and weather.rain_mm_h >= 2.5
            and (self.fly_base_open_share - open_share) >= 0.09 and self.rain_start_id
        ):
            self.fly_rain_shifted = True
            self.fly_shift_evt = self._emit(
                sim_time_s, clk, "INSECT", "POP_DROSOPHILA", "Fliegenpopulation (FlyWire v783)",
                "open_air_share", round(100.0 * self.fly_base_open_share, 1), round(100.0 * open_share, 1), "% Freiluft",
                f"{100.0 * (open_share - self.fly_base_open_share):.1f} %",
                [self.rain_start_id, self.terrace_voc_evt],
                "Regenabtrieb + duftgeschwächte Terrasse verschieben äußere Drosophila-Fliegen Richtung Kronenschutz/Portal.",
                "FLYWIRE_V783",
            )
        elif self.fly_rain_shifted and not self.fly_dispersed_post and weather.rain_mm_h < 0.2 and self.clear_id and open_share >= 0.55:
            self.fly_dispersed_post = True
            self._emit(
                sim_time_s, clk, "INSECT", "POP_DROSOPHILA", "Fliegenpopulation (FlyWire v783)",
                "open_air_share", "<=48 %", round(100.0 * open_share, 1), "% Freiluft", "Wiederverteilung",
                [self.clear_id, self.compost_evt, self.fly_shift_evt],
                "Nach Aufklaren strömen Fliegen wieder stärker in den feuchtwarmen Garten- & Kompost-Luftraum.",
                "FLYWIRE_V783",
            )

        # 6. Vogelreaktionen & reale CPA-Fänge
        rs_bird = next((b for b in birds if b.profile.species_id == "HIRUNDO_RUSTICA"), None)
        if rs_bird is not None:
            if not self.swallow_sheltered and weather.rain_mm_h >= 6.5 and rs_bird.state == "PERCHING":
                self.swallow_sheltered = True
                self._emit(
                    sim_time_s, clk, "BIRD", rs_bird.bird_id, "Rauchschwalbe (RS_01)",
                    "state", "PATROLLING", "PERCHING", "Verhalten", "Dachfirst-Schutzrast",
                    [self.rain_peak_id or self.rain_start_id, self.fly_shift_evt],
                    "Bei Starkregen (>= 6,5 mm/h) + Sichtabfall unterbricht die Rauchschwalbe die freie Luftjagd und sucht ihre Sitzwarte.",
                    "MODELLWERT",
                )
            elif self.swallow_sheltered and not self.swallow_resumed and weather.rain_mm_h < 2.0 and rs_bird.state != "PERCHING":
                self.swallow_resumed = True
                self._emit(
                    sim_time_s, clk, "BIRD", rs_bird.bird_id, "Rauchschwalbe (RS_01)",
                    "state", "PERCHING", rs_bird.state, "Verhalten", "Luftjagd wiederaufgenommen",
                    [self.clear_id, self.fly_shift_evt],
                    "Mit nachlassendem Regen und zurückkehrender Beute nimmt die Rauchschwalbe den Prop-Nav-Jagdflug wieder auf.",
                    "MODELLWERT",
                )

        for ev in bird_events:
            if ev.get("catch"):
                bid = str(ev.get("bird_id", "BIRD"))
                ctx_cause = self.compost_evt or self.fly_shift_evt or self.rain_start_id
                self._emit(
                    sim_time_s, clk, "BIRD", bid, f"Vogel {bid}",
                    "catches", "n", "+1", "Fang", f"Fliege #{ev.get('fly_id')} gefangen (CPA)",
                    [ctx_cause],
                    f"Physische 3D-CPA-Abfangung von Fliege #{ev.get('fly_id')} durch {bid} ohne Skript-Vorgabe.",
                    "MODELLWERT",
                )

    def trace_chain(self, event_id: str) -> Dict[str, Any]:
        """Liefert die vollständige kausale Vorgänger- und Nachfolger-Kette für event_id."""
        target = self._event_map.get(event_id)
        if target is None:
            return {"target": None, "ancestors": [], "descendants": []}

        ancestors: List[CausalEvent] = []
        seen_a = {event_id}
        stack = list(target.cause_event_ids)
        while stack:
            cid = stack.pop(0)
            if cid in seen_a:
                continue
            seen_a.add(cid)
            cev = self._event_map.get(cid)
            if cev:
                ancestors.append(cev)
                stack.extend(cev.cause_event_ids)
        ancestors.sort(key=lambda x: x.sim_time_s)

        descendants = [ev for ev in self.events if event_id in ev.cause_event_ids]
        return {
            "target": asdict(target),
            "ancestors": [asdict(a) for a in ancestors],
            "descendants": [asdict(d) for d in descendants],
        }


class ObservatoryTimeline:
    """Speichert 1-Sekunden-Snapshots der Welt für Time-Scrubbing und Vorher-Nachher-Vergleiche."""

    def __init__(self) -> None:
        self.frames: List[Dict[str, Any]] = []

    def clear(self) -> None:
        self.frames.clear()

    def record_frame(
        self,
        sim_time_s: float,
        weather: Any,
        hydro: Any,
        soil_zones: List[Any],
        plants: List[Any],
        substrates: List[Any],
        fly_pop: Any,
        other_insects: List[Any],
        birds: List[Any],
        world: Any,
        tracker: CausalTracker,
    ) -> Dict[str, Any]:
        recent_cutoff = sim_time_s - 6.0
        recent_ids = sorted([eid for eid, ts in tracker.entity_last_changed_s.items() if ts >= recent_cutoff])

        slots = fly_pop.alive_slots()
        flies_list = [
            {
                "id": f"FLY_{int(fly_pop.fly_ids[s])}",
                "fly_num": int(fly_pop.fly_ids[s]),
                "pos": [round(float(fly_pop.pos[s, 0]), 2), round(float(fly_pop.pos[s, 1]), 2), round(float(fly_pop.pos[s, 2]), 2)],
                "state": fly_pop.state_label[s],
                "energy_mj": round(float(fly_pop.energy_mj[s]), 2),
                "escapes": int(fly_pop.total_escapes[s]),
                "orn_ester": round(float(fly_pop.last_orn_ester[s]), 3),
                "lc4": round(float(fly_pop.last_lc4[s]), 3),
                "dnp01": round(float(fly_pop.last_dnp01[s]), 3),
            }
            for s in slots
        ]
        fz = fly_pop.zone_distribution(world)

        frame = {
            "t_s": round(float(sim_time_s), 2),
            "weather": asdict(weather),
            "grid_moisture_pct": np.round(hydro.moisture_frac * 48.0, 1).tolist(),
            "grid_puddle_mm": np.round(hydro.puddle_mm, 2).tolist(),
            "grid_flow_vx_cms": np.round(hydro.flow_vx_cms, 2).tolist(),
            "grid_flow_vy_cms": np.round(hydro.flow_vy_cms, 2).tolist(),
            "soil_zones": {z.zone_id: asdict(z) for z in soil_zones},
            "plants": {p.plant_id: asdict(p) for p in plants},
            "substrates": {
                s.substrate_id: {
                    "substrate_id": s.substrate_id,
                    "label_de": s.label_de,
                    "zone": s.zone,
                    "pos": list(s.pos),
                    "voc_strength": round(float(s.voc_strength), 3),
                    "base_voc_strength": round(float(s._base_voc_strength), 3),
                    "nutrients": round(float(s.nutrients), 2),
                    "max_nutrients": round(float(s.max_nutrients), 2),
                    "regen_per_s": round(float(s.regen_per_s), 3),
                }
                for s in substrates
            },
            "fly_summary": {
                "alive": fz["total"],
                "indoor": fz["indoor"],
                "canopy": fz["canopy"],
                "open_air": fz["open_air"],
                "births": int(fly_pop.total_births),
                "captured": int(fly_pop.total_captured),
                "escapes": int(fly_pop.total_escapes.sum()),
                "spikes": int(fly_pop.total_flywire_spikes),
            },
            "flies": flies_list,
            "other_insects": {i.insect_id: asdict(i) for i in other_insects},
            "birds": {
                b.bird_id: {
                    "bird_id": b.bird_id,
                    "species_id": b.profile.species_id,
                    "common_name_de": b.profile.common_name_de,
                    "scientific_name": b.profile.scientific_name,
                    "gbif_occ_ref": b.profile.gbif_taxon_key,
                    "pos": [round(float(x), 2) for x in b.pos],
                    "vel": [round(float(x), 2) for x in b.vel],
                    "heading": [round(float(x), 3) for x in b.heading],
                    "speed_mps": round(float(np.linalg.norm(b.vel)), 2),
                    "state": b.state,
                    "energy_j": round(float(b.energy_j), 2),
                    "energy_max_j": round(float(b.profile.energy_max_j), 2),
                    "catches": int(b.catches),
                    "missed_strikes": int(b.missed_strikes),
                    "detections": int(b.detections),
                    "locked_fly_id": b.target_fly_id,
                }
                for b in birds
            },
            "recent_change_ids": recent_ids,
            "event_count": len(tracker.events),
        }
        self.frames.append(frame)
        return frame

    def get_frame(self, t_s: Optional[float] = None) -> Optional[Dict[str, Any]]:
        if not self.frames:
            return None
        if t_s is None:
            return self.frames[-1]
        best = min(self.frames, key=lambda f: abs(f["t_s"] - float(t_s)))
        return best

    def compute_diff(
        self,
        t1_s: float,
        t2_s: float,
        tracker: CausalTracker,
        entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        f1 = self.get_frame(t1_s)
        f2 = self.get_frame(t2_s)
        if f1 is None or f2 is None:
            return {"error": "Keine Zeitreihen-Frames vorhanden"}
        if f1["t_s"] > f2["t_s"]:
            f1, f2 = f2, f1

        m1 = np.asarray(f1["grid_moisture_pct"], dtype=np.float32)
        m2 = np.asarray(f2["grid_moisture_pct"], dtype=np.float32)
        p1 = np.asarray(f1["grid_puddle_mm"], dtype=np.float32)
        p2 = np.asarray(f2["grid_puddle_mm"], dtype=np.float32)

        zone_diffs = {}
        for zid, z2 in f2["soil_zones"].items():
            z1 = f1["soil_zones"][zid]
            zone_diffs[zid] = {
                "label_de": z2["label_de"],
                "moisture_t1": z1["soil_moisture_pct"],
                "moisture_t2": z2["soil_moisture_pct"],
                "delta_moisture_pct": round(z2["soil_moisture_pct"] - z1["soil_moisture_pct"], 2),
                "puddle_t1": z1["puddle_depth_mm"],
                "puddle_t2": z2["puddle_depth_mm"],
                "delta_puddle_mm": round(z2["puddle_depth_mm"] - z1["puddle_depth_mm"], 2),
                "flow_t1": z1["flow_speed_cms"],
                "flow_t2": z2["flow_speed_cms"],
            }

        plant_diffs = {}
        for pid, p2d in f2["plants"].items():
            p1d = f1["plants"][pid]
            plant_diffs[pid] = {
                "label_de": p2d["label_de"],
                "wetness_t1": p1d["foliage_wetness"],
                "wetness_t2": p2d["foliage_wetness"],
                "delta_wetness": round(p2d["foliage_wetness"] - p1d["foliage_wetness"], 3),
                "turgor_t1": p1d["turgor_index"],
                "turgor_t2": p2d["turgor_index"],
                "delta_turgor": round(p2d["turgor_index"] - p1d["turgor_index"], 3),
                "nectar_t1": p1d["nectar_mg"],
                "nectar_t2": p2d["nectar_mg"],
                "delta_nectar_mg": round(p2d["nectar_mg"] - p1d["nectar_mg"], 2),
            }

        sub_diffs = {}
        for sid, s2d in f2["substrates"].items():
            s1d = f1["substrates"][sid]
            sub_diffs[sid] = {
                "label_de": s2d["label_de"],
                "voc_t1": s1d["voc_strength"],
                "voc_t2": s2d["voc_strength"],
                "delta_voc": round(s2d["voc_strength"] - s1d["voc_strength"], 3),
                "nutrients_t1": s1d["nutrients"],
                "nutrients_t2": s2d["nutrients"],
            }

        bird_diffs = {}
        for bid, b2d in f2["birds"].items():
            b1d = f1["birds"][bid]
            bird_diffs[bid] = {
                "common_name_de": b2d["common_name_de"],
                "state_t1": b1d["state"],
                "state_t2": b2d["state"],
                "delta_catches": b2d["catches"] - b1d["catches"],
                "delta_misses": b2d["missed_strikes"] - b1d["missed_strikes"],
                "delta_energy_j": round(b2d["energy_j"] - b1d["energy_j"], 2),
            }

        ev_between = [
            asdict(e) for e in tracker.events
            if f1["t_s"] < e.sim_time_s <= f2["t_s"]
        ]

        selected_rows: List[Dict[str, Any]] = []
        if entity_id:
            if entity_id in zone_diffs:
                zd = zone_diffs[entity_id]
                selected_rows = [
                    {"metric": "Bodenfeuchte", "t1": zd["moisture_t1"], "t2": zd["moisture_t2"], "delta": zd["delta_moisture_pct"], "unit": "% Vol."},
                    {"metric": "Pfützentiefe", "t1": zd["puddle_t1"], "t2": zd["puddle_t2"], "delta": zd["delta_puddle_mm"], "unit": "mm"},
                    {"metric": "Wasserfluss", "t1": zd["flow_t1"], "t2": zd["flow_t2"], "delta": round(zd["flow_t2"] - zd["flow_t1"], 2), "unit": "cm/s"},
                ]
            elif entity_id in plant_diffs:
                pd = plant_diffs[entity_id]
                selected_rows = [
                    {"metric": "Blattnässe", "t1": pd["wetness_t1"], "t2": pd["wetness_t2"], "delta": pd["delta_wetness"], "unit": "Index"},
                    {"metric": "Turgor", "t1": pd["turgor_t1"], "t2": pd["turgor_t2"], "delta": pd["delta_turgor"], "unit": "Index"},
                    {"metric": "Nektar", "t1": pd["nectar_t1"], "t2": pd["nectar_t2"], "delta": pd["delta_nectar_mg"], "unit": "mg"},
                ]
            elif entity_id in sub_diffs:
                sd = sub_diffs[entity_id]
                selected_rows = [
                    {"metric": "VOC-Duftstärke", "t1": sd["voc_t1"], "t2": sd["voc_t2"], "delta": sd["delta_voc"], "unit": "Rel."},
                    {"metric": "Nährstoffvorrat", "t1": sd["nutrients_t1"], "t2": sd["nutrients_t2"], "delta": round(sd["nutrients_t2"] - sd["nutrients_t1"], 2), "unit": "mg"},
                ]
            elif entity_id in bird_diffs:
                bd = bird_diffs[entity_id]
                selected_rows = [
                    {"metric": "Verhalten", "t1": bd["state_t1"], "t2": bd["state_t2"], "delta": "geändert" if bd["state_t1"] != bd["state_t2"] else "unverändert", "unit": ""},
                    {"metric": "Fänge", "t1": f1["birds"][entity_id]["catches"], "t2": f2["birds"][entity_id]["catches"], "delta": bd["delta_catches"], "unit": "Stk"},
                    {"metric": "Energie", "t1": f1["birds"][entity_id]["energy_j"], "t2": f2["birds"][entity_id]["energy_j"], "delta": bd["delta_energy_j"], "unit": "J"},
                ]

        return {
            "t1_s": f1["t_s"],
            "t2_s": f2["t_s"],
            "clock_t1": f1["weather"]["clock_str"],
            "clock_t2": f2["weather"]["clock_str"],
            "weather_delta": {
                "rain_mm_h_t1": f1["weather"]["rain_mm_h"],
                "rain_mm_h_t2": f2["weather"]["rain_mm_h"],
                "cum_rain_delta_mm": round(f2["weather"]["cumulative_rain_mm"] - f1["weather"]["cumulative_rain_mm"], 3),
                "temp_delta_c": round(f2["weather"]["temperature_c"] - f1["weather"]["temperature_c"], 2),
                "humidity_delta_pct": round(f2["weather"]["humidity_pct"] - f1["weather"]["humidity_pct"], 1),
            },
            "grid_delta_moisture_pct": np.round(m2 - m1, 2).tolist(),
            "grid_delta_puddle_mm": np.round(p2 - p1, 2).tolist(),
            "zone_diffs": zone_diffs,
            "plant_diffs": plant_diffs,
            "substrate_diffs": sub_diffs,
            "bird_diffs": bird_diffs,
            "fly_delta": {
                "alive_t1": f1["fly_summary"]["alive"],
                "alive_t2": f2["fly_summary"]["alive"],
                "delta_alive": f2["fly_summary"]["alive"] - f1["fly_summary"]["alive"],
                "open_air_delta": f2["fly_summary"]["open_air"] - f1["fly_summary"]["open_air"],
                "canopy_delta": f2["fly_summary"]["canopy"] - f1["fly_summary"]["canopy"],
                "indoor_delta": f2["fly_summary"]["indoor"] - f1["fly_summary"]["indoor"],
                "new_captures": f2["fly_summary"]["captured"] - f1["fly_summary"]["captured"],
                "new_escapes": f2["fly_summary"]["escapes"] - f1["fly_summary"]["escapes"],
            },
            "selected_entity_id": entity_id,
            "selected_entity_rows": selected_rows,
            "events_in_window": ev_between,
        }
