# -*- coding: utf-8 -*-
"""
Modul D: Strikte Welt -> Fliege Sensor-Schnittstelle (Δt = 10 ms).

Bildet den exakten Sensor-Input-Vektor gemäß Seestraße-43-Spezifikation:
- Stereo-Olfaktorik (Linke/Rechte Antenne: Konzentration C & zeitliche Ableitung dC/dt für 8 VOC-Klassen)
- Visuelles System (UV-A, Blau, Grün je Auge, Kontrastkanten-Ring, optischer Fluss / Looming, Lichtrichtung)
- Mechanosensorik & Thermorezeptoren (Johnston-Organ v_local im Körperkoordinatensystem, T_local, is_landed)
- Gustatorik (nur bei Tarsen-/Rüsselkontakt: Zucker, Säure, Wasser, Bitterstoffe)

Wissenschaftliche Kennzeichnung:
[MODEL_ASSUMPTION] Die effektive bilaterale Antennen-Gradienten-Verstärkung (osmotropotaxis_gain)
skaliert die 0,35-mm-Kopfbasis auf das 0,25-m-Raumluftgitter, gekoppelt mit echter zeitlicher
dC/dt-Klinokinese und Johnston-Organ-Anemotaxis (Duistermars et al. 2009 / Alvarez-Salvado et al. 2018).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Optional, Tuple

import numpy as np

from .seestrasse_43_world import (
    FoodSubstrate,
    GUSTATORY_CHANNELS,
    SPECTRAL_BANDS,
    Seestrasse43World,
    VOC_CLASSES,
)


@dataclass(frozen=True)
class SensorInputVector:
    sim_time_s: float
    dt_s: float
    room_id: str
    # Olfaktorik: 8 chemische Klassen je Antenne + dC/dt [a.u. / s]
    olfaction_conc_left: np.ndarray
    olfaction_conc_right: np.ndarray
    olfaction_dcdt_left: np.ndarray
    olfaction_dcdt_right: np.ndarray
    # Vision: (3,) = (UV-A, Blue, Green) pro Facettenauge, 8 Kontrastsektoren, 6 Looming-Strahlen, Lichtvektor
    vision_spectral_left: np.ndarray
    vision_spectral_right: np.ndarray
    vision_contrast_edges: np.ndarray
    optical_flow_looming: np.ndarray  # [front, front_left, front_right, up, down, back] [1/s]
    light_dir_body: np.ndarray        # Einheitsvektor zum hellsten Gradienten im Körperrahmen
    # Mechanosensorik & Thermorezeptoren / Hygrorezeptoren
    wind_local_body: np.ndarray       # Relativer Luftstrom v_air - v_fly im Körperrahmen [m/s]
    temp_local_c: float
    humidity_local_pct: float
    is_landed: bool
    # Gustatorik (Tarsen / Rüssel, strikt 0 ohne Kontakt!)
    gustation_contact: np.ndarray     # [sugar, acid, water, bitter] in [0..1]
    contact_food_id: Optional[str]


class FlySensoryInterface:
    """Berechnet den deterministischen Δt = 10 ms SensorInputVector aus der 3D-Welt."""

    # Biologischer Antennenabstand ~0,35 mm; effektive Gradientenskalierung für 0,25-m-Voxelplumes [MODEL_ASSUMPTION]
    PHYSICAL_ANTENNA_HALF_SPAN_M: float = 0.000175
    EFFECTIVE_GRADIENT_SPAN_M: float = 0.045

    def __init__(self, olfaction_enabled: bool = True, vision_enabled: bool = True, looming_enabled: bool = True,
                 left_antenna_intact: bool = True, right_antenna_intact: bool = True) -> None:
        self.olfaction_enabled = olfaction_enabled
        self.vision_enabled = vision_enabled
        self.looming_enabled = looming_enabled
        self.left_antenna_intact = left_antenna_intact
        self.right_antenna_intact = right_antenna_intact
        self._prev_conc_left = np.zeros(len(VOC_CLASSES), dtype=np.float32)
        self._prev_conc_right = np.zeros(len(VOC_CLASSES), dtype=np.float32)
        self._initialized = False

    def reset(self) -> None:
        self._prev_conc_left.fill(0.0)
        self._prev_conc_right.fill(0.0)
        self._initialized = False

    @staticmethod
    def _world_to_body(vec_xyz: np.ndarray, yaw_rad: float, pitch_rad: float = 0.0) -> np.ndarray:
        cy, sy = math.cos(yaw_rad), math.sin(yaw_rad)
        cp, sp = math.cos(pitch_rad), math.sin(pitch_rad)
        vx, vy, vz = float(vec_xyz[0]), float(vec_xyz[1]), float(vec_xyz[2])
        # Horizontal in Körper-X/Y drehen
        bx = cy * vx + sy * vy
        by = -sy * vx + cy * vy
        # Nickwinkel berücksichtigen
        bx2 = cp * bx + sp * vz
        bz2 = -sp * bx + cp * vz
        return np.array([bx2, by, bz2], dtype=np.float32)

    def _raycast_wall_distance(
        self, world: Seestrasse43World, origin: np.ndarray, dir_xyz: np.ndarray, max_dist_m: float = 1.25, step_m: float = 0.14
    ) -> float:
        d = step_m
        while d <= max_dist_m:
            p = origin + d * dir_xyz
            if not world.is_navigable(float(p[0]), float(p[1]), float(p[2]), radius_m=0.005):
                return d
            d += step_m
        return max_dist_m

    def sense(
        self,
        world: Seestrasse43World,
        pos_xyz: np.ndarray,
        vel_xyz: np.ndarray,
        yaw_rad: float,
        pitch_rad: float,
        is_landed: bool,
        dt_s: float = 0.010,
    ) -> SensorInputVector:
        x, y, z = float(pos_xyz[0]), float(pos_xyz[1]), float(pos_xyz[2])
        q_center = world.query_environment(x, y, z)
        left_vec = np.array([-math.sin(yaw_rad), math.cos(yaw_rad), 0.0], dtype=np.float32)
        fwd_vec = np.array([math.cos(yaw_rad), math.sin(yaw_rad), 0.0], dtype=np.float32)

        # 1. Stereo-Olfaktorik (8 Klassen x 2 Antennen)
        if self.olfaction_enabled:
            span = self.EFFECTIVE_GRADIENT_SPAN_M
            p_l = pos_xyz + span * left_vec + 0.01 * fwd_vec
            p_r = pos_xyz - span * left_vec + 0.01 * fwd_vec
            c_left = np.asarray(world.query_environment(float(p_l[0]), float(p_l[1]), float(p_l[2]))["voc"], dtype=np.float32)
            c_right = np.asarray(world.query_environment(float(p_r[0]), float(p_r[1]), float(p_r[2]))["voc"], dtype=np.float32)
            if not self.left_antenna_intact:
                c_left = np.zeros(len(VOC_CLASSES), dtype=np.float32)
            if not self.right_antenna_intact:
                c_right = np.zeros(len(VOC_CLASSES), dtype=np.float32)
        else:
            c_left = np.zeros(len(VOC_CLASSES), dtype=np.float32)
            c_right = np.zeros(len(VOC_CLASSES), dtype=np.float32)

        if self._initialized and dt_s > 0.0:
            dcdt_l = ((c_left - self._prev_conc_left) / np.float32(dt_s)).astype(np.float32)
            dcdt_r = ((c_right - self._prev_conc_right) / np.float32(dt_s)).astype(np.float32)
        else:
            dcdt_l = np.zeros(len(VOC_CLASSES), dtype=np.float32)
            dcdt_r = np.zeros(len(VOC_CLASSES), dtype=np.float32)
            self._initialized = True
        self._prev_conc_left = c_left.copy()
        self._prev_conc_right = c_right.copy()

        # 2. Facettenaugen: Spektrallicht, räumliche Kontraste, Lichtgradient & Looming-Fluss
        looming = np.zeros(6, dtype=np.float32)
        contrast = np.zeros(8, dtype=np.float32)
        if self.vision_enabled:
            eye_offset = 0.08
            pl_eye = pos_xyz + eye_offset * (0.5 * fwd_vec + 0.866 * left_vec)
            pr_eye = pos_xyz + eye_offset * (0.5 * fwd_vec - 0.866 * left_vec)
            pf_eye = pos_xyz + 0.20 * fwd_vec
            pu_eye = pos_xyz + np.array([0.0, 0.0, 0.20], dtype=np.float32)
            spec_l = np.asarray(world.query_environment(float(pl_eye[0]), float(pl_eye[1]), float(pl_eye[2]))["light_rgb_uv"], dtype=np.float32)
            spec_r = np.asarray(world.query_environment(float(pr_eye[0]), float(pr_eye[1]), float(pr_eye[2]))["light_rgb_uv"], dtype=np.float32)
            spec_f = np.asarray(world.query_environment(float(pf_eye[0]), float(pf_eye[1]), float(pf_eye[2]))["light_rgb_uv"], dtype=np.float32)
            spec_u = np.asarray(world.query_environment(float(pu_eye[0]), float(pu_eye[1]), float(pu_eye[2]))["light_rgb_uv"], dtype=np.float32)
            spec_c = np.asarray(q_center["light_rgb_uv"], dtype=np.float32)

            grad_light_world = np.array(
                [
                    float((spec_f.sum() - spec_c.sum()) * fwd_vec[0] + (spec_l.sum() - spec_r.sum()) * left_vec[0]),
                    float((spec_f.sum() - spec_c.sum()) * fwd_vec[1] + (spec_l.sum() - spec_r.sum()) * left_vec[1]),
                    float(spec_u.sum() - spec_c.sum()),
                ],
                dtype=np.float32,
            )
            norm = float(np.linalg.norm(grad_light_world))
            light_dir_body = (
                self._world_to_body(grad_light_world / norm, yaw_rad, pitch_rad)
                if norm > 1e-6
                else np.zeros(3, dtype=np.float32)
            )

            # Azimutale Wandabstände & optischer Expansionsfluss (r_dot / r = (v·d)/d^2)
            ray_dirs_world = [
                fwd_vec,
                0.707 * fwd_vec + 0.707 * left_vec,
                0.707 * fwd_vec - 0.707 * left_vec,
                np.array([0.0, 0.0, 1.0], dtype=np.float32),
                np.array([0.0, 0.0, -1.0], dtype=np.float32),
                -fwd_vec,
            ]
            dists = [self._raycast_wall_distance(world, pos_xyz, rd, max_dist_m=1.25, step_m=0.14) for rd in ray_dirs_world]
            for idx_r, (rd, dist_m) in enumerate(zip(ray_dirs_world, dists)):
                contrast[idx_r] = np.float32(min(1.0, 0.25 / max(0.05, dist_m)))
                if self.looming_enabled:
                    v_app = max(0.0, float(np.dot(vel_xyz, rd)))
                    # Nahbereichs-Kollisionswarner kombiniert Annäherungsfluss v/d mit kritischem Abstand (<0,32 m)
                    looming[idx_r] = np.float32(v_app / max(0.08, dist_m) + (0.65 if dist_m < 0.26 else 0.0))
            contrast[6] = np.float32(abs(spec_l.sum() - spec_r.sum()))
            contrast[7] = np.float32(min(1.0, float(spec_f.sum())))
        else:
            spec_l = np.zeros(len(SPECTRAL_BANDS), dtype=np.float32)
            spec_r = np.zeros(len(SPECTRAL_BANDS), dtype=np.float32)
            light_dir_body = np.zeros(3, dtype=np.float32)

        # 3. Mechanosensorik (Johnston-Organ: v_air - v_fly), Temp & Feuchte
        wind_rel_world = np.asarray(q_center["wind_xyz"], dtype=np.float32) - np.asarray(vel_xyz, dtype=np.float32)
        wind_local_body = self._world_to_body(wind_rel_world, yaw_rad, pitch_rad)

        # 4. Gustatorik strikt nur bei Kontakt!
        food = world.nearest_food_in_contact(x, y, z, tol_m=0.18) if is_landed else None
        if food is not None:
            gust = np.asarray(food.gustation_profile, dtype=np.float32)
            contact_food_id: Optional[str] = food.food_id
        else:
            gust = np.zeros(len(GUSTATORY_CHANNELS), dtype=np.float32)
            contact_food_id = None

        return SensorInputVector(
            sim_time_s=world.sim_time_s,
            dt_s=dt_s,
            room_id=str(q_center["room_id"]),
            olfaction_conc_left=c_left,
            olfaction_conc_right=c_right,
            olfaction_dcdt_left=dcdt_l,
            olfaction_dcdt_right=dcdt_r,
            vision_spectral_left=spec_l,
            vision_spectral_right=spec_r,
            vision_contrast_edges=contrast,
            optical_flow_looming=looming,
            light_dir_body=light_dir_body,
            wind_local_body=wind_local_body,
            temp_local_c=float(q_center["temp_c"]),
            humidity_local_pct=float(q_center["humidity_pct"]),
            is_landed=bool(is_landed),
            gustation_contact=gust,
            contact_food_id=contact_food_id,
  )
