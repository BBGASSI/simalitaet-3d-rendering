# -*- coding: utf-8 -*-
"""
Dynamische Umwelt-, Hydrologie-, Vegetations- und Sekundärinsekten-Engine
für das SIMALITÄT Ökosystem-Observatorium (Seestraße 43, Wölfersheim).

Verbindet:
- Wetter- & Jahreszeitenmodell (inkl. Regenzyklus, Trocken-Kontrolle, Starkregen)
- Physikalisches 18x18-Hydrologie-Raster (Bodenfeuchte [% Vol.], Pfützen [mm],
  Dachtraufen-Abfluss, Laubkronen-Interzeption und hangabwärtige Wasserströmung [cm/s])
- 8 klickbare Pflanzenindividuen (Blattnässe, verzögerter Turgor, Nektar & Vitalität)
- Substrat-/Lebensraum-Rückkopplung (Terrasse-Auswaschung vs. Kompost-Aktivität vs. Küche)
- 8 klickbare Sekundärinsekten auf Wölfersheimer GBIF-Basis (Bombus pascuorum, Carabus auratus)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .ecosystem_world import Seestrasse43EcosystemWorld


SEASON_PRESETS: Dict[str, Dict[str, float]] = {
    "FRUEHLING": {"temp_base_c": 14.5, "uv_peak": 0.88, "soil_init": 0.34, "lush_base": 0.74, "evap_mult": 0.85},
    "SOMMER":    {"temp_base_c": 21.0, "uv_peak": 1.00, "soil_init": 0.22, "lush_base": 0.82, "evap_mult": 1.15},
    "HERBST":    {"temp_base_c": 11.5, "uv_peak": 0.70, "soil_init": 0.40, "lush_base": 0.58, "evap_mult": 0.65},
    "WINTER":    {"temp_base_c": 3.5,  "uv_peak": 0.45, "soil_init": 0.46, "lush_base": 0.30, "evap_mult": 0.35},
}


def format_sim_clock(clock_hour: float) -> str:
    h_tot = clock_hour % 24.0
    hh = int(h_tot)
    mm = int((h_tot - hh) * 60.0)
    return f"{hh:02d}:{mm:02d}"


@dataclass
class WeatherState:
    sim_time_s: float
    scenario: str
    season: str
    clock_hour: float
    clock_str: str
    regime: str                 # "KLAR", "BEWOELKT", "REGEN", "AUFKLAREND"
    rain_mm_h: float
    temperature_c: float
    humidity_pct: float
    cloud_cover_pct: float
    wind_speed_mps: float
    daylight_uv_factor: float
    rain_vis_factor: float
    cumulative_rain_mm: float


class WeatherAndSeasonEngine:
    """Erzeugt deterministische Wetter-, Niederschlags- und Tageszeitverläufe."""

    def __init__(self, scenario: str = "REGENZYKLUS", season: str = "SOMMER", start_hour: float = 13.5) -> None:
        self.scenario = scenario.upper()
        self.season = season.upper() if season.upper() in SEASON_PRESETS else "SOMMER"
        self.start_hour = float(start_hour)
        self.cumulative_rain_mm: float = 0.0
        self.current = self._eval_state(0.0, 0.0)

    def reset(self, scenario: Optional[str] = None, season: Optional[str] = None) -> None:
        if scenario is not None:
            self.scenario = scenario.upper()
        if season is not None and season.upper() in SEASON_PRESETS:
            self.season = season.upper()
        self.cumulative_rain_mm = 0.0
        self.current = self._eval_state(0.0, 0.0)

    def _eval_state(self, t_s: float, dt_s: float) -> WeatherState:
        sp = SEASON_PRESETS[self.season]
        # Zeitkompression für beobachtbare Tageszeitänderung: 1,5 Sim-Minuten pro Simulationssekunde
        clock_hour = (self.start_hour + t_s * 1.5 / 60.0) % 24.0
        solar_elev = max(0.0, math.sin(math.pi * np.clip((clock_hour - 6.0) / 15.0, 0.0, 1.0)))
        diurnal_temp = sp["temp_base_c"] + 2.2 * solar_elev - 1.2

        rain_mm_h = 0.0
        clouds = 18.0
        rh = 54.0
        wind = 0.36
        temp_drop = 0.0
        regime = "KLAR"

        if self.scenario == "TROCKEN_KONTROLLE":
            clouds = 18.0 + 4.0 * math.sin(t_s * 0.04)
            rh = 53.0 - 3.0 * solar_elev
            wind = 0.36 + 0.06 * math.sin(t_s * 0.09)
            regime = "KLAR"
        elif self.scenario == "STARKREGEN":
            if t_s < 16.0:
                regime, clouds, rh = "KLAR", 22.0, 56.0
            elif t_s < 26.0:
                frac = (t_s - 16.0) / 10.0
                regime = "BEWOELKT"
                clouds = 22.0 + 70.0 * frac
                rh = 56.0 + 26.0 * frac
                wind = 0.36 + 1.4 * frac
                rain_mm_h = 0.8 * frac
            elif t_s <= 66.0:
                phase = (t_s - 26.0) / 40.0
                envelope = math.sin(math.pi * phase) ** 1.05
                inertia_env = math.sin(math.pi * min(0.75, phase * 0.75))
                rain_mm_h = 22.0 * envelope
                clouds = 94.0
                rh = 82.0 + 13.0 * inertia_env
                wind = 1.6 + 1.2 * envelope
                temp_drop = 4.2 * inertia_env
                regime = "REGEN" if rain_mm_h >= 0.4 else "AUFKLAREND"
            else:
                decay = math.exp(-(t_s - 66.0) / 28.0)
                clouds = 25.0 + 69.0 * decay
                rh = 64.0 + 27.2 * decay
                wind = 0.42 + 1.18 * decay
                temp_drop = 2.97 * decay
                regime = "AUFKLAREND" if clouds > 45.0 else "KLAR"
        else:  # Standard REGENZYKLUS
            if t_s < 18.0:
                regime, clouds, rh = "KLAR", 20.0, 54.0
            elif t_s < 28.0:
                frac = (t_s - 18.0) / 10.0
                regime = "BEWOELKT"
                clouds = 20.0 + 68.0 * frac
                rh = 54.0 + 23.0 * frac
                wind = 0.38 + 0.85 * frac
                rain_mm_h = 0.35 * frac
            elif t_s <= 64.0:
                phase = (t_s - 28.0) / 36.0
                envelope = math.sin(math.pi * phase) ** 1.1
                inertia_env = math.sin(math.pi * min(0.75, phase * 0.75))
                rain_mm_h = 11.8 * envelope
                clouds = 90.0
                rh = 77.0 + 16.0 * inertia_env
                wind = 1.15 + 0.75 * envelope
                temp_drop = 3.2 * inertia_env
                regime = "REGEN" if rain_mm_h >= 0.35 else "AUFKLAREND"
            else:
                decay = math.exp(-(t_s - 64.0) / 26.0)
                clouds = 22.0 + 68.0 * decay
                rh = 60.0 + 28.3 * decay
                wind = 0.40 + 0.75 * decay
                temp_drop = 2.26 * decay
                regime = "AUFKLAREND" if clouds > 44.0 else "KLAR"

        # Konsistente Hydrologie-Zeitskalierung (36x) für mm Niederschlagssumme
        self.cumulative_rain_mm += rain_mm_h * ((dt_s * 36.0) / 3600.0)
        uv_factor = float(np.clip(sp["uv_peak"] * (0.28 + 0.72 * solar_elev) * (1.0 - 0.62 * (clouds / 100.0)), 0.12, 1.0))
        vis_factor = float(np.clip(1.0 - 0.036 * min(12.0, rain_mm_h) - 0.10 * max(0.0, (clouds - 60.0) / 40.0), 0.42, 1.0))

        return WeatherState(
            sim_time_s=round(t_s, 3),
            scenario=self.scenario,
            season=self.season,
            clock_hour=round(clock_hour, 4),
            clock_str=format_sim_clock(clock_hour),
            regime=regime,
            rain_mm_h=round(float(rain_mm_h), 3),
            temperature_c=round(float(diurnal_temp - temp_drop), 2),
            humidity_pct=round(float(np.clip(rh, 20.0, 99.0)), 1),
            cloud_cover_pct=round(float(np.clip(clouds, 0.0, 100.0)), 1),
            wind_speed_mps=round(float(wind), 2),
            daylight_uv_factor=round(uv_factor, 3),
            rain_vis_factor=round(vis_factor, 3),
            cumulative_rain_mm=round(float(self.cumulative_rain_mm), 3),
        )

    def step(self, world: Seestrasse43EcosystemWorld, dt_s: float) -> WeatherState:
        self.current = self._eval_state(world.sim_time_s, dt_s)
        w = self.current
        world.rain_mm_h = w.rain_mm_h
        world.temperature_c = w.temperature_c
        world.humidity_pct = w.humidity_pct
        world.cloud_cover_pct = w.cloud_cover_pct
        world.wind_speed_mps = w.wind_speed_mps
        world.rain_vis_factor = w.rain_vis_factor
        world.daylight_uv_factor = w.daylight_uv_factor
        world.season = w.season
        world.clock_hour = w.clock_hour
        return w


@dataclass
class SoilZoneState:
    zone_id: str
    label_de: str
    center: Tuple[float, float]
    radius_m: float
    is_indoor: bool
    soil_moisture_pct: float
    puddle_depth_mm: float
    flow_speed_cms: float
    infiltration_mm_h: float


class HydrologyGrid:
    """Physikalisches 18x18-Hydrologie- & Wasserbewegungsraster rund um Seestraße 43."""

    NX: int = 18
    NY: int = 18
    CELL_SIZE_M: float = 2.0

    def __init__(self, world: Seestrasse43EcosystemWorld, season: str = "SOMMER") -> None:
        self.x_min = world.BOUNDS_MIN[0]
        self.y_min = world.BOUNDS_MIN[1]
        self.xs = self.x_min + (np.arange(self.NX) + 0.5) * self.CELL_SIZE_M
        self.ys = self.y_min + (np.arange(self.NY) + 0.5) * self.CELL_SIZE_M
        xx, yy = np.meshgrid(self.xs, self.ys)  # shape (18, 18)

        # Hausdach- & Dachtraufen-Maske
        in_main = (xx >= 0.0) & (xx <= 11.0) & (yy >= 0.0) & (yy <= 9.0)
        in_annex = (xx >= 5.5) & (xx <= 10.0) & (yy >= 9.0) & (yy <= 12.5)
        self.roof_mask = in_main | in_annex
        self.eave_mask = (
            (~self.roof_mask)
            & (
                ((xx >= 0.0) & (xx <= 11.5) & (yy >= -2.5) & (yy < 0.0))
                | ((xx > 11.0) & (xx <= 13.0) & (yy >= -1.0) & (yy <= 9.5))
            )
        )

        # Kronenbedeckung auf Bodenzellenhöhe
        pts_3d = np.stack([xx.ravel(), yy.ravel(), np.full(xx.size, 3.8)], axis=-1)
        self.canopy_grid = world.max_canopy_density_vec(pts_3d).reshape(self.NY, self.NX)
        pts_low = np.stack([xx.ravel(), yy.ravel(), np.full(xx.size, 1.5)], axis=-1)
        self.canopy_grid = np.maximum(self.canopy_grid, world.max_canopy_density_vec(pts_low).reshape(self.NY, self.NX))

        # Mikro-Topographie (Hangneigung Süd-Südost + lokale Mulden bei Terrasse, Apfelbaum, Kompost)
        terrace_basin = 0.24 * np.exp(-((xx - 3.5) ** 2 + (yy + 3.5) ** 2) / 14.0)
        apple_hollow = 0.20 * np.exp(-((xx + 4.5) ** 2 + (yy + 5.0) ** 2) / 10.0)
        compost_hollow = 0.16 * np.exp(-((xx - 14.0) ** 2 + (yy - 5.5) ** 2) / 11.0)
        slope = 0.018 * (yy - 2.0) - 0.008 * (xx - 5.0)
        self.elevation_m = (146.15 + slope - terrace_basin - apple_hollow - compost_hollow).astype(np.float32)

        # Boden-Infiltrationsrate [mm/h] (Terrasse stark verdichtet, Kompost/Wiese durchlässig)
        self.infiltration_mm_h = np.full((self.NY, self.NX), 8.5, dtype=np.float32)
        terrace_plate = (xx >= 0.5) & (xx <= 7.5) & (yy >= -5.5) & (yy <= -0.2)
        self.infiltration_mm_h[terrace_plate] = 3.2
        self.infiltration_mm_h[self.eave_mask] = 4.0
        compost_zone = (xx >= 11.5) & (xx <= 16.5) & (yy >= 3.5) & (yy <= 8.0)
        self.infiltration_mm_h[compost_zone] = 12.5
        self.infiltration_mm_h[self.roof_mask] = 0.0

        self.xx = xx.astype(np.float32)
        self.yy = yy.astype(np.float32)
        self.season = season
        self.moisture_frac = np.zeros((self.NY, self.NX), dtype=np.float32)
        self.puddle_mm = np.zeros((self.NY, self.NX), dtype=np.float32)
        self.flow_vx_cms = np.zeros((self.NY, self.NX), dtype=np.float32)
        self.flow_vy_cms = np.zeros((self.NY, self.NX), dtype=np.float32)
        self.zone_specs = self._build_zone_specs()
        self.reset(season)

    @staticmethod
    def _build_zone_specs() -> List[Dict[str, Any]]:
        return [
            {"id": "SOIL_TERRACE_SOUTH", "label": "Südterrasse & Pflaster", "center": (3.5, -3.5), "r": 2.6, "indoor": False},
            {"id": "SOIL_ROOF_EAVE_S", "label": "Dachtraufe Süd", "center": (6.0, -1.0), "r": 2.2, "indoor": False},
            {"id": "SOIL_APPLE_HOLLOW", "label": "Mulde am Apfelbaum (SW)", "center": (-4.5, -5.0), "r": 2.8, "indoor": False},
            {"id": "SOIL_COMPOST_EAST", "label": "Kompost & Beet (Ost)", "center": (13.8, 5.5), "r": 2.5, "indoor": False},
            {"id": "SOIL_LAWN_WEST", "label": "Westrasen an Hecke", "center": (-5.5, 3.0), "r": 2.8, "indoor": False},
            {"id": "SOIL_INDOOR_FLOOR", "label": "Innenboden Küche (Seestr. 43)", "center": (6.0, 4.0), "r": 2.5, "indoor": True},
        ]

    def reset(self, season: str = "SOMMER") -> None:
        self.season = season
        base_m = SEASON_PRESETS.get(season, SEASON_PRESETS["SOMMER"])["soil_init"]
        self.moisture_frac.fill(base_m)
        self.moisture_frac[self.roof_mask] = 0.0
        self.puddle_mm.fill(0.0)
        self.flow_vx_cms.fill(0.0)
        self.flow_vy_cms.fill(0.0)

    def step(self, dt_s: float, weather: WeatherState) -> None:
        # Kompressionsfaktor für sichtbare Hydrologie innerhalb eines 90-120s-Regenzyklus ([MODEL_VALUE])
        hydro_scale = 36.0
        dt_h = (dt_s * hydro_scale) / 3600.0
        out = ~self.roof_mask

        # 1. Effektiver Niederschlag (Kronen-Interzeption + Dachtraufen-Zulauf)
        throughfall = weather.rain_mm_h * (1.0 - 0.52 * self.canopy_grid)
        eff_rain = np.where(out, throughfall, 0.0).astype(np.float32)
        if weather.rain_mm_h > 0.05:
            roof_cells = float(self.roof_mask.sum())
            eave_cells = max(1.0, float(self.eave_mask.sum()))
            eave_bonus = weather.rain_mm_h * (0.48 * roof_cells / eave_cells)
            eff_rain[self.eave_mask] += eave_bonus

        # 2. Infiltration & Sättigung -> Pfützenbildung [mm]
        avail_water_mm = self.puddle_mm + eff_rain * float(dt_h) * 2.4
        wet_capacity_factor = np.maximum(0.15, 1.0 - self.moisture_frac * 0.85)
        max_infil_mm = self.infiltration_mm_h * wet_capacity_factor * float(dt_h) * 2.2
        infil_mm = np.minimum(avail_water_mm, max_infil_mm)
        infil_mm[self.roof_mask] = 0.0

        self.puddle_mm = np.maximum(0.0, avail_water_mm - infil_mm)
        self.puddle_mm[self.roof_mask] = 0.0

        evap_mult = SEASON_PRESETS.get(self.season, SEASON_PRESETS["SOMMER"])["evap_mult"]
        evap_mm = (
            max(0.0, 1.8 * evap_mult * weather.daylight_uv_factor * max(0.1, (100.0 - weather.humidity_pct) / 50.0))
            * float(dt_h)
        )
        self.puddle_mm = np.maximum(0.0, self.puddle_mm - evap_mm)

        # Bodenfeuchte-Update (%-Fraktion 0..1, Anzeige als soil_moisture * 48 % Vol.; Top-30-mm-Schicht)
        self.moisture_frac[out] += infil_mm[out] * 0.068 - (0.014 * evap_mm * self.moisture_frac[out])
        # Langsame Tiefensickerung bei Übersättigung
        drain = np.maximum(0.0, self.moisture_frac - 0.58) * 0.12 * float(dt_s)
        self.moisture_frac[out] -= drain[out]
        np.clip(self.moisture_frac, 0.08, 0.96, out=self.moisture_frac)
        self.moisture_frac[self.roof_mask] = 0.0

        # 3. Oberflächlicher Wasserfluss nach Mikro-Topographie (Elevation + Pfützenhöhe)
        head = self.elevation_m + self.puddle_mm * 0.004
        dh_dx = np.zeros_like(head)
        dh_dy = np.zeros_like(head)
        dh_dx[:, 1:-1] = (head[:, :-2] - head[:, 2:]) / (2.0 * self.CELL_SIZE_M)
        dh_dy[1:-1, :] = (head[:-2, :] - head[2:, :]) / (2.0 * self.CELL_SIZE_M)

        active_flow = out & (self.puddle_mm > 0.35)
        self.flow_vx_cms = np.where(active_flow, np.clip(dh_dx * 34.0, -9.0, 9.0), 0.0).astype(np.float32)
        self.flow_vy_cms = np.where(active_flow, np.clip(dh_dy * 34.0, -9.0, 9.0), 0.0).astype(np.float32)

        # Advektiver Pfützen-Ausgleich zu niedrigerem Nachbarfeld
        if np.any(active_flow):
            flux_scale = float(np.clip(0.18 * dt_s * 12.0, 0.0, 0.28))
            move_amt = np.where(active_flow, self.puddle_mm * flux_scale, 0.0)
            inflow = np.zeros_like(self.puddle_mm)
            go_r = move_amt * (self.flow_vx_cms > 0.15)
            go_l = move_amt * (self.flow_vx_cms < -0.15)
            go_u = move_amt * (self.flow_vy_cms > 0.15)
            go_d = move_amt * (self.flow_vy_cms < -0.15)
            inflow[:, 1:] += go_r[:, :-1] * 0.5
            inflow[:, :-1] += go_l[:, 1:] * 0.5
            inflow[1:, :] += go_u[:-1, :] * 0.5
            inflow[:-1, :] += go_d[1:, :] * 0.5
            outflow = (go_r + go_l + go_u + go_d) * 0.5
            self.puddle_mm = np.maximum(0.0, self.puddle_mm - outflow + inflow)
            self.puddle_mm[self.roof_mask] = 0.0

    def sample_at(self, x: float, y: float) -> Tuple[float, float, float]:
        """Liefert (Bodenfeuchte [% Vol.], Pfützentiefe [mm], Fließgeschwindigkeit [cm/s]) an (x, y)."""
        ix = int(np.clip((x - self.x_min) / self.CELL_SIZE_M, 0, self.NX - 1))
        iy = int(np.clip((y - self.y_min) / self.CELL_SIZE_M, 0, self.NY - 1))
        moist_pct = float(self.moisture_frac[iy, ix] * 48.0)
        pud = float(self.puddle_mm[iy, ix])
        spd = math.hypot(float(self.flow_vx_cms[iy, ix]), float(self.flow_vy_cms[iy, ix]))
        return moist_pct, pud, spd

    def summarize_zones(self) -> List[SoilZoneState]:
        zones: List[SoilZoneState] = []
        for zs in self.zone_specs:
            cx, cy = zs["center"]
            if zs["indoor"]:
                zones.append(
                    SoilZoneState(
                        zone_id=zs["id"],
                        label_de=zs["label"],
                        center=zs["center"],
                        radius_m=zs["r"],
                        is_indoor=True,
                        soil_moisture_pct=0.0,
                        puddle_depth_mm=0.0,
                        flow_speed_cms=0.0,
                        infiltration_mm_h=0.0,
                    )
                )
                continue
            d2 = (self.xx - cx) ** 2 + (self.yy - cy) ** 2
            mask = (d2 <= zs["r"] ** 2) & (~self.roof_mask)
            if not np.any(mask):
                m_pct, pud, fspd = self.sample_at(cx, cy)
                inf = 5.0
            else:
                m_pct = float(self.moisture_frac[mask].mean() * 48.0)
                pud = float(self.puddle_mm[mask].mean())
                fspd = float(np.hypot(self.flow_vx_cms[mask], self.flow_vy_cms[mask]).mean())
                inf = float(self.infiltration_mm_h[mask].mean())
            zones.append(
                SoilZoneState(
                    zone_id=zs["id"],
                    label_de=zs["label"],
                    center=zs["center"],
                    radius_m=zs["r"],
                    is_indoor=False,
                    soil_moisture_pct=round(m_pct, 2),
                    puddle_depth_mm=round(pud, 2),
                    flow_speed_cms=round(fspd, 2),
                    infiltration_mm_h=round(inf, 1),
                )
            )
        return zones


@dataclass
class PlantEntity:
    plant_id: str
    label_de: str
    species_ref: str
    gbif_occ_ref: int
    kind: str                   # "tree", "shrub", "meadow", "herb"
    pos: Tuple[float, float, float]
    radius_m: float
    canopy_shelter: float
    foliage_wetness: float      # 0..1
    turgor_index: float         # 0..1 (verzögerte Wurzelantwort!)
    lushness_index: float       # 0..1
    nectar_mg: float
    max_nectar_mg: float
    nectar_regen_mg_s: float
    stomatal_conductance: float
    local_soil_moisture_pct: float


class VegetationManager:
    """Steuert physiologische Pflanzenreaktionen auf Niederschlag, Bodenfeuchte & UV-Licht."""

    def __init__(self, world: Seestrasse43EcosystemWorld, hydro: HydrologyGrid) -> None:
        self.plants: List[PlantEntity] = []
        self.reset(world, hydro)

    def reset(self, world: Seestrasse43EcosystemWorld, hydro: HydrologyGrid) -> None:
        gb = world.gbif_extended_records
        season = hydro.season
        lush0 = SEASON_PRESETS.get(season, SEASON_PRESETS["SOMMER"])["lush_base"]
        specs = [
            ("PLANT_APPLE_TREE", "Apfelbaum (SW)", "Malus domestica", 0, "tree", (-4.5, -5.0, 4.1), 3.2, 0.72, 18.0, 0.55),
            ("PLANT_PLUM_TREE", "Pflaumenbaum (SE)", "Prunus padus", gb.get("Prunus padus", {}).get("total_count", 0), "tree", (15.5, -4.5, 4.5), 3.4, 0.70, 16.0, 0.50),
            ("PLANT_BERRY_HEDGE", "Holunderhecke (West)", "Sambucus ebulus", gb.get("Sambucus ebulus", {}).get("total_count", 0), "shrub", (-6.0, 5.0, 1.6), 2.8, 0.78, 22.0, 0.70),
            ("PLANT_FLOWER_BED_SW", "Gundermann-Blühstreifen", "Glechoma hederacea", gb.get("Glechoma hederacea", {}).get("total_count", 0), "herb", (-1.5, -7.5, 0.4), 2.2, 0.15, 28.0, 0.90),
            ("PLANT_LAWN_SOUTH", "Südrasen-Grasfläche", "Eragrostis minor", gb.get("Eragrostis minor", {}).get("total_count", 0), "meadow", (7.0, -7.0, 0.2), 2.8, 0.05, 4.0, 0.10),
            ("PLANT_LAWN_EAST", "Ost-Gartenwiese", "Avena sativa", gb.get("Avena sativa", {}).get("total_count", 0), "meadow", (15.0, 1.5, 0.2), 2.6, 0.05, 6.0, 0.15),
            ("PLANT_TERRACE_HERBS", "Terrassen-Kräuterbeet", "Thymus / Salvia (Modell)", 0, "herb", (0.5, -2.5, 0.5), 1.5, 0.10, 14.0, 0.45),
            ("PLANT_MOSS_NORTH", "Nordwand-Schattenmoos", "Bryophyta (Modell)", 0, "meadow", (2.5, 10.5, 0.2), 2.0, 0.20, 0.5, 0.02),
        ]
        self.plants.clear()
        for pid, lbl, sp, occ, kind, pos, rad, shelt, max_n, nreg in specs:
            m_pct, _, _ = hydro.sample_at(pos[0], pos[1])
            t0 = float(np.clip(0.32 + 0.032 * m_pct, 0.25, 0.92))
            self.plants.append(
                PlantEntity(
                    plant_id=pid,
                    label_de=lbl,
                    species_ref=sp,
                    gbif_occ_ref=int(occ),
                    kind=kind,
                    pos=pos,
                    radius_m=rad,
                    canopy_shelter=shelt,
                    foliage_wetness=0.0,
                    turgor_index=round(t0, 3),
                    lushness_index=round(float(np.clip(0.55 * t0 + 0.45 * lush0, 0.15, 0.95)), 3),
                    nectar_mg=round(0.65 * max_n, 2),
                    max_nectar_mg=max_n,
                    nectar_regen_mg_s=nreg,
                    stomatal_conductance=round(0.68 * lush0, 3),
                    local_soil_moisture_pct=round(m_pct, 2),
                )
            )

    def step(self, dt_s: float, weather: WeatherState, hydro: HydrologyGrid, world: Seestrasse43EcosystemWorld) -> None:
        lush0 = SEASON_PRESETS.get(weather.season, SEASON_PRESETS["SOMMER"])["lush_base"]
        evap_mult = SEASON_PRESETS.get(weather.season, SEASON_PRESETS["SOMMER"])["evap_mult"]

        for pl in self.plants:
            m_pct, _, _ = hydro.sample_at(pl.pos[0], pl.pos[1])
            pl.local_soil_moisture_pct = round(m_pct, 2)

            # 1. Blattnässe sofort bei Niederschlag, Trocknung über Sonne & Wind
            wet = pl.foliage_wetness + (weather.rain_mm_h * 0.045 - 0.015 * evap_mult * weather.daylight_uv_factor * (0.6 + 0.4 * weather.wind_speed_mps)) * dt_s
            pl.foliage_wetness = round(float(np.clip(wet, 0.0, 1.0)), 3)

            # 2. Turgor folgt der lokalen Bodenfeuchte physiologisch verzögert (tau ~ 14s)!
            target_turgor = float(np.clip(0.34 + 0.036 * m_pct, 0.22, 0.98))
            alpha_t = min(1.0, dt_s / 14.0)
            pl.turgor_index = round(pl.turgor_index + alpha_t * (target_turgor - pl.turgor_index), 4)

            # 3. Stomatäre Leitfähigkeit & Vitalität
            stoma_target = float(np.clip(weather.daylight_uv_factor * pl.turgor_index * (1.0 - 0.30 * pl.foliage_wetness), 0.05, 1.0))
            pl.stomatal_conductance = round(pl.stomatal_conductance + min(1.0, dt_s / 5.0) * (stoma_target - pl.stomatal_conductance), 3)
            pl.lushness_index = round(float(np.clip(0.58 * pl.turgor_index + 0.42 * lush0 - 0.08 * max(0.0, pl.foliage_wetness - 0.8), 0.12, 0.99)), 3)

            # 4. Nektar-Auswaschung bei Starkregen & gesteigerter Nachschub bei guter Wasserversorgung
            wash = (0.045 * max(0.0, weather.rain_mm_h - 1.5)) * (1.0 - 0.65 * pl.canopy_shelter)
            regen = pl.nectar_regen_mg_s * pl.turgor_index * max(0.25, weather.daylight_uv_factor)
            pl.nectar_mg = round(float(np.clip(pl.nectar_mg + (regen - wash) * dt_s, 0.05, pl.max_nectar_mg)), 3)

        # Substrate an Wetter & Bodenfeuchte koppeln (Küche bleibt komplett stabil!)
        m_compost, _, _ = hydro.sample_at(13.5, 5.5)
        for sub_s in world.substrates:
            if sub_s.substrate_id == "SUB_INDOOR_KITCHEN":
                sub_s.voc_strength = sub_s._base_voc_strength
                sub_s.regen_per_s = sub_s._base_regen_per_s
            elif sub_s.substrate_id == "SUB_TERRACE_FRUIT":
                rain_damp = max(0.45, 1.0 - 0.05 * weather.rain_mm_h)
                sub_s.voc_strength = round(sub_s._base_voc_strength * rain_damp, 3)
            elif sub_s.substrate_id == "SUB_COMPOST":
                moist_boost = 1.0 + 0.35 * max(0.0, (m_compost - 10.5) / 14.0)
                sub_s.voc_strength = round(sub_s._base_voc_strength * min(1.32, moist_boost), 3)
                sub_s.regen_per_s = round(sub_s._base_regen_per_s * min(1.40, moist_boost), 3)
            else:
                sub_s.voc_strength = round(sub_s._base_voc_strength * max(0.70, 1.0 - 0.022 * weather.rain_mm_h), 3)


@dataclass
class OtherInsectEntity:
    insect_id: str
    guild: str                  # "BUMBLEBEE" | "GROUND_BEETLE"
    species: str
    label_de: str
    gbif_occ_ref: int
    pos: Tuple[float, float, float]
    vel: Tuple[float, float, float]
    state: str                  # "FORAGING_NECTAR", "SHELTERING_RAIN", "FORAGING_MOIST", "AVOIDING_PUDDLE", "PATROLLING_GROUND"
    energy_pct: float
    activity_index: float
    target_plant_id: Optional[str]


class OtherInsectPopulation:
    """Autonome Sekundärinsekten (Ackerhummeln & Goldlaufkäfer auf Wölfersheimer GBIF-Basis)."""

    def __init__(self, world: Seestrasse43EcosystemWorld, plants: VegetationManager, seed: int = 42) -> None:
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed + 555)
        self.insects: List[OtherInsectEntity] = []
        self.reset(world, plants, seed=self.seed)

    def reset(self, world: Seestrasse43EcosystemWorld, plants: VegetationManager, seed: Optional[int] = None) -> None:
        if seed is not None:
            self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed + 555)
        gb = world.gbif_extended_records
        occ_b = int(gb.get("Bombus pascuorum", {}).get("total_count", 0))
        occ_c = int(gb.get("Carabus auratus", {}).get("total_count", 0))
        self.insects.clear()

        b_starts = [(-1.5, -7.2, 0.8), (-4.2, -4.8, 2.2), (-5.8, 4.8, 1.4), (0.6, -2.6, 0.7)]
        for i, sp_pos in enumerate(b_starts, 1):
            self.insects.append(
                OtherInsectEntity(
                    insect_id=f"BUMBLE_{i:02d}",
                    guild="BUMBLEBEE",
                    species="Bombus pascuorum",
                    label_de=f"Ackerhummel #{i}",
                    gbif_occ_ref=occ_b,
                    pos=sp_pos,
                    vel=(0.3, 0.1, 0.0),
                    state="FORAGING_NECTAR",
                    energy_pct=82.0,
                    activity_index=0.85,
                    target_plant_id="PLANT_FLOWER_BED_SW",
                )
            )
        c_starts = [(12.8, 5.2, 0.05), (6.5, -6.5, 0.05), (-3.8, 3.2, 0.05), (14.5, 1.8, 0.05)]
        for i, c_pos in enumerate(c_starts, 1):
            self.insects.append(
                OtherInsectEntity(
                    insect_id=f"BEETLE_{i:02d}",
                    guild="GROUND_BEETLE",
                    species="Carabus auratus",
                    label_de=f"Goldlaufkäfer #{i}",
                    gbif_occ_ref=occ_c,
                    pos=c_pos,
                    vel=(0.12, -0.08, 0.0),
                    state="PATROLLING_GROUND",
                    energy_pct=80.0,
                    activity_index=0.55,
                    target_plant_id=None,
                )
            )

    def step(self, dt_s: float, world: Seestrasse43EcosystemWorld, weather: WeatherState, hydro: HydrologyGrid, plants: VegetationManager) -> None:
        canopy_pts = [p for p in plants.plants if p.kind in ("tree", "shrub")]
        nectar_pts = [p for p in plants.plants if p.max_nectar_mg >= 6.0]

        for ins in self.insects:
            px, py, pz = ins.pos
            vx, vy, vz = ins.vel
            noise = self.rng.normal(0.0, 0.35, size=3)

            if ins.guild == "BUMBLEBEE":
                if weather.rain_mm_h >= 1.5 or weather.daylight_uv_factor < 0.22:
                    ins.state = "SHELTERING_RAIN"
                    target_pl = min(canopy_pts, key=lambda p: (p.pos[0] - px) ** 2 + (p.pos[1] - py) ** 2)
                    ins.target_plant_id = target_pl.plant_id
                    tx, ty, tz = target_pl.pos
                    dx, dy, dz = tx - px, ty - py, max(0.8, tz - 0.6) - pz
                    dist = math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-5
                    spd = 2.2 if dist > 0.8 else 0.15
                    des = (spd * dx / dist, spd * dy / dist, spd * dz / dist)
                    ins.activity_index = round(0.18 if dist <= 1.2 else 0.45, 2)
                else:
                    ins.state = "FORAGING_NECTAR"
                    target_pl = max(nectar_pts, key=lambda p: p.nectar_mg / (1.5 + math.hypot(p.pos[0] - px, p.pos[1] - py)))
                    ins.target_plant_id = target_pl.plant_id
                    tx, ty, tz = target_pl.pos
                    dx, dy, dz = tx - px, ty - py, max(0.45, min(3.8, tz)) - pz
                    dist = math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-5
                    if dist <= 1.1:
                        taken = min(target_pl.nectar_mg, 0.32 * dt_s)
                        target_pl.nectar_mg = round(max(0.0, target_pl.nectar_mg - taken), 3)
                        ins.energy_pct = round(min(100.0, ins.energy_pct + taken * 3.2), 1)
                    ang = self.rng.uniform(0.0, 6.283)
                    spd = 1.45 * max(0.45, weather.daylight_uv_factor)
                    des = (spd * dx / dist + 0.35 * math.cos(ang), spd * dy / dist + 0.35 * math.sin(ang), 0.7 * dz / dist)
                    ins.activity_index = round(float(np.clip(0.55 + 0.40 * weather.daylight_uv_factor, 0.25, 0.98)), 2)

                nvx = 0.75 * vx + 0.25 * (des[0] + noise[0] * 0.25)
                nvy = 0.75 * vy + 0.25 * (des[1] + noise[1] * 0.25)
                nvz = 0.75 * vz + 0.25 * des[2]
                nxt = world.clamp_or_slide_fly(
                    np.array([px, py, pz], dtype=np.float32),
                    np.array([px + nvx * dt_s, py + nvy * dt_s, pz + nvz * dt_s], dtype=np.float32),
                )
                if world.is_inside_house(nxt):
                    nxt = np.array([px, min(-0.4, py), pz], dtype=np.float32)
                ins.pos = (round(float(nxt[0]), 3), round(float(nxt[1]), 3), round(float(np.clip(nxt[2], 0.35, 5.2)), 3))
                ins.vel = (round(float(nvx), 3), round(float(nvy), 3), round(float(nvz), 3))
                ins.energy_pct = round(float(np.clip(ins.energy_pct - (0.04 if ins.state == "SHELTERING_RAIN" else 0.08) * dt_s, 15.0, 100.0)), 1)

            else:  # GROUND_BEETLE (Carabus auratus)
                m_pct, pud_mm, fspd = hydro.sample_at(px, py)
                if pud_mm > 5.0:
                    ins.state = "AVOIDING_PUDDLE"
                    # Zurück Richtung höheres/trockeneres Nord- oder West-Gelände ausweichen
                    tx, ty = (-5.5, 4.5) if px < 5.0 else (14.0, 5.5)
                    dx, dy = tx - px, ty - py
                    d = math.hypot(dx, dy) + 1e-5
                    des_xy = (0.34 * dx / d, 0.34 * dy / d)
                    ins.activity_index = 0.72
                elif m_pct >= 14.5:
                    ins.state = "FORAGING_MOIST"
                    # Aktivitäts- & Nahrungssuchschub auf feuchtem Boden (Kompost / Wiese)
                    tx, ty = (13.5, 5.5) if px > 6.0 else (-4.5, 2.5)
                    dx, dy = tx - px, ty - py
                    d = math.hypot(dx, dy) + 1e-5
                    des_xy = (0.28 * dx / d + 0.16 * noise[0], 0.28 * dy / d + 0.16 * noise[1])
                    ins.activity_index = round(float(np.clip(0.75 + 0.012 * (m_pct - 14.0), 0.7, 0.99)), 2)
                    ins.energy_pct = round(min(100.0, ins.energy_pct + 0.09 * dt_s), 1)
                else:
                    ins.state = "PATROLLING_GROUND"
                    des_xy = (0.14 * vx / (math.hypot(vx, vy) + 1e-4) + 0.12 * noise[0], 0.14 * vy / (math.hypot(vx, vy) + 1e-4) + 0.12 * noise[1])
                    ins.activity_index = 0.45

                nvx = 0.78 * vx + 0.22 * des_xy[0]
                nvy = 0.78 * vy + 0.22 * des_xy[1]
                nx = float(np.clip(px + nvx * dt_s, world.BOUNDS_MIN[0] + 0.8, world.BOUNDS_MAX[0] - 0.8))
                ny = float(np.clip(py + nvy * dt_s, world.BOUNDS_MIN[1] + 0.8, world.BOUNDS_MAX[1] - 0.8))
                if world.is_inside_house(np.array([nx, ny, 0.2]), margin=0.25):
                    nx, ny = px, min(-0.6, py) if py < 0.0 else py
                    nvx, nvy = -nvx, -nvy
                ins.pos = (round(nx, 3), round(ny, 3), 0.05)
                ins.vel = (round(float(nvx), 3), round(float(nvy), 3), 0.0)


class EnvironmentDynamics:
    """Fassadenklasse für Wetter, Jahreszeit, Hydrologie, Vegetation und Sekundärinsekten."""

    def __init__(
        self,
        world: Seestrasse43EcosystemWorld,
        scenario: str = "REGENZYKLUS",
        season: str = "SOMMER",
        seed: int = 42,
    ) -> None:
        self.weather_engine = WeatherAndSeasonEngine(scenario=scenario, season=season)
        self.hydro = HydrologyGrid(world=world, season=season)
        self.vegetation = VegetationManager(world=world, hydro=self.hydro)
        self.other_insects = OtherInsectPopulation(world=world, plants=self.vegetation, seed=seed)

    def reset(
        self,
        world: Seestrasse43EcosystemWorld,
        scenario: Optional[str] = None,
        season: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.weather_engine.reset(scenario=scenario, season=season)
        self.hydro.reset(season=self.weather_engine.season)
        self.vegetation.reset(world=world, hydro=self.hydro)
        self.other_insects.reset(world=world, plants=self.vegetation, seed=seed)
        self.weather_engine.step(world, 0.0)

    def step(self, world: Seestrasse43EcosystemWorld, dt_s: float) -> WeatherState:
        w = self.weather_engine.step(world, dt_s)
        self.hydro.step(dt_s, w)
        self.vegetation.step(dt_s, w, self.hydro, world)
        self.other_insects.step(dt_s, world, w, self.hydro, self.vegetation)
        return w
