# -*- coding: utf-8 -*-
"""
Schritt 3: Drei ornithologisch differenzierte Vogelarten mit eigenen Körper-, Flug-,
Sicht-, neuronalen Entscheidungs- und Energiemodellen:
1. Blaumeise (Cyanistes caeruleus)   — agiler UV-Kronen-Absucher & Schwirrjäger
2. Kohlmeise (Parus major)           — Wartenjäger (Perch-and-Sally) an Kompost/Terrasse/Ästen
3. Rauchschwalbe (Hirundo rustica)   — Hochgeschwindigkeits-Luftjäger mit Proportional-Navigation

Wichtige Prinzipien:
- Keine vorprogrammierten Fangergebnisse: Detektion über reales 3D-Sichtfeld,
  Winkelgröße, Sichtlinien-Transmittanz und Bewegungssalienz; Fang nur bei realer
  kontinuierlicher Schnabel-Abfanggeometrie (CPA d_min <= capture_radius).
- Fehlschläge kosten echte Burst-Flugenergie; erfolgreiche Fänge entfernen die Fliege
  aus der Simulation und laden den Vogel-Energiespeicher auf.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from .ecosystem_world import PerchNode, Seestrasse43EcosystemWorld


@dataclass(frozen=True)
class BirdSpeciesProfile:
    species_id: str
    scientific_name: str
    common_name_de: str
    gbif_taxon_key: int
    # [EMPIRICAL_ORNITHOLOGY] Morphologie & Aerodynamik
    mass_kg: float
    wingspan_m: float
    wing_area_m2: float
    aspect_ratio: float
    v_cruise_mps: float
    v_burst_mps: float
    v_min_mps: float
    hover_capable: bool
    max_turn_rad_s: float
    max_climb_rate_mps: float
    max_canopy_density: float
    preferred_perch_kind: str
    preferred_alt_range_m: Tuple[float, float]
    # [EMPIRICAL_ORNITHOLOGY] + [MODEL_ASSUMPTION] Visuelle Sensorik & Jagdstrategie
    fov_half_deg: float
    binocular_half_deg: float
    acuity_scale: float
    max_detect_range_m: float
    canopy_contrast_bonus: float
    ground_contrast_bonus: float
    open_sky_bonus: float
    capture_radius_m: float
    hunting_strategy: str          # "FOLIAGE_GLEAN_HOVER", "PERCH_AND_SALLY", "AERIAL_HAWKING_PN"
    # [MODEL_ASSUMPTION] Skaliertes Energiebudget für mehrminütige Ökosystemläufe
    energy_max_j: float
    energy_initial_j: float
    bmr_perch_w: float
    power_cruise_w: float
    power_hover_w: float
    power_burst_w: float
    prey_assimilated_j: float


SPECIES_PROFILES: Dict[str, BirdSpeciesProfile] = {
    "CYANISTES_CAERULEUS": BirdSpeciesProfile(
        species_id="CYANISTES_CAERULEUS",
        scientific_name="Cyanistes caeruleus",
        common_name_de="Blaumeise",
        gbif_taxon_key=2487879,
        mass_kg=0.011,
        wingspan_m=0.18,
        wing_area_m2=0.0068,
        aspect_ratio=4.8,
        v_cruise_mps=5.2,
        v_burst_mps=8.8,
        v_min_mps=0.0,
        hover_capable=True,
        max_turn_rad_s=6.5,
        max_climb_rate_mps=3.2,
        max_canopy_density=0.86,
        preferred_perch_kind="fine_twig",
        preferred_alt_range_m=(2.2, 7.2),
        fov_half_deg=145.0,
        binocular_half_deg=19.0,
        acuity_scale=0.050,
        max_detect_range_m=8.0,
        canopy_contrast_bonus=1.55,
        ground_contrast_bonus=0.90,
        open_sky_bonus=0.80,
        capture_radius_m=0.16,
        hunting_strategy="FOLIAGE_GLEAN_HOVER",
        energy_max_j=100.0,
        energy_initial_j=62.0,
        bmr_perch_w=0.22,
        power_cruise_w=0.92,
        power_hover_w=2.15,
        power_burst_w=2.95,
        prey_assimilated_j=12.5,
    ),
    "PARUS_MAJOR": BirdSpeciesProfile(
        species_id="PARUS_MAJOR",
        scientific_name="Parus major",
        common_name_de="Kohlmeise",
        gbif_taxon_key=9705453,
        mass_kg=0.018,
        wingspan_m=0.24,
        wing_area_m2=0.0113,
        aspect_ratio=5.1,
        v_cruise_mps=6.8,
        v_burst_mps=11.2,
        v_min_mps=1.0,
        hover_capable=False,
        max_turn_rad_s=4.4,
        max_climb_rate_mps=3.5,
        max_canopy_density=0.45,
        preferred_perch_kind="branch_or_rail",
        preferred_alt_range_m=(0.3, 5.0),
        fov_half_deg=142.0,
        binocular_half_deg=17.0,
        acuity_scale=0.056,
        max_detect_range_m=10.5,
        canopy_contrast_bonus=1.00,
        ground_contrast_bonus=1.50,
        open_sky_bonus=0.95,
        capture_radius_m=0.17,
        hunting_strategy="PERCH_AND_SALLY",
        energy_max_j=145.0,
        energy_initial_j=88.0,
        bmr_perch_w=0.30,
        power_cruise_w=1.45,
        power_hover_w=3.20,
        power_burst_w=3.55,
        prey_assimilated_j=13.0,
    ),
    "HIRUNDO_RUSTICA": BirdSpeciesProfile(
        species_id="HIRUNDO_RUSTICA",
        scientific_name="Hirundo rustica",
        common_name_de="Rauchschwalbe",
        gbif_taxon_key=9515886,
        mass_kg=0.019,
        wingspan_m=0.33,
        wing_area_m2=0.0118,
        aspect_ratio=9.2,
        v_cruise_mps=9.8,
        v_burst_mps=15.8,
        v_min_mps=4.5,
        hover_capable=False,
        max_turn_rad_s=2.8,
        max_climb_rate_mps=4.8,
        max_canopy_density=0.22,
        preferred_perch_kind="roof_eave_wire",
        preferred_alt_range_m=(1.4, 11.5),
        fov_half_deg=135.0,
        binocular_half_deg=24.0,
        acuity_scale=0.078,
        max_detect_range_m=15.0,
        canopy_contrast_bonus=0.45,
        ground_contrast_bonus=0.85,
        open_sky_bonus=1.65,
        capture_radius_m=0.19,
        hunting_strategy="AERIAL_HAWKING_PN",
        energy_max_j=160.0,
        energy_initial_j=98.0,
        bmr_perch_w=0.28,
        power_cruise_w=0.88,
        power_hover_w=3.50,
        power_burst_w=3.10,
        prey_assimilated_j=13.5,
    ),
}


@dataclass
class BirdPerspectiveSample:
    sim_time_s: float
    bird_id: str
    species_id: str
    state: str
    pos: Tuple[float, float, float]
    vel: Tuple[float, float, float]
    speed_mps: float
    energy_j: float
    hunger_drive: float
    r_visual_salience: float
    r_pursuit_gate: float
    r_strike_motor: float
    locked_fly_id: Optional[int]
    locked_dist_m: Optional[float]
    visible_flies: List[Dict[str, object]]  # az_deg, el_deg, dist_m, salience, in_bino, locked


def _closest_approach_3d(p_a0: np.ndarray, p_a1: np.ndarray, p_b0: np.ndarray, p_b1: np.ndarray) -> float:
    """Exakter minimaler Abstand [m] zweier linear bewegter Körper während eines Zeitschritts."""
    r0 = p_a0 - p_b0
    dv = (p_a1 - p_a0) - (p_b1 - p_b0)
    dv2 = float(np.dot(dv, dv))
    if dv2 < 1e-12:
        return float(np.linalg.norm(r0))
    t = float(np.clip(-np.dot(r0, dv) / dv2, 0.0, 1.0))
    return float(np.linalg.norm(r0 + t * dv))


class BirdAgent:
    """Autonomes Individuum einer der drei Vogelarten mit eigenem Sicht-, Neural- und Flugmodell."""

    def __init__(
        self,
        bird_id: str,
        profile: BirdSpeciesProfile,
        start_pos: Tuple[float, float, float],
        patrol_center: Tuple[float, float, float],
        seed: int = 1001,
        vision_gain: float = 1.0,
    ) -> None:
        self.bird_id = bird_id
        self.profile = profile
        self.rng = np.random.default_rng(seed)
        self.vision_gain = float(vision_gain)

        self.pos = np.asarray(start_pos, dtype=np.float64)
        ang0 = float(self.rng.uniform(0.0, 2.0 * math.pi))
        v0 = profile.v_cruise_mps * 0.65 if not profile.hover_capable else 1.5
        self.vel = np.array([v0 * math.cos(ang0), v0 * math.sin(ang0), 0.0], dtype=np.float64)
        self.heading = self.vel / max(1e-6, float(np.linalg.norm(self.vel)))
        self.patrol_center = np.asarray(patrol_center, dtype=np.float64)
        self.patrol_phase: float = float(self.rng.uniform(0.0, 2.0 * math.pi))

        # Status & Energiemodell
        self.alive: bool = True
        self.state: str = "PATROLLING" if profile.hunting_strategy == "AERIAL_HAWKING_PN" else "PERCHING"
        self.energy_j: float = float(profile.energy_initial_j)
        self.exhausted_events: int = 0
        self.perch_timer_s: float = float(self.rng.uniform(0.4, 1.8)) if self.state == "PERCHING" else 0.0
        self.strike_cooldown_s: float = 0.0
        self.scan_yaw_offset: float = 0.0

        # Kontinuierliche neuronale Zustandsvariablen (Tectum / Forebrain-Motorik-Proxy)
        self.r_visual: float = 0.0
        self.r_hunger: float = 0.4
        self.r_pursuit: float = 0.0
        self.r_strike: float = 0.0

        # Laufendes Ziel-Tracking (ohne Orakel)
        self.target_slot: Optional[int] = None
        self.target_fly_id: Optional[int] = None
        self.prev_target_pos: Optional[np.ndarray] = None
        self.in_strike_attempt: bool = False
        self.strike_min_dist: float = 99.0
        self.last_perceived_bearing: np.ndarray = self.heading.copy()

        # Bilanz-Metriken
        self.catches: int = 0
        self.missed_strikes: int = 0
        self.detections: int = 0
        self.energy_spent_j: float = 0.0
        self.energy_gained_j: float = 0.0
        self.flight_distance_m: float = 0.0
        self.zone_time_s: Dict[str, float] = {"canopy": 0.0, "edge_ground": 0.0, "open_air": 0.0}
        self.perspective_history: List[BirdPerspectiveSample] = []

    def _select_target_perch(self, world: Seestrasse43EcosystemWorld) -> PerchNode:
        cands = [p for p in world.perches if self.profile.species_id in p.preferred_species]
        if not cands:
            cands = world.perches
        best = min(cands, key=lambda p: float(np.linalg.norm(np.asarray(p.pos) - self.pos)) + float(self.rng.uniform(0.0, 2.0)))
        return best

    def perceive_flies(
        self,
        world: Seestrasse43EcosystemWorld,
        fly_slots: np.ndarray,
        fly_ids: np.ndarray,
        fly_pos: np.ndarray,
        fly_vel: np.ndarray,
        los_vec: Optional[np.ndarray] = None,
        fly_canopy_vec: Optional[np.ndarray] = None,
    ) -> Tuple[Optional[int], float, np.ndarray, List[Dict[str, object]]]:
        """
        Reale 3D-Sichtwahrnehmung ohne Orakel-Koordinaten:
        Prüft Kegelwinkel (FOV), Winkelgröße, Sichtlinien-Transmittanz durch Haus & Laub,
        sowie Habitatkontrast (UV-Krone vs. Boden vs. offener Himmel).
        """
        if len(fly_slots) == 0:
            return None, 0.0, self.heading, []

        p = self.profile
        h = self.heading / max(1e-6, float(np.linalg.norm(self.heading)))
        up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        right = np.cross(h, up)
        nr = float(np.linalg.norm(right))
        right = right / nr if nr > 1e-4 else np.array([0.0, -1.0, 0.0], dtype=np.float64)
        cam_up = np.cross(right, h)

        fov_cos = math.cos(math.radians(p.fov_half_deg))
        max_r = p.max_detect_range_m * max(0.35, self.vision_gain)
        fp_all = fly_pos[fly_slots].astype(np.float64)
        fv_all = fly_vel[fly_slots].astype(np.float64)

        diff = fp_all - self.pos[None, :]
        dist = np.linalg.norm(diff, axis=-1)
        u = diff / np.maximum(dist[:, None], 1e-9)
        cos_ang = u @ h

        if los_vec is None:
            los_arr = world.compute_los_matrix(fp_all, self.pos[None, :])[:, 0].astype(np.float64)
        else:
            los_arr = np.asarray(los_vec, dtype=np.float64)
        if fly_canopy_vec is None:
            canopy_arr = world.max_canopy_density_vec(fp_all).astype(np.float64)
        else:
            canopy_arr = np.asarray(fly_canopy_vec, dtype=np.float64)

        valid = (dist >= 0.02) & (dist <= max_r) & (cos_ang >= fov_cos) & (los_arr >= 0.14)
        if p.hunting_strategy == "AERIAL_HAWKING_PN":
            valid &= canopy_arr <= (p.max_canopy_density + 0.08)

        if not np.any(valid):
            return None, 0.0, h, []

        fly_speed = np.linalg.norm(fv_all, axis=-1)
        motion_boost = 1.0 + 0.85 * np.minimum(1.5, fly_speed)
        niche_bonus = np.where(
            canopy_arr >= 0.25,
            p.canopy_contrast_bonus,
            np.where(fp_all[:, 2] <= 1.5, p.ground_contrast_bonus, p.open_sky_bonus),
        )
        salience = (p.acuity_scale / np.maximum(0.32, dist)) * los_arr * niche_bonus * motion_boost * self.vision_gain
        rain_vis = float(getattr(world, "rain_vis_factor", 1.0))
        if rain_vis < 0.999:
            salience = salience * rain_vis
        if self.target_slot is not None:
            salience = np.where(fly_slots == int(self.target_slot), salience * 1.38, salience)

        keep = valid & (salience >= 0.0065)
        if not np.any(keep):
            return None, 0.0, h, []

        best_idx = int(np.argmax(np.where(keep, salience, -1.0)))
        best_slot = int(fly_slots[best_idx])
        best_salience = float(salience[best_idx])
        best_dir = u[best_idx].copy()

        vis_list: List[Dict[str, object]] = []
        for idx_s in np.where(keep)[0]:
            slot = int(fly_slots[idx_s])
            ui = u[idx_s]
            el_deg = math.degrees(math.asin(float(np.clip(float(np.dot(ui, cam_up)), -1.0, 1.0))))
            az_deg = math.degrees(math.atan2(float(np.dot(ui, right)), max(1e-6, float(cos_ang[idx_s]))))
            vis_list.append({
                "fly_id": int(fly_ids[slot]),
                "slot": slot,
                "az_deg": round(az_deg, 1),
                "el_deg": round(el_deg, 1),
                "dist_m": round(float(dist[idx_s]), 2),
                "salience": round(float(salience[idx_s]), 4),
                "in_bino": abs(az_deg) <= p.binocular_half_deg,
            })

        # Sensorisches Winkelrauschen (verschlechtert sich bei Vision-Ablation!)
        sigma_ang = 0.018 / max(0.25, self.vision_gain)
        noisy = best_dir + self.rng.normal(0.0, sigma_ang, size=3)
        n = float(np.linalg.norm(noisy))
        if n > 1e-6:
            best_dir = noisy / n
        return best_slot, best_salience, best_dir, vis_list

    def step(
        self,
        world: Seestrasse43EcosystemWorld,
        fly_pop,
        dt_s: float = 0.025,
        record_perspective: bool = False,
        alive_slots: Optional[np.ndarray] = None,
        los_vec: Optional[np.ndarray] = None,
        fly_canopy_vec: Optional[np.ndarray] = None,
    ) -> Dict[str, object]:
        """Führt einen autonomen 25-ms-Sicht-, Entscheidungs-, Flug- & Jagdschritt durch."""
        p = self.profile
        self.strike_cooldown_s = max(0.0, self.strike_cooldown_s - dt_s)
        pos_prev = self.pos.copy()
        event_out: Dict[str, object] = {"catch": False, "miss": False, "fly_id": None}

        # 1. Hunger- und Erschöpfungszustand
        e_frac = float(np.clip(self.energy_j / p.energy_max_j, 0.0, 1.0))
        self.r_hunger = float(np.clip(1.25 - 1.10 * e_frac, 0.12, 1.25))
        satiated = e_frac >= 0.92 and self.in_strike_attempt is False

        # 2. Sichtwahrnehmung aller lebenden Fliegen
        slots_use = alive_slots if alive_slots is not None else fly_pop.alive_slots()
        slot_det, salience, sight_dir, vis_list = self.perceive_flies(
            world,
            slots_use,
            fly_pop.fly_ids,
            fly_pop.pos,
            fly_pop.vel,
            los_vec=los_vec,
            fly_canopy_vec=fly_canopy_vec,
        )

        self.r_visual = float(0.65 * self.r_visual + 0.35 * min(1.0, salience * 22.0))
        if slot_det is not None and slot_det != self.target_slot:
            self.detections += 1

        # 3. Kontinuierliche Entscheidungslogik pro Art (Perch / Patrol / Pursuit / Strike)
        if self.state == "PERCHING":
            self.perch_timer_s -= dt_s
            self.scan_yaw_offset += 1.6 * math.sin(world.sim_time_s * 3.1) * dt_s
            self.heading = np.array([math.cos(self.scan_yaw_offset), math.sin(self.scan_yaw_offset), -0.05], dtype=np.float64)
            self.heading /= float(np.linalg.norm(self.heading))
            self.vel[:] = 0.0
            self.r_pursuit = 0.0
            self.r_strike = 0.0
            if (slot_det is not None and not satiated and self.strike_cooldown_s <= 0.0) or (
                self.perch_timer_s <= 0.0 and not satiated
            ):
                self.state = "PURSUING" if slot_det is not None else "PATROLLING"
                self.target_slot = slot_det
                if slot_det is not None:
                    self.target_fly_id = int(fly_pop.fly_ids[slot_det])
                    self.prev_target_pos = fly_pop.pos[slot_det].astype(np.float64).copy()
                    self.in_strike_attempt = False
                    self.strike_min_dist = 99.0

        # Wenn fliegend: Verfolgung / Streifenflug / Sitzwarten-Erholung
        desired_speed = p.v_cruise_mps
        desired_dir = self.heading.copy()
        power_w = p.power_cruise_w

        if self.state != "PERCHING":
            if slot_det is not None and not satiated and self.strike_cooldown_s <= 0.0:
                self.target_slot = slot_det
                self.target_fly_id = int(fly_pop.fly_ids[slot_det])
                tf_pos = fly_pop.pos[slot_det].astype(np.float64)
                tf_pos_prev = self.prev_target_pos if self.prev_target_pos is not None else tf_pos
                dist_now = float(np.linalg.norm(tf_pos - self.pos))
                self.state = "STRIKE_ATTEMPT" if dist_now <= 0.85 else "PURSUING"
                self.r_pursuit = float(np.clip(self.r_visual * self.r_hunger * 1.4, 0.2, 1.0))

                # Abbruch falls Beute für Rauchschwalbe zu tief ins Laub eintaucht
                if world.canopy_density_at(tf_pos) > p.max_canopy_density + 0.04:
                    if self.in_strike_attempt:
                        self.missed_strikes += 1
                        event_out = {"catch": False, "miss": True, "fly_id": self.target_fly_id}
                    self.target_slot = None
                    self.in_strike_attempt = False
                    self.strike_cooldown_s = 1.1
                    self.state = "PATROLLING"
                else:
                    # Artspezifische Jagd-Führung (Pure Pursuit + Hover vs. Sally vs. Proportional Navigation!)
                    if p.hunting_strategy == "AERIAL_HAWKING_PN":
                        # Proportional-Navigation: Vorhalt auf Basis geschaetzter Zielgeschwindigkeit aus letztem Wahrnehmungs-Delta
                        v_est = (tf_pos - tf_pos_prev) / max(1e-4, dt_s)
                        t_lead = min(0.28, dist_now / max(3.0, p.v_burst_mps))
                        aim_pt = tf_pos + v_est * t_lead
                        diff_aim = aim_pt - self.pos
                        desired_dir = diff_aim / max(1e-6, float(np.linalg.norm(diff_aim)))
                        desired_speed = p.v_burst_mps if dist_now < 4.5 else p.v_cruise_mps * 1.15
                        power_w = p.power_burst_w if dist_now < 4.0 else p.power_cruise_w
                    elif p.hunting_strategy == "FOLIAGE_GLEAN_HOVER":
                        desired_dir = sight_dir
                        if dist_now < 1.0:
                            # Kurzer Schnabel-Vorstoß in letzter Annäherungsphase
                            desired_speed = 6.4
                            power_w = p.power_burst_w * 0.90
                        elif dist_now < 2.2:
                            # Schwirr-/Schwebeflug beim Absuchen des Blattwerks
                            desired_speed = 3.4
                            power_w = p.power_hover_w
                        else:
                            desired_speed = p.v_burst_mps * 0.85
                            power_w = p.power_burst_w * 0.85
                    else:  # Kohlmeise PERCH_AND_SALLY
                        desired_dir = sight_dir
                        desired_speed = p.v_burst_mps if dist_now < 3.5 else p.v_cruise_mps
                        power_w = p.power_burst_w if dist_now < 3.5 else p.power_cruise_w

                    self.r_strike = 1.0 if self.state == "STRIKE_ATTEMPT" else 0.35
                    if self.state == "STRIKE_ATTEMPT":
                        self.in_strike_attempt = True
                        self.strike_min_dist = min(self.strike_min_dist, dist_now)

                self.prev_target_pos = tf_pos.copy()
            else:
                # Ziel verloren oder kein Ziel -> falls zuvor im Strike-Anflug: echtes Verfehlen zählen!
                if self.in_strike_attempt:
                    self.missed_strikes += 1
                    event_out = {"catch": False, "miss": True, "fly_id": self.target_fly_id}
                    self.in_strike_attempt = False
                    self.strike_cooldown_s = 1.0
                self.target_slot = None
                self.target_fly_id = None
                self.prev_target_pos = None
                self.r_pursuit = 0.0
                self.r_strike = 0.0

                # Rückkehr zur Sitzwarte bei Meisen (oder satter/verregneter Rauchschwalbe) bzw. freier Streifenflug
                rain_cur = float(getattr(world, "rain_mm_h", 0.0))
                should_rest = (
                    (p.hunting_strategy != "AERIAL_HAWKING_PN" and self.rng.random() < 0.025)
                    or (p.hunting_strategy == "AERIAL_HAWKING_PN" and rain_cur >= 6.5)
                    or satiated
                    or e_frac < 0.14
                )
                if should_rest:
                    perch = self._select_target_perch(world)
                    to_p = np.asarray(perch.pos, dtype=np.float64) - self.pos
                    dp = float(np.linalg.norm(to_p))
                    if dp <= 0.55:
                        self.state = "PERCHING"
                        self.perch_timer_s = 3.5 if satiated else float(self.rng.uniform(0.9, 2.2))
                        self.pos = np.asarray(perch.pos, dtype=np.float64)
                        self.vel[:] = 0.0
                        desired_speed = 0.0
                        power_w = p.bmr_perch_w
                    else:
                        desired_dir = to_p / dp
                        desired_speed = p.v_cruise_mps * 0.8
                        power_w = p.power_cruise_w
                        self.state = "PATROLLING"
                else:
                    self.state = "PATROLLING"
                    # Artspezifische Acht-/Revierflugbahn um bevorzugte Zone & Höhe
                    if p.hunting_strategy == "AERIAL_HAWKING_PN":
                        omega_pat, rx, ry, z_amp = 0.55, 10.5, 7.5, 0.45 * (p.preferred_alt_range_m[1] - p.preferred_alt_range_m[0])
                    elif p.hunting_strategy == "FOLIAGE_GLEAN_HOVER":
                        omega_pat, rx, ry, z_amp = 1.15, 2.1, 1.9, 0.85
                    else:  # PERCH_AND_SALLY
                        omega_pat, rx, ry, z_amp = 0.85, 4.2, 3.6, 0.40 * (p.preferred_alt_range_m[1] - p.preferred_alt_range_m[0])
                    self.patrol_phase = (self.patrol_phase + omega_pat * dt_s) % (2.0 * math.pi)
                    wp = self.patrol_center + np.array(
                        [
                            rx * math.cos(self.patrol_phase),
                            ry * math.sin(2.0 * self.patrol_phase if p.hunting_strategy == "AERIAL_HAWKING_PN" else self.patrol_phase),
                            z_amp * math.sin(self.patrol_phase * 1.5),
                        ],
                        dtype=np.float64,
                    )
                    wp[2] = np.clip(wp[2], p.preferred_alt_range_m[0], p.preferred_alt_range_m[1])
                    to_w = wp - self.pos
                    dw = float(np.linalg.norm(to_w)) + 1e-5
                    desired_dir = to_w / dw
                    desired_speed = p.v_cruise_mps
                    power_w = p.power_cruise_w

            # 4. Physische Dreh- und Beschleunigungskinematik (begrenzt durch max_turn_rad_s & v_min)
            if desired_speed > 0.05:
                # Hindernisabstoßung vor zu dichter Krone nur beim freien Streifenflug (nicht bei aktiver Jagd)
                if self.state == "PATROLLING" and world.canopy_density_at(self.pos + desired_dir * 1.0) > p.max_canopy_density:
                    desired_dir[2] += 0.35
                    desired_dir[0] *= -0.5
                    desired_dir /= max(1e-6, float(np.linalg.norm(desired_dir)))

                cur_h = self.heading / max(1e-6, float(np.linalg.norm(self.heading)))
                dot_c = float(np.clip(np.dot(cur_h, desired_dir), -1.0, 1.0))
                ang_diff = math.acos(dot_c)
                max_d_ang = p.max_turn_rad_s * dt_s
                if ang_diff > max_d_ang and ang_diff > 1e-5:
                    t_sl = max_d_ang / ang_diff
                    new_h = (1.0 - t_sl) * cur_h + t_sl * desired_dir
                else:
                    new_h = desired_dir
                nh = float(np.linalg.norm(new_h))
                self.heading = new_h / nh if nh > 1e-6 else cur_h

                cur_spd = float(np.linalg.norm(self.vel))
                target_spd = float(np.clip(desired_speed, p.v_min_mps, p.v_burst_mps))
                new_spd = 0.72 * cur_spd + 0.28 * target_spd
                self.vel = self.heading * new_spd
                next_pos = self.pos + self.vel * dt_s
                self.pos, self.vel = world.clamp_bird_outside_obstacles(next_pos, self.vel, margin=0.22)
                n_v = float(np.linalg.norm(self.vel))
                if n_v > 1e-4:
                    self.heading = self.vel / n_v

            # 5. Physische CPA-Abfangprüfung (keine vordefinierten Fangergebnisse!)
            if self.target_slot is not None and fly_pop.active[self.target_slot] and self.in_strike_attempt:
                ts = self.target_slot
                fp_now = fly_pop.pos[ts].astype(np.float64)
                fv_now = fly_pop.vel[ts].astype(np.float64)
                fp_prev = fp_now - fv_now * dt_s
                d_cpa = _closest_approach_3d(pos_prev, self.pos, fp_prev, fp_now)
                d_now = float(np.linalg.norm(fp_now - self.pos))
                los_now = world.line_of_sight_transmittance(self.pos, fp_now)
                u_now = (fp_now - self.pos) / max(1e-5, d_now)
                beak_aligned = float(np.dot(self.heading, u_now)) > 0.35 or d_cpa <= p.capture_radius_m

                if d_cpa <= p.capture_radius_m and los_now >= 0.22 and beak_aligned:
                    killed_id = fly_pop.kill_fly(ts, f"CAPTURED_{p.species_id}", species_id=p.species_id)
                    self.catches += 1
                    e_gain = p.prey_assimilated_j
                    self.energy_j = min(p.energy_max_j, self.energy_j + e_gain)
                    self.energy_gained_j += e_gain
                    event_out = {"catch": True, "miss": False, "fly_id": killed_id}
                    self.target_slot = None
                    self.target_fly_id = None
                    self.in_strike_attempt = False
                    self.strike_cooldown_s = 1.2
                    if p.hunting_strategy != "AERIAL_HAWKING_PN":
                        self.state = "PATROLLING"
                elif d_now > self.strike_min_dist + 0.22 and d_now > 0.68:
                    # Fliege ist erfolgreich entkommen (z.B. per LC4/DNp01-Ausweichsprung) -> Fehlschlag!
                    self.missed_strikes += 1
                    event_out = {"catch": False, "miss": True, "fly_id": self.target_fly_id}
                    self.target_slot = None
                    self.target_fly_id = None
                    self.in_strike_attempt = False
                    self.strike_cooldown_s = 1.0
                else:
                    self.strike_min_dist = min(self.strike_min_dist, d_now)
        else:
            power_w = p.bmr_perch_w

        # Regen-Flugwiderstand erhöht Energieverbrauch bei aktivem Flug (0 bei trockenem Wetter)
        rain_cur_e = float(getattr(world, "rain_mm_h", 0.0))
        if rain_cur_e > 0.05 and self.state != "PERCHING":
            power_w *= (1.0 + 0.022 * min(12.0, rain_cur_e))

        # 6. Energieverbrauch & Zonenstatistik
        de_j = power_w * dt_s
        self.energy_spent_j += de_j
        self.energy_j = max(0.0, self.energy_j - de_j)
        if self.energy_j <= 0.2:
            self.exhausted_events += 1
            self.state = "PERCHING"
            self.perch_timer_s = 4.0
            self.vel[:] = 0.0

        self.flight_distance_m += float(np.linalg.norm(self.pos - pos_prev))
        cdens = world.canopy_density_at(self.pos)
        if cdens >= 0.25:
            self.zone_time_s["canopy"] += dt_s
        elif self.pos[2] <= 2.4:
            self.zone_time_s["edge_ground"] += dt_s
        else:
            self.zone_time_s["open_air"] += dt_s

        if record_perspective:
            self.perspective_history.append(
                BirdPerspectiveSample(
                    sim_time_s=round(world.sim_time_s, 3),
                    bird_id=self.bird_id,
                    species_id=p.species_id,
                    state=self.state,
                    pos=(round(float(self.pos[0]), 3), round(float(self.pos[1]), 3), round(float(self.pos[2]), 3)),
                    vel=(round(float(self.vel[0]), 3), round(float(self.vel[1]), 3), round(float(self.vel[2]), 3)),
                    speed_mps=round(float(np.linalg.norm(self.vel)), 2),
                    energy_j=round(float(self.energy_j), 2),
                    hunger_drive=round(float(self.r_hunger), 3),
                    r_visual_salience=round(float(self.r_visual), 4),
                    r_pursuit_gate=round(float(self.r_pursuit), 3),
                    r_strike_motor=round(float(self.r_strike), 3),
                    locked_fly_id=self.target_fly_id,
                    locked_dist_m=round(float(np.linalg.norm(fly_pop.pos[self.target_slot] - self.pos)), 2)
                    if (self.target_slot is not None and fly_pop.active[self.target_slot])
                    else None,
                    visible_flies=vis_list[:12],
                )
            )
        return event_out
