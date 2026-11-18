# -*- coding: utf-8 -*-
"""
Modul F: Deterministisches 3D-Testuniversum SIMALITAET_FLY_LAB (Seestraße 43).

Modelleigenschaften:
- Read-Only-Geodatenanker an HOME_SEESTRASSE_43 aus SIMALITAET_GROSSGEMEINDE_WOELFERSHEIM.
- Exakte 3D-Gebäudegeometrie (Haupthaus 11,0 x 9,0 m + Heizungsanbau 4,5 x 3,5 m,
  EG/OG/DG mit 1,1 m Kniestock, 38°-Satteldach, durchgängiges Ost-Treppenhaus 2,4 x 3,8 m,
  alle 13 definierten Räume inkl. 1,5 cm Speisekammer- und 2,0 cm Heizraum-Türspalt).
- Gekoppeltes 0,25-m-Voxel-Mikroklima (72.600 Zellen): T(x,y,z,t), v_air(x,y,z,t),
  H(x,y,z,t), Spektrallicht L(UV-A, Blau, Grün) und 8-Klassen-VOC-Advection-Diffusion
  aus den 9 dynamischen Nahrungs- und Substratquellen FOOD_01..FOOD_09.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .security_guards import (
    BIODIV_DB_PATH,
    FLY_LAB_ROOT,
    WOELFERSHEIM_DB_PATH,
    FlyLabSecurityGuard,
)


VOC_CLASSES: Tuple[str, ...] = (
    "ethanol",
    "acetic_acid",
    "fruit_esters",
    "terpenes",
    "geosmin",
    "co2",
    "pheromones",
    "moisture_gradient",
)

SPECTRAL_BANDS: Tuple[str, ...] = ("uv_a", "blue", "green")
GUSTATORY_CHANNELS: Tuple[str, ...] = ("sugar", "acid", "water", "bitter")

FLOOR_BASE_Z: Dict[str, float] = {"EG": 0.0, "OG": 2.8, "DG": 5.6}
FLOOR_CEIL_Z: Dict[str, float] = {"EG": 2.6, "OG": 5.3, "DG": 8.2}


@dataclass(frozen=True)
class Box3D:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float
    label: str = ""

    def contains(self, x: float, y: float, z: float, margin: float = 0.0) -> bool:
        return (
            self.x_min - margin <= x <= self.x_max + margin
            and self.y_min - margin <= y <= self.y_max + margin
            and self.z_min - margin <= z <= self.z_max + margin
        )


@dataclass(frozen=True)
class RoomSpec:
    room_id: str
    floor: str
    function_de: str
    target_area_m2: float
    boxes: Tuple[Box3D, ...]
    features: str
    base_temp_c: float
    base_humidity_pct: float
    has_daylight: bool


@dataclass(frozen=True)
class PortalSpec:
    """Durchgang, Bogen, gekipptes Fenster oder schmaler Türspalt (Sub-Voxel-Präzision)."""
    portal_id: str
    room_a: str
    room_b: str
    kind: str  # "open_arch", "open_stairwell", "interior_door", "door_gap", "tilted_window"
    box: Box3D
    gap_height_m: Optional[float]
    conductance: float  # [0..1] Kopplung für Luft/VOC/Temperatur zwischen den Räumen


@dataclass(frozen=True)
class WindowLightSource:
    window_id: str
    room_id: str
    orientation: str  # S, W, E, N, SKYLIGHT_S, SKYLIGHT_N, TILTED_S
    pos: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    area_m2: float
    uv_a_gain: float
    blue_gain: float
    green_gain: float
    solar_heat_c: float


@dataclass
class FoodSubstrate:
    food_id: str
    label_de: str
    room_id: str
    floor: str
    furniture_de: str
    x: float
    y: float
    z_rel_m: float
    z_abs_m: float
    radius_m: float
    initial_ripeness: float
    ripeness: float
    initial_mass_g: float
    mass_g: float
    moisture_pct: float
    voc_signature_note: str
    # Emission rates [a.u./s] across 8 VOC_CLASSES:
    base_voc_rates: Tuple[float, ...]
    # Gustatory profile on tarsal/proboscis contact [0..1] across (sugar, acid, water, bitter):
    gustation_profile: Tuple[float, float, float, float]
    is_fermenting: bool
    is_aversive: bool
    total_feeding_events: int = 0
    total_feeding_time_s: float = 0.0
    mass_consumed_mg: float = 0.0

    def current_voc_rates(self) -> np.ndarray:
        """Skaliert VOC-Emission mit Reifegrad R(t) und Restmasse."""
        mass_factor = max(0.05, min(1.0, self.mass_g / max(1e-6, self.initial_mass_g)))
        ripeness_scale = 0.45 + 0.85 * self.ripeness
        arr = np.asarray(self.base_voc_rates, dtype=np.float32) * np.float32(mass_factor * ripeness_scale)
        # Fermentationsprodukte (Ethanol, Essigsäure, CO2) steigen überlinear bei R -> 1
        if self.is_fermenting:
            arr[0] *= np.float32(0.75 + 0.65 * self.ripeness)
            arr[1] *= np.float32(0.75 + 0.70 * self.ripeness)
            arr[5] *= np.float32(0.80 + 0.60 * self.ripeness)
        return arr


def roof_ceiling_z(y: float) -> float:
    """Dachgeschoss-Deckenprofil: 1,1 m Kniestock ab Z=5,6 m (Traufe Z=6,7 m), 38° Satteldach, max 8,2 m."""
    if y < 0.0 or y > 9.0:
        return 0.0
    dist_from_ridge = abs(y - 4.5)
    run_from_eave = max(0.0, 4.5 - dist_from_ridge)
    z_slope = 5.6 + 1.1 + run_from_eave * math.tan(math.radians(38.0))
    return min(8.2, z_slope)


def build_seestrasse_43_catalog() -> Tuple[List[RoomSpec], List[PortalSpec], List[WindowLightSource], List[Box3D], List[FoodSubstrate]]:
    """Erstellt die kanonischen Räume, Portale, Fenster, Möbel und 9 Substrate der Seestraße 43."""
    rooms: List[RoomSpec] = [
        RoomSpec(
            "EG_WOHN_ESS", "EG", "Wohn- und Essbereich", 36.0,
            (Box3D(0.25, 6.25, 0.25, 6.25, 0.0, 2.6, "EG_WOHN_ESS"),),
            "Große Fensterfront (Süd/West), Terrassentür (gekippt), offener Bogen zu EG_KUECHE",
            20.6, 48.0, True,
        ),
        RoomSpec(
            "EG_KUECHE", "EG", "Offene Küche", 16.0,
            (Box3D(6.40, 10.75, 0.25, 3.93, 0.0, 2.6, "EG_KUECHE"),),
            "Durchreiche/Offener Bogen zu EG_WOHN_ESS, 1 Südfenster, Türspalt zu EG_SPEIS",
            21.0, 54.0, True,
        ),
        RoomSpec(
            "EG_SPEIS", "EG", "Speisekammer / Abstellraum", 5.0,
            (Box3D(6.40, 8.20, 4.08, 6.86, 0.0, 2.6, "EG_SPEIS"),),
            "Tür zu EG_KUECHE (Spaltmaß 1,5 cm), dunkel, kühl",
            17.6, 52.0, False,
        ),
        RoomSpec(
            "EG_BAD_1", "EG", "Gäste-WC / Duschbad", 6.5,
            (Box3D(0.25, 3.02, 6.40, 8.75, 0.0, 2.6, "EG_BAD_1"),),
            "Tür zu EG_FLUR, kleines Kippfenster, erhöhte Grundfeuchte (68%)",
            20.8, 68.0, True,
        ),
        RoomSpec(
            "EG_FLUR", "EG", "Diele & Treppenhaus", 14.5,
            (
                Box3D(3.17, 6.25, 6.40, 8.75, 0.0, 2.6, "EG_FLUR_W"),
                Box3D(6.40, 8.20, 7.01, 8.75, 0.0, 2.6, "EG_FLUR_N"),
                Box3D(8.35, 10.75, 4.08, 8.75, 0.0, 2.8, "EG_FLUR_STAIR"),
            ),
            "Haustür, offener Durchgang zu EG_WOHN_ESS, offene Treppe ins OG, Brandschutztür zu ANBAU_HEIZ",
            21.3, 47.0, True,
        ),
        RoomSpec(
            "ANBAU_HEIZ", "EG", "Heizungs- & Technikraum (Anbau Nord)", 15.75,
            (Box3D(5.50, 10.00, 9.00, 12.50, 0.0, 2.6, "ANBAU_HEIZ"),),
            "Rückwärtiger Flachdach-Anbau 4,5 x 3,5 m, Brandschutztür zu EG_FLUR (Spaltmaß 2,0 cm), Wärmequelle 26,5 °C",
            26.5, 39.0, False,
        ),
        RoomSpec(
            "OG_FLUR", "OG", "Galerie & Treppenhaus", 12.0,
            (
                Box3D(3.85, 8.20, 3.96, 5.73, 2.8, 5.3, "OG_FLUR_GAL"),
                Box3D(8.35, 10.75, 3.82, 8.75, 2.8, 5.6, "OG_FLUR_STAIR"),
            ),
            "Offene Galerie zu EG und DG (Treppenhaus 2,4 x 3,8 m), Türen zu allen OG-Räumen",
            22.1, 49.0, True,
        ),
        RoomSpec(
            "OG_SCHLAF", "OG", "Hauptschlafzimmer", 20.0,
            (Box3D(4.90, 10.75, 0.25, 3.67, 2.8, 5.3, "OG_SCHLAF"),),
            "Ostfenster, konstante Temperatur",
            20.8, 48.0, True,
        ),
        RoomSpec(
            "OG_ARBEIT", "OG", "Arbeits- / Lesezimmer", 16.0,
            (Box3D(0.25, 4.75, 0.25, 3.81, 2.8, 5.3, "OG_ARBEIT"),),
            "Südfenster, direkte Sonneneinstrahlung",
            22.6, 46.0, True,
        ),
        RoomSpec(
            "OG_GAST", "OG", "Gäste- / Kinderzimmer", 15.0,
            (Box3D(0.25, 3.70, 4.40, 8.75, 2.8, 5.3, "OG_GAST"),),
            "Westfenster",
            21.4, 48.0, True,
        ),
        RoomSpec(
            "OG_BAD_2", "OG", "Hauptbadezimmer", 12.5,
            (Box3D(3.85, 8.20, 5.88, 8.75, 2.8, 5.3, "OG_BAD_2"),),
            "Badewanne/Dusche, Nordfenster, hohe Luftfeuchtigkeit (75%)",
            22.2, 75.0, True,
        ),
        RoomSpec(
            "DG_STUDIO", "DG", "Offenes Dachstudio", 42.0,
            (
                Box3D(2.52, 8.20, 0.25, 8.75, 5.6, 8.2, "DG_STUDIO_MAIN"),
                Box3D(8.20, 10.75, 0.25, 4.95, 5.6, 8.2, "DG_STUDIO_SE"),
                Box3D(8.35, 10.75, 4.95, 8.75, 5.6, 8.2, "DG_STUDIO_STAIR"),
            ),
            "Kniestock 1,1 m, Dachneigung 38°, Dachflächenfenster Süd/Nord, wärmste Zone durch Auftrieb (23,5 °C)",
            23.5, 44.0, True,
        ),
        RoomSpec(
            "DG_ABSTELL", "DG", "Dachboden / Lagerkammer", 18.0,
            (Box3D(0.25, 2.37, 0.25, 8.75, 5.6, 8.2, "DG_ABSTELL"),),
            "Holztür zu DG_STUDIO, ungedämmter Bereich, trocken/kühl, dunkel",
            16.8, 36.0, False,
        ),
    ]

    portals: List[PortalSpec] = [
        PortalSpec(
            "P_WOHN_KUECHE", "EG_WOHN_ESS", "EG_KUECHE", "open_arch",
            Box3D(6.20, 6.45, 1.00, 3.40, 0.00, 2.25, "Durchreiche/Offener Bogen"), None, 1.00,
        ),
        PortalSpec(
            "P_WOHN_FLUR", "EG_WOHN_ESS", "EG_FLUR", "open_arch",
            Box3D(4.20, 5.80, 6.20, 6.45, 0.00, 2.25, "Offener Durchgang Wohn/Ess-Diele"), None, 1.00,
        ),
        PortalSpec(
            "P_KUECHE_FLUR", "EG_KUECHE", "EG_FLUR", "open_arch",
            Box3D(8.55, 9.65, 3.88, 4.13, 0.00, 2.15, "Küchendurchgang zur Diele / Treppenhaus"), None, 0.85,
        ),
        PortalSpec(
            "P_FLUR_BAD1", "EG_FLUR", "EG_BAD_1", "interior_door",
            Box3D(2.97, 3.22, 7.20, 8.05, 0.00, 2.00, "Tür EG_FLUR <-> EG_BAD_1"), None, 0.55,
        ),
        PortalSpec(
            "P_KUECHE_SPEIS_GAP", "EG_KUECHE", "EG_SPEIS", "door_gap",
            Box3D(6.90, 7.75, 3.88, 4.13, 0.00, 0.015, "Türspalt EG_SPEIS 1,5 cm"), 0.015, 0.30,
        ),
        PortalSpec(
            "P_FLUR_HEIZ_GAP", "EG_FLUR", "ANBAU_HEIZ", "door_gap",
            Box3D(6.80, 7.70, 8.70, 9.05, 0.00, 0.020, "Brandschutztürspalt ANBAU_HEIZ 2,0 cm"), 0.020, 0.35,
        ),
        PortalSpec(
            "P_STAIR_EG_OG", "EG_FLUR", "OG_FLUR", "open_stairwell",
            Box3D(8.35, 10.75, 4.95, 8.75, 2.50, 2.95, "Offenes Treppenhaus EG <-> OG"), None, 1.00,
        ),
        PortalSpec(
            "P_STAIR_OG_DG", "OG_FLUR", "DG_STUDIO", "open_stairwell",
            Box3D(8.35, 10.75, 4.95, 8.75, 5.20, 5.75, "Offenes Treppenhaus OG <-> DG"), None, 1.00,
        ),
        PortalSpec(
            "P_OGFLUR_ARBEIT", "OG_FLUR", "OG_ARBEIT", "interior_door",
            Box3D(3.85, 4.65, 3.76, 4.02, 2.80, 4.85, "Tür OG_FLUR <-> OG_ARBEIT"), None, 0.85,
        ),
        PortalSpec(
            "P_OGFLUR_SCHLAF", "OG_FLUR", "OG_SCHLAF", "interior_door",
            Box3D(5.20, 6.05, 3.62, 4.02, 2.80, 4.85, "Tür OG_FLUR <-> OG_SCHLAF"), None, 0.65,
        ),
        PortalSpec(
            "P_OGFLUR_GAST", "OG_FLUR", "OG_GAST", "interior_door",
            Box3D(3.65, 3.92, 4.55, 5.40, 2.80, 4.85, "Tür OG_FLUR <-> OG_GAST"), None, 0.65,
        ),
        PortalSpec(
            "P_OGFLUR_BAD2", "OG_FLUR", "OG_BAD_2", "interior_door",
            Box3D(5.40, 6.25, 5.68, 5.93, 2.80, 4.85, "Tür OG_FLUR <-> OG_BAD_2"), None, 0.85,
        ),
        PortalSpec(
            "P_DGSTUDIO_ABSTELL", "DG_STUDIO", "DG_ABSTELL", "interior_door",
            Box3D(2.32, 2.57, 4.10, 4.85, 5.60, 7.20, "Holztür DG_STUDIO <-> DG_ABSTELL"), None, 0.28,
        ),
    ]

    windows: List[WindowLightSource] = [
        WindowLightSource("WIN_EG_WOHN_S", "EG_WOHN_ESS", "S", (2.6, 0.25, 1.35), (0.0, 1.0, 0.0), 4.2, 0.92, 1.00, 0.96, 1.1),
        WindowLightSource("WIN_EG_WOHN_TERR", "EG_WOHN_ESS", "TILTED_S", (1.3, 0.25, 1.95), (0.0, 1.0, -0.2), 1.8, 0.78, 0.85, 0.82, 0.2),
        WindowLightSource("WIN_EG_WOHN_W", "EG_WOHN_ESS", "W", (0.25, 3.4, 1.35), (1.0, 0.0, 0.0), 3.2, 0.85, 0.94, 0.90, 0.9),
        WindowLightSource("WIN_EG_KUECHE_S", "EG_KUECHE", "S", (8.6, 0.25, 1.45), (0.0, 1.0, 0.0), 1.6, 0.82, 0.92, 0.88, 0.8),
        WindowLightSource("WIN_EG_BAD1_N", "EG_BAD_1", "N", (1.6, 8.75, 1.65), (0.0, -1.0, 0.0), 0.7, 0.45, 0.52, 0.48, 0.1),
        WindowLightSource("WIN_OG_ARBEIT_S", "OG_ARBEIT", "S", (2.5, 0.25, 4.05), (0.0, 1.0, 0.0), 2.1, 0.95, 1.00, 0.98, 1.5),
        WindowLightSource("WIN_OG_SCHLAF_E", "OG_SCHLAF", "E", (10.75, 1.95, 4.05), (-1.0, 0.0, 0.0), 2.0, 0.72, 0.80, 0.76, 0.5),
        WindowLightSource("WIN_OG_GAST_W", "OG_GAST", "W", (0.25, 6.60, 4.05), (1.0, 0.0, 0.0), 1.8, 0.80, 0.88, 0.85, 0.7),
        WindowLightSource("WIN_OG_BAD2_N", "OG_BAD_2", "N", (6.05, 8.75, 4.10), (0.0, -1.0, 0.0), 1.2, 0.52, 0.60, 0.56, 0.2),
        WindowLightSource("WIN_DG_SKYLIGHT_S", "DG_STUDIO", "SKYLIGHT_S", (5.5, 2.2, 7.25), (0.0, 0.6, -0.8), 2.2, 0.96, 1.00, 0.98, 1.3),
        WindowLightSource("WIN_DG_SKYLIGHT_N", "DG_STUDIO", "SKYLIGHT_N", (5.5, 6.8, 7.25), (0.0, -0.6, -0.8), 1.8, 0.68, 0.76, 0.72, 0.4),
    ]

    furniture: List[Box3D] = [
        Box3D(6.80, 8.20, 1.20, 2.50, 0.0, 0.92, "EG_KUECHE_Insel_FOOD_01"),
        Box3D(8.50, 9.20, 3.00, 3.70, 0.0, 0.35, "EG_KUECHE_Biomuell_FOOD_02"),
        Box3D(9.45, 10.65, 0.40, 3.20, 0.0, 0.90, "EG_KUECHE_Arbeitsplatte_FOOD_06_08"),
        Box3D(3.20, 5.00, 1.80, 3.00, 0.0, 0.78, "EG_WOHN_Esstisch_FOOD_03"),
        Box3D(7.15, 8.10, 5.30, 6.40, 0.0, 1.10, "EG_SPEIS_Regal_FOOD_04"),
        Box3D(1.60, 3.20, 0.85, 2.05, 2.80, 3.56, "OG_ARBEIT_Schreibtisch_FOOD_05"),
        Box3D(5.55, 6.75, 7.75, 8.65, 2.80, 3.65, "OG_BAD2_Waschbecken_FOOD_09"),
        Box3D(4.60, 5.80, 2.80, 4.00, 5.60, 6.15, "DG_STUDIO_Beistelltisch_FOOD_07"),
    ]

    foods: List[FoodSubstrate] = [
        FoodSubstrate(
            "FOOD_01", "Reife Bananen (3x)", "EG_KUECHE", "EG", "Obstschale",
            7.50, 1.85, 0.92, 0.92, 0.16, 0.85, 0.85, 360.0, 360.0, 65.0,
            "Isoamylacetat (Frucht-Ester), Ethanol (leicht)",
            (0.45, 0.25, 1.85, 0.0, 0.0, 0.15, 0.0, 0.65),
            (0.85, 0.15, 0.65, 0.00), False, False,
        ),
        FoodSubstrate(
            "FOOD_02", "Fermentierende Banane", "EG_KUECHE", "EG", "Biomüll-Eimer",
            8.85, 3.35, 0.35, 0.35, 0.18, 0.98, 0.98, 140.0, 140.0, 88.0,
            "Essigsäure, Ethanol, Ethylacetat (sehr stark)",
            (3.40, 3.80, 3.20, 0.0, 0.0, 1.40, 0.0, 0.88),
            (0.75, 0.72, 0.88, 0.02), True, False,
        ),
        FoodSubstrate(
            "FOOD_03", "Äpfel (Elstar, 4x)", "EG_WOHN_ESS", "EG", "Esstisch",
            4.10, 2.40, 0.78, 0.78, 0.18, 0.60, 0.60, 520.0, 520.0, 50.0,
            "Hexylacetat, Butylacetat (frisch, moderat)",
            (0.08, 0.05, 0.85, 0.0, 0.0, 0.05, 0.0, 0.50),
            (0.58, 0.22, 0.50, 0.00), False, False,
        ),
        FoodSubstrate(
            "FOOD_04", "Überreife Birnen (2x)", "EG_SPEIS", "EG", "Regalbrett 2",
            7.60, 5.85, 1.10, 1.10, 0.15, 0.90, 0.90, 280.0, 280.0, 82.0,
            "Ethyl-2,4-decadienoat, Acetaldehyd",
            (1.65, 1.15, 2.40, 0.0, 0.0, 0.55, 0.0, 0.82),
            (0.88, 0.35, 0.82, 0.00), True, False,
        ),
        FoodSubstrate(
            "FOOD_05", "Trauben (angeschnitten)", "OG_ARBEIT", "OG", "Schreibtisch",
            2.40, 1.45, 0.76, 3.56, 0.14, 0.75, 0.75, 120.0, 120.0, 90.0,
            "Fructose-Lösung, Linalool, Hefenote",
            (1.05, 0.45, 1.55, 0.15, 0.0, 0.40, 0.0, 0.90),
            (0.92, 0.25, 0.90, 0.00), True, False,
        ),
        FoodSubstrate(
            "FOOD_06", "Pflaumen (leicht aufgeplatzt)", "EG_KUECHE", "EG", "Arbeitsplatte",
            9.85, 1.35, 0.90, 0.90, 0.14, 0.88, 0.88, 210.0, 210.0, 85.0,
            "Benzaldehyd, Lactone, Ethanol",
            (1.50, 0.65, 2.05, 0.0, 0.0, 0.45, 0.0, 0.85),
            (0.82, 0.32, 0.85, 0.03), True, False,
        ),
        FoodSubstrate(
            "FOOD_07", "Orangen (geschält/Reste)", "DG_STUDIO", "DG", "Beistelltisch",
            5.20, 3.40, 0.55, 6.15, 0.15, 0.70, 0.70, 180.0, 180.0, 78.0,
            "Limonen (Terpene – starker Reiz/Abwehr-Modulator)",
            (0.15, 0.20, 0.45, 3.40, 0.0, 0.10, 0.0, 0.78),
            (0.35, 0.55, 0.78, 0.38), False, True,
        ),
        FoodSubstrate(
            "FOOD_08", "Feuchter Kaffeesatz & Apfelschale", "EG_KUECHE", "EG", "Spülenrand",
            10.20, 2.55, 0.91, 0.91, 0.14, 0.92, 0.92, 160.0, 160.0, 95.0,
            "Pyrazine, Essigsäure, hohe Verdunstung",
            (0.95, 2.25, 1.45, 0.0, 0.0, 0.70, 0.0, 0.95),
            (0.45, 0.62, 0.95, 0.22), True, False,
        ),
        FoodSubstrate(
            "FOOD_09", "Feuchter Schwamm / Abflussfilm", "OG_BAD_2", "OG", "Waschbecken",
            6.15, 8.15, 0.85, 3.65, 0.16, 0.50, 0.50, 90.0, 90.0, 98.0,
            "Geosmin (Schimmel/Bakterien-Marker, DA2-Aversion), H2O-Dampf",
            (0.05, 0.08, 0.0, 0.0, 3.20, 0.15, 0.0, 0.98),
            (0.02, 0.10, 0.98, 0.82), False, True,
        ),
    ]
    return rooms, portals, windows, furniture, foods


class Seestrasse43World:
    """Deterministische 3D-Umwelt-Engine für Seestraße 43 (Voxel Δ = 0,25 m)."""

    VOXEL_SIZE_M: float = 0.25
    NX: int = 44   # 0.0 .. 11.00 m
    NY: int = 50   # 0.0 .. 12.50 m
    NZ: int = 33   # 0.0 .. 8.25 m (72.600 Voxel!)

    def __init__(
        self,
        guard: Optional[FlyLabSecurityGuard] = None,
        sim_hour_of_day: float = 14.0,
        ventilation_boost: float = 1.0,
    ) -> None:
        self.guard = guard or FlyLabSecurityGuard()
        self.sim_time_s: float = 0.0
        self.sim_hour_of_day: float = sim_hour_of_day
        self.ventilation_boost: float = ventilation_boost
        self.anchor_record: Dict[str, object] = self._load_ro_woelfersheim_anchor()
        self.rooms, self.portals, self.windows, self.furniture, self.foods = build_seestrasse_43_catalog()
        self.room_by_id: Dict[str, RoomSpec] = {r.room_id: r for r in self.rooms}
        self.food_by_id: Dict[str, FoodSubstrate] = {f.food_id: f for f in self.foods}

        # Voxelzentren vorbereiten
        self.xc = (np.arange(self.NX, dtype=np.float32) + 0.5) * self.VOXEL_SIZE_M
        self.yc = (np.arange(self.NY, dtype=np.float32) + 0.5) * self.VOXEL_SIZE_M
        self.zc = (np.arange(self.NZ, dtype=np.float32) + 0.5) * self.VOXEL_SIZE_M

        # Voxel-Raummaske & Skalar-/Vektorfelder (float32, Gesamt < 6 MB RAM!)
        self.room_idx_grid = np.full((self.NX, self.NY, self.NZ), -1, dtype=np.int16)
        self.air_mask = np.zeros((self.NX, self.NY, self.NZ), dtype=bool)
        self.temp_c = np.full((self.NX, self.NY, self.NZ), 20.5, dtype=np.float32)
        self.humidity_pct = np.full((self.NX, self.NY, self.NZ), 48.0, dtype=np.float32)
        self.vel = np.zeros((3, self.NX, self.NY, self.NZ), dtype=np.float32)
        self.light = np.zeros((3, self.NX, self.NY, self.NZ), dtype=np.float32)
        self.voc = np.zeros((len(VOC_CLASSES), self.NX, self.NY, self.NZ), dtype=np.float32)
        self._food_voxel_indices: List[Tuple[FoodSubstrate, int, int, int]] = []
        self._tx = np.zeros((self.NX - 1, self.NY, self.NZ), dtype=np.float32)
        self._ty = np.zeros((self.NX, self.NY - 1, self.NZ), dtype=np.float32)
        self._tz = np.zeros((self.NX, self.NY, self.NZ - 1), dtype=np.float32)
        self._voc_dt_accum: float = 0.0

        self._build_voxel_geometry()
        self._build_face_conductances()
        self._rebuild_static_microclimate()
        self.warm_up_voc_plumes(steps=45, dt_s=0.45)

    def _load_ro_woelfersheim_anchor(self) -> Dict[str, object]:
        """Lädt den kanonischen Gebäudeanker HOME_SEESTRASSE_43 streng read-only."""
        anchor: Dict[str, object] = {
            "source_db": str(WOELFERSHEIM_DB_PATH),
            "building_id": "HOME_SEESTRASSE_43",
            "verified_readonly": False,
        }
        if WOELFERSHEIM_DB_PATH.exists():
            con = self.guard.open_readonly_sqlite(WOELFERSHEIM_DB_PATH)
            try:
                row = con.execute(
                    """
                    SELECT building_id, osm_way_id, ortsteil, usage_class, street, housenumber,
                           footprint_m2, levels_est, east_m, north_m, alt_nhn_m, lat_deg, lon_deg,
                           qbdp_addr, content_sha
                    FROM buildings WHERE building_id = 'HOME_SEESTRASSE_43'
                    """
                ).fetchone()
                total_buildings = con.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
                if row:
                    anchor.update(dict(row))
                    anchor["woelfersheim_total_buildings"] = int(total_buildings)
                    anchor["verified_readonly"] = True
            finally:
                con.close()
        if BIODIV_DB_PATH.exists():
            con_b = self.guard.open_readonly_sqlite(BIODIV_DB_PATH)
            try:
                b_cnt = con_b.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                anchor["biodiv_ro_tables"] = int(b_cnt)
            finally:
                con_b.close()
        return anchor

    def _build_voxel_geometry(self) -> None:
        """Rasterisiert die 13 Räume + Dachschräge 38° + offenes Ost-Treppenhaus + Portale."""
        for ix, x in enumerate(self.xc):
            for iy, y in enumerate(self.yc):
                for iz, z in enumerate(self.zc):
                    if y <= 9.0 and z >= 5.6 and z > roof_ceiling_z(float(y)):
                        continue
                    rid_idx = -1
                    for r_i, room in enumerate(self.rooms):
                        for box in room.boxes:
                            if box.contains(float(x), float(y), float(z)):
                                rid_idx = r_i
                                break
                        if rid_idx >= 0:
                            break
                    if rid_idx < 0:
                        for p in self.portals:
                            if p.kind in ("open_arch", "open_stairwell", "interior_door") and p.box.contains(
                                float(x), float(y), float(z), margin=0.08
                            ):
                                rid_idx = self.rooms.index(self.room_by_id[p.room_a])
                                break
                    if rid_idx >= 0:
                        self.room_idx_grid[ix, iy, iz] = rid_idx
                        self.air_mask[ix, iy, iz] = True

        self._food_voxel_indices.clear()
        for f in self.foods:
            ix = int(np.clip(f.x / self.VOXEL_SIZE_M, 0, self.NX - 1))
            iy = int(np.clip(f.y / self.VOXEL_SIZE_M, 0, self.NY - 1))
            iz = int(np.clip(f.z_abs_m / self.VOXEL_SIZE_M, 0, self.NZ - 1))
            self._food_voxel_indices.append((f, ix, iy, iz))

    def _build_face_conductances(self) -> None:
        """
        Precomputet wanddichte Flächenleitwerte zwischen Nachbarvoxeln:
        1,0 innerhalb desselben Raums, portal.conductance an expliziten Portalen/Türspalten,
        0,0 durch massive Innenwände und geschlossene Geschossdecken.
        """
        rg = self.room_idx_grid
        same_x = (rg[:-1, :, :] >= 0) & (rg[:-1, :, :] == rg[1:, :, :])
        same_y = (rg[:, :-1, :] >= 0) & (rg[:, :-1, :] == rg[:, 1:, :])
        same_z = (rg[:, :, :-1] >= 0) & (rg[:, :, :-1] == rg[:, :, 1:])
        self._tx = same_x.astype(np.float32)
        self._ty = same_y.astype(np.float32)
        self._tz = same_z.astype(np.float32)

        idx_by_id = {r.room_id: i for i, r in enumerate(self.rooms)}
        X = self.xc[:, None, None]
        Y = self.yc[None, :, None]
        Z = self.zc[None, None, :]

        for p in self.portals:
            if p.room_a not in idx_by_id or p.room_b not in idx_by_id:
                continue
            ia, ib = idx_by_id[p.room_a], idx_by_id[p.room_b]
            m = 0.28
            in_p = (
                (X >= p.box.x_min - m) & (X <= p.box.x_max + m)
                & (Y >= p.box.y_min - m) & (Y <= p.box.y_max + m)
                & (Z >= p.box.z_min - m) & (Z <= p.box.z_max + m)
            )
            cond = np.float32(p.conductance)
            pair_x = ((rg[:-1, :, :] == ia) & (rg[1:, :, :] == ib)) | ((rg[:-1, :, :] == ib) & (rg[1:, :, :] == ia))
            mask_x = pair_x & (in_p[:-1, :, :] | in_p[1:, :, :])
            self._tx = np.maximum(self._tx, mask_x * cond)

            pair_y = ((rg[:, :-1, :] == ia) & (rg[:, 1:, :] == ib)) | ((rg[:, :-1, :] == ib) & (rg[:, 1:, :] == ia))
            mask_y = pair_y & (in_p[:, :-1, :] | in_p[:, 1:, :])
            self._ty = np.maximum(self._ty, mask_y * cond)

            pair_z = ((rg[:, :, :-1] == ia) & (rg[:, :, 1:] == ib)) | ((rg[:, :, :-1] == ib) & (rg[:, :, 1:] == ia))
            mask_z = pair_z & (in_p[:, :, :-1] | in_p[:, :, 1:])
            self._tz = np.maximum(self._tz, mask_z * cond)

        # Offener Bogen/Durchgang im EG soll durchlässig bleiben auch falls Box zwischen zwei EG-Räumen liegt
        for r_pair in (("EG_FLUR", "OG_FLUR"), ("OG_FLUR", "DG_STUDIO")):
            ia, ib = idx_by_id[r_pair[0]], idx_by_id[r_pair[1]]
            pair_z = ((rg[:, :, :-1] == ia) & (rg[:, :, 1:] == ib)) | ((rg[:, :, :-1] == ib) & (rg[:, :, 1:] == ia))
            stair_xy = (X >= 8.20) & (X <= 10.85) & (Y >= 4.80) & (Y <= 8.85)
            self._tz = np.maximum(self._tz, (pair_z & stair_xy).astype(np.float32))

    def _rebuild_static_microclimate(self) -> None:
        """Berechnet Temperatur-, Konvektions-, Feuchte- und Spektrallichtfeld für Seestraße 43."""
        # 1. Grundwerte pro Raum
        for r_i, room in enumerate(self.rooms):
            mask = self.room_idx_grid == r_i
            self.temp_c[mask] = room.base_temp_c
            self.humidity_pct[mask] = room.base_humidity_pct

        # Koordinaten-Broadcasts für weiche physikalische Gradienten (alle (44, 50, 33))
        X, Y, Z = np.broadcast_arrays(
            self.xc[:, None, None],
            self.yc[None, :, None],
            self.zc[None, None, :],
        )

        # Kamineffekt im Treppenhaus + Wärmelecks am ANBAU_HEIZ-Spalt + solarer Fenstereintrag
        solar_factor = max(0.25, math.sin(max(0.0, min(math.pi, (self.sim_hour_of_day - 6.0) / 14.0 * math.pi))))
        anbau_plume = np.exp(-((X - 7.25) ** 2 / 2.2 + (Y - 8.90) ** 2 / 1.8 + (Z - 0.6) ** 2 / 1.2))
        eg_only = (Z < 2.65) & self.air_mask
        self.temp_c[eg_only] += (1.6 * anbau_plume[eg_only]).astype(np.float32)

        solar_warm = np.where((Y < 2.2) | (X < 1.8), 0.75 * solar_factor, 0.0)
        self.temp_c[self.air_mask] += solar_warm[self.air_mask].astype(np.float32)
        # Sicherstellen, dass ANBAU_HEIZ exakt ~26,5 °C und DG_STUDIO ~23,5 °C Zielzonen halten
        heiz_idx = self.rooms.index(self.room_by_id["ANBAU_HEIZ"])
        self.temp_c[self.room_idx_grid == heiz_idx] = np.float32(26.5)

        # 2. Konvektionswalzen v_air(x,y,z) [m/s]:
        # EG: gekippte Terrassentür (X~1.3, Y~0.25) -> Richtung Küche & Diele -> Ost-Treppenhaus (X~9.5, Y~6.8) -> hoch ins DG
        vx = np.zeros_like(self.temp_c)
        vy = np.zeros_like(self.temp_c)
        vz = np.zeros_like(self.temp_c)
        vb = float(self.ventilation_boost)

        eg = (Z < 2.65) & self.air_mask
        vx[eg] = vb * 0.055 * np.sign(9.5 - X)[eg]
        vy[eg] = vb * (0.045 * (Y < 4.5) - 0.040 * (Y > 8.2))[eg]
        vz[eg] = 0.015 * np.sin((X / 11.0) * math.pi)[eg]

        # Offenes Treppenhaus (X in [8.2, 10.8], Y in [4.8, 8.8]): starker thermischer Aufwind
        stair = (X >= 8.20) & (X <= 10.85) & (Y >= 4.80) & (Y <= 8.85) & self.air_mask
        vz[stair] = vb * (0.14 + 0.03 * np.sin(Z / 2.5))[stair]
        vy[stair] = vb * 0.025

        # OG & DG Konvektion aus dem Treppenhaus zu den Fenstern/Dachflächenfenstern
        og = (Z >= 2.75) & (Z < 5.35) & self.air_mask & (~stair)
        vx[og] = vb * (-0.035 * ((X - 4.5) / 5.5))[og]
        vy[og] = vb * (0.025 * np.cos(Y / 3.0))[og]
        vz[og] = 0.010

        dg = (Z >= 5.55) & self.air_mask & (~stair)
        vx[dg] = vb * (-0.045 * ((X - 4.0) / 6.0))[dg]
        vy[dg] = vb * (0.030 * np.sin((Y - 4.5) / 2.5))[dg]
        vz[dg] = vb * (-0.015 + 0.035 * np.exp(-((Y - 2.2) ** 2 + (Y - 6.8) ** 2) / 16.0))[dg]

        self.vel[0], self.vel[1], self.vel[2] = vx, vy, vz
        # Precomputete Flächen-Advektionsgeschwindigkeiten (spart Rechenzeit in jedem PDE-Schritt)
        self._vx_f = (np.float32(0.5) * (vx[:-1, :, :] + vx[1:, :, :]) * self._tx)[None, ...]
        self._vy_f = (np.float32(0.5) * (vy[:, :-1, :] + vy[:, 1:, :]) * self._ty)[None, ...]
        self._vz_f = (np.float32(0.5) * (vz[:, :, :-1] + vz[:, :, 1:]) * self._tz)[None, ...]
        self._vx_f_pos = self._vx_f >= 0
        self._vy_f_pos = self._vy_f >= 0
        self._vz_f_pos = self._vz_f >= 0
        self._tx_e = self._tx[None, ...]
        self._ty_e = self._ty[None, ...]
        self._tz_e = self._tz[None, ...]

        # 3. Lokale Feuchtequellen um nasse Substrate & Bäder
        for f in self.foods:
            dist2 = (X - f.x) ** 2 + (Y - f.y) ** 2 + (Z - f.z_abs_m) ** 2
            halo = (f.moisture_pct - 48.0) * 0.45 * np.exp(-dist2 / 0.85)
            self.humidity_pct[self.air_mask] = np.clip(
                self.humidity_pct[self.air_mask] + np.maximum(0.0, halo[self.air_mask]), 25.0, 99.0
            )

        # 4. Spektrales Lichtfeld L(UV-A, Blau, Grün) durch reale Fenster & Dachflächenfenster
        self.light.fill(0.015)  # diffuse Innenraum-Basis
        for win in self.windows:
            wx, wy, wz = win.pos
            room_box_z_floor = FLOOR_BASE_Z[self.room_by_id[win.room_id].floor]
            room_box_z_ceil = FLOOR_CEIL_Z[self.room_by_id[win.room_id].floor]
            same_floor = (Z >= room_box_z_floor - 0.1) & (Z <= room_box_z_ceil + 0.2) & self.air_mask
            dist2 = (X - wx) ** 2 + (Y - wy) ** 2 + (Z - wz) ** 2 + 0.35
            att = np.where(same_floor, np.minimum(1.0, (win.area_m2 * 0.9) / dist2), 0.0)
            self.light[0] += (att * win.uv_a_gain * solar_factor).astype(np.float32)
            self.light[1] += (att * win.blue_gain * solar_factor).astype(np.float32)
            self.light[2] += (att * win.green_gain * solar_factor).astype(np.float32)

        # Speisekammer & Abstellraum bleiben dunkel/schattig
        for dark_id in ("EG_SPEIS", "DG_ABSTELL", "ANBAU_HEIZ"):
            idx = self.rooms.index(self.room_by_id[dark_id])
            m = self.room_idx_grid == idx
            self.light[:, m] *= 0.08
        self.light = np.clip(self.light, 0.0, 1.5)

    def warm_up_voc_plumes(self, steps: int = 45, dt_s: float = 0.45) -> None:
        """Löst das 3D-Advection-Diffusion-System auf quasi-stationäre Duftfahnen vor."""
        for _ in range(steps):
            self._step_voc_field(dt_s=dt_s)

    def _step_voc_field(self, dt_s: float) -> None:
        """Wanddichter Upwind-Advection + Flächenleitwert-Diffusionsschritt auf 72.600 Voxeln."""
        C = self.voc
        for f, ix, iy, iz in self._food_voxel_indices:
            C[:, ix, iy, iz] += f.current_voc_rates() * np.float32(dt_s * 0.65)

        substeps = max(1, int(math.ceil(dt_s / 0.15)))
        h_dt = np.float32(dt_s / substeps)
        inv_dx = np.float32(1.0 / self.VOXEL_SIZE_M)
        diff_coeff = np.float32(0.055)  # CFL-stabile turbulente Raumluft-Diffusivität [m^2/s]
        decay = np.float32(0.0025)
        vx_f, vy_f, vz_f = self._vx_f, self._vy_f, self._vz_f
        air_m = self.air_mask[None, ...]

        for _ in range(substeps):
            fx = diff_coeff * (C[:, 1:, :, :] - C[:, :-1, :, :]) * inv_dx * self._tx_e
            fy = diff_coeff * (C[:, :, 1:, :] - C[:, :, :-1, :]) * inv_dx * self._ty_e
            fz = diff_coeff * (C[:, :, :, 1:] - C[:, :, :, :-1]) * inv_dx * self._tz_e

            fx = fx - np.where(self._vx_f_pos, vx_f * C[:, :-1, :, :], vx_f * C[:, 1:, :, :])
            fy = fy - np.where(self._vy_f_pos, vy_f * C[:, :, :-1, :], vy_f * C[:, :, 1:, :])
            fz = fz - np.where(self._vz_f_pos, vz_f * C[:, :, :, :-1], vz_f * C[:, :, :, 1:])

            div = np.zeros_like(C)
            div[:, :-1, :, :] += fx
            div[:, 1:, :, :] -= fx
            div[:, :, :-1, :] += fy
            div[:, :, 1:, :] -= fy
            div[:, :, :, :-1] += fz
            div[:, :, :, 1:] -= fz

            C = np.where(air_m, np.maximum(0.0, C + h_dt * (div * inv_dx - decay * C)), 0.0).astype(np.float32)

        self.voc = C

    def snapshot_voc_and_foods(self) -> Dict[str, object]:
        return {
            "voc": self.voc.copy(),
            "foods": [(f.ripeness, f.mass_g, f.mass_consumed_mg, f.total_feeding_events, f.total_feeding_time_s) for f in self.foods],
            "sim_time_s": self.sim_time_s,
        }

    def restore_voc_and_foods(self, snap: Dict[str, object]) -> None:
        self.voc = snap["voc"].copy()  # type: ignore[attr-defined]
        for f, st in zip(self.foods, snap["foods"]):  # type: ignore[arg-type]
            f.ripeness, f.mass_g, f.mass_consumed_mg, f.total_feeding_events, f.total_feeding_time_s = st
        self.sim_time_s = float(snap["sim_time_s"])  # type: ignore[arg-type]
        self._voc_dt_accum = 0.0

    def step(self, dt_s: float) -> None:
        """Führt das gesamte Weltmodell deterministisch um dt_s Sekunden fort."""
        self.sim_time_s += dt_s
        for f in self.foods:
            f.ripeness = min(1.0, f.ripeness + 2.5e-5 * dt_s)
        self._voc_dt_accum += dt_s
        if self._voc_dt_accum >= 0.60:
            self._step_voc_field(self._voc_dt_accum)
            self._voc_dt_accum = 0.0

    def _trilinear_sample(self, field: np.ndarray, x: float, y: float, z: float) -> np.ndarray | float:
        gx = np.clip(x / self.VOXEL_SIZE_M - 0.5, 0.0, self.NX - 1.001)
        gy = np.clip(y / self.VOXEL_SIZE_M - 0.5, 0.0, self.NY - 1.001)
        gz = np.clip(z / self.VOXEL_SIZE_M - 0.5, 0.0, self.NZ - 1.001)
        x0, y0, z0 = int(gx), int(gy), int(gz)
        dx, dy, dz = float(gx - x0), float(gy - y0), float(gz - z0)
        c000 = field[..., x0, y0, z0]
        c100 = field[..., x0 + 1, y0, z0]
        c010 = field[..., x0, y0 + 1, z0]
        c110 = field[..., x0 + 1, y0 + 1, z0]
        c001 = field[..., x0, y0, z0 + 1]
        c101 = field[..., x0 + 1, y0, z0 + 1]
        c011 = field[..., x0, y0 + 1, z0 + 1]
        c111 = field[..., x0 + 1, y0 + 1, z0 + 1]
        c00 = c000 * (1 - dx) + c100 * dx
        c10 = c010 * (1 - dx) + c110 * dx
        c01 = c001 * (1 - dx) + c101 * dx
        c11 = c011 * (1 - dx) + c111 * dx
        c0 = c00 * (1 - dy) + c10 * dy
        c1 = c01 * (1 - dy) + c11 * dy
        return c0 * (1 - dz) + c1 * dz

    def query_environment(self, x: float, y: float, z: float) -> Dict[str, object]:
        """Abfrage aller physikalischen und chemischen Größen am 3D-Punkt (x,y,z)."""
        rid = self.classify_room(x, y, z)
        voc_val = np.asarray(self._trilinear_sample(self.voc, x, y, z), dtype=np.float32)
        # Nahfeld-Gradient nur im selben Raum (oder offener EG-Wohn-Küche-Achse) ohne Leckage durch Geschossdecken!
        for f in self.foods:
            same_open_zone = (f.room_id == rid) or ({f.room_id, rid} == {"EG_WOHN_ESS", "EG_KUECHE"})
            if not same_open_zone:
                continue
            d = math.sqrt((x - f.x) ** 2 + (y - f.y) ** 2 + (z - f.z_abs_m) ** 2)
            if d < 1.8:
                near = math.exp(-(d * d) / 0.42)
                voc_val = voc_val + f.current_voc_rates() * np.float32(0.90 * near)
        temp_val = float(self._trilinear_sample(self.temp_c, x, y, z))
        hum_val = float(self._trilinear_sample(self.humidity_pct, x, y, z))
        wind_val = np.asarray(self._trilinear_sample(self.vel, x, y, z), dtype=np.float32)
        light_val = np.asarray(self._trilinear_sample(self.light, x, y, z), dtype=np.float32)
        return {
            "room_id": rid,
            "voc": voc_val,
            "temp_c": temp_val,
            "humidity_pct": hum_val,
            "wind_xyz": wind_val,
            "light_rgb_uv": light_val,
        }

    def classify_room(self, x: float, y: float, z: float) -> str:
        for r in self.rooms:
            for b in r.boxes:
                if b.contains(x, y, z, margin=0.05):
                    return r.room_id
        for p in self.portals:
            if p.box.contains(x, y, z, margin=0.10):
                return p.room_a
        return "EXTERIOR_OR_WALL"

    def is_navigable(self, x: float, y: float, z: float, radius_m: float = 0.005) -> bool:
        """Prüft exakt inkl. Dachschräge, Treppenhaus und 1,5 cm / 2,0 cm Türspalten, ob (x,y,z) frei ist."""
        if x < 0.25 + radius_m or x > 10.75 - radius_m or z < radius_m:
            return False
        if y < 0.25 + radius_m:
            return False
        if y > 9.0:
            # Nur im rückwärtigen Heizungsanbau begehbar
            if not (5.50 + radius_m <= x <= 10.00 - radius_m and 9.00 <= y <= 12.50 - radius_m and 0.0 <= z <= 2.60 - radius_m):
                return False
            return True
        if z >= 5.6 and z > roof_ceiling_z(y) - radius_m:
            return False
        # Prüfe explizite Türspalten, Bogen, Treppenhaus und offene Türen
        for p in self.portals:
            if p.box.contains(x, y, z, margin=0.02):
                if p.kind == "door_gap" and p.gap_height_m is not None:
                    return z <= p.gap_height_m + 0.002
                return True
        # Innerhalb eines der 13 Raumvolumen?
        for r in self.rooms:
            for b in r.boxes:
                if b.contains(x, y, z):
                    # Subtrahiere massive Möbelvolumen (Fliege landet AUF ihnen, dringt nicht ein)
                    for furn in self.furniture:
                        if (
                            furn.x_min <= x <= furn.x_max
                            and furn.y_min <= y <= furn.y_max
                            and furn.z_min <= z < furn.z_max - 0.002
                        ):
                            return False
                    return True
        return False

    def surface_height_below(self, x: float, y: float, z: float) -> Optional[float]:
        """Liefert die nächste tragende horizontale Oberfläche unter (x,y,z) (Boden, Treppenstufe, Möbel)."""
        candidates: List[float] = []
        # Prüfe Möbel-Oberflächen
        for furn in self.furniture:
            if furn.x_min - 0.05 <= x <= furn.x_max + 0.05 and furn.y_min - 0.05 <= y <= furn.y_max + 0.05:
                if furn.z_max <= z + 0.05:
                    candidates.append(furn.z_max)
        # Prüfe Geschossdecken (außer im offenen Treppenhaus!)
        in_stairwell = (8.35 <= x <= 10.75) and (4.95 <= y <= 8.75)
        if not in_stairwell:
            for floor_z in (0.0, 2.8, 5.6):
                if floor_z <= z + 0.05:
                    candidates.append(floor_z)
        else:
            # Treppenstufen im Ost-Treppenhaus approximativ
            candidates.append(0.0)
            if 5.2 <= y <= 8.4:
                step_eg_og = max(0.0, min(2.8, (y - 5.2) / 3.2 * 2.8))
                if step_eg_og <= z + 0.08:
                    candidates.append(step_eg_og)
                step_og_dg = 2.8 + max(0.0, min(2.8, (8.4 - y) / 3.2 * 2.8))
                if step_og_dg <= z + 0.08:
                    candidates.append(step_og_dg)
        return max(candidates) if candidates else None

    def nearest_food_in_contact(self, x: float, y: float, z: float, tol_m: float = 0.20) -> Optional[FoodSubstrate]:
        best: Optional[FoodSubstrate] = None
        best_d = tol_m
        for f in self.foods:
            d = math.sqrt((x - f.x) ** 2 + (y - f.y) ** 2 + (z - f.z_abs_m) ** 2)
            if d <= f.radius_m + tol_m and d < best_d + f.radius_m:
                best = f
                best_d = d
        return best

    def apply_proboscis_feeding(self, food: FoodSubstrate, dt_s: float) -> Tuple[float, float, float]:
        """Rüssel-Extension reduziert Objektmasse und liefert (consumed_mg, energy_mJ, hydration_pct)."""
        rate_mg_per_s = 0.085
        dm_mg = min(food.mass_g * 1000.0 * 0.5, rate_mg_per_s * dt_s)
        food.mass_g = max(0.001, food.mass_g - dm_mg / 1000.0)
        food.mass_consumed_mg += dm_mg
        food.total_feeding_events += 1
        food.total_feeding_time_s += dt_s
        sugar, _acid, water, _bitter = food.gustation_profile
        energy_gain_mj = dm_mg * sugar * 16.5 * 0.25  # aufgenommener nutzbarer Zucker [mJ]
        hydration_gain_pct = dm_mg * water * 4.5
        return dm_mg, energy_gain_mj, hydration_gain_pct

    def apply_environmental_shift(self, scenario: str = "cross_ventilation") -> None:
        """Verändert Luftstrom/Fenster/Wärmezustand dynamisch für Experiment 5."""
        if scenario == "cross_ventilation":
            self.ventilation_boost = 1.8
            self.sim_hour_of_day = 17.0
        elif scenario == "night_cooling":
            self.ventilation_boost = 0.65
            self.sim_hour_of_day = 22.0
        else:
            self.ventilation_boost = 1.0
        self._rebuild_static_microclimate()
        self.warm_up_voc_plumes(steps=60, dt_s=1.0)

    def export_schema(self, path: Optional[Path] = None) -> Dict[str, object]:
        payload = {
            "schema_id": "SIMALITAET_FLY_LAB_SEESTRASSE_43_V1",
            "house_dimensions_m": {
                "main_x_m": 11.0,
                "main_y_m": 9.0,
                "anbau_x_m": 4.5,
                "anbau_y_m": 3.5,
                "eg_z_m": [0.0, 2.8],
                "og_z_m": [2.8, 5.6],
                "dg_z_m": [5.6, 8.2],
                "kniestock_m": 1.1,
                "roof_pitch_deg": 38.0,
                "open_stairwell_m": [2.4, 3.8],
            },
            "voxel_grid": {
                "resolution_m": self.VOXEL_SIZE_M,
                "shape_xyz": [self.NX, self.NY, self.NZ],
                "total_voxels": self.NX * self.NY * self.NZ,
                "air_voxels": int(self.air_mask.sum()),
                "voc_classes": list(VOC_CLASSES),
                "spectral_bands": list(SPECTRAL_BANDS),
                "gustatory_channels": list(GUSTATORY_CHANNELS),
            },
            "woelfersheim_anchor": self.anchor_record,
            "rooms": [
                {
                    "room_id": r.room_id,
                    "floor": r.floor,
                    "function_de": r.function_de,
                    "target_area_m2": r.target_area_m2,
                    "base_temp_c": r.base_temp_c,
                    "base_humidity_pct": r.base_humidity_pct,
                    "has_daylight": r.has_daylight,
                    "features": r.features,
                    "boxes": [asdict(b) for b in r.boxes],
                }
                for r in self.rooms
            ],
            "portals": [
                {
                    "portal_id": p.portal_id,
                    "room_a": p.room_a,
                    "room_b": p.room_b,
                    "kind": p.kind,
                    "gap_height_m": p.gap_height_m,
                    "conductance": p.conductance,
                    "box": asdict(p.box),
                }
                for p in self.portals
            ],
            "food_sources": [asdict(f) for f in self.foods],
        }
        if path is not None:
            self.guard.safe_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))
        return payload
