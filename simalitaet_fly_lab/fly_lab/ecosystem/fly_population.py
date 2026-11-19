# -*- coding: utf-8 -*-
"""
Schritt 2: Autonome Fruchtfliegen-Population (Drosophila melanogaster)
auf Basis gebündelter realer FlyWire-v783-Subnetzwerke (W_eco @ R_batch).

Eigenschaften:
- Jede lebende Fliege durchläuft pro 25-ms-Ökosystem-Tick echte LIF-Propagation
  auf dem direkt aus Connectivity_783.parquet extrahierten Teilgraphen W_eco.
- Wahrnehmung: Bilaterale Antennen-VOC-Gradienten zu Substraten, Thermikaufwinde,
  Schutzdichte (Laubkrone / Seestraße-43-Terrassenportal) sowie optische Winkel-
  expansionsrate theta_dot herannahender Vögel auf LC4/LPLC2 -> DNp01 (Giant Fiber).
- Lebenszyklus: Nahrungssuche, Fressen (Substratverbrauch & Energiegewinn),
  Fluchtmanöver (verbrennt Energie), Aushungern & Reproduktion bei Überschuss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import sparse

from ..connectome import FlyWireConnectome
from .ecosystem_world import EcosystemSubstrate, Seestrasse43EcosystemWorld


@dataclass
class FlyEcosystemSubcircuit:
    """Kompakter induzierter FlyWire-v783-Teilgraph für schnelle Populations-MatMul."""
    n_neurons: int
    n_edges: int
    w_eco: sparse.csr_matrix
    pools: Dict[str, Dict[str, np.ndarray]]


def build_ecosystem_flywire_subcircuit(conn: FlyWireConnectome) -> FlyEcosystemSubcircuit:
    """Extrahiert reale FlyWire-v783-Kanten für Sensorik, Looming (LC4/LPLC2) & DNs."""
    caps = {
        "vision_spectral": 120,
        "jo_mechano": 100,
        "kc": 160,
        "lhln": 120,
    }
    chosen: set[int] = set()
    for pname, sides in conn.pools.items():
        if pname in ("orn_ester", "orn_geosmin", "pn_ester", "pn_geosmin", "looming",
                     "dan_reward", "dan_punish", "mbon_gaba_glut", "mbon_ach",
                     "dn_steer", "dn_forward", "dn_backward", "dn_jump", "motor_feeding"):
            chosen.update(sides["all"])
        elif pname in caps:
            half = caps[pname] // 2
            chosen.update(sides["left"][:half])
            chosen.update(sides["right"][:half])

    full_idx = np.asarray(sorted(chosen), dtype=np.int32)
    g2l = {int(g): i for i, g in enumerate(full_idx)}
    w_eco = conn.w_full[full_idx, :][:, full_idx].tocsr()

    pools: Dict[str, Dict[str, np.ndarray]] = {}
    for pname, sides in conn.pools.items():
        pools[pname] = {}
        for s in ("left", "right", "all"):
            pools[pname][s] = np.asarray([g2l[g] for g in sides[s] if g in g2l], dtype=np.int32)

    return FlyEcosystemSubcircuit(
        n_neurons=int(w_eco.shape[0]),
        n_edges=int(w_eco.nnz),
        w_eco=w_eco,
        pools=pools,
    )


@dataclass
class FlyPerspectiveSample:
    sim_time_s: float
    fly_id: int
    fly_pos: Tuple[float, float, float]
    fly_yaw_rad: float
    fly_state: str
    energy_mj: float
    visible_birds: List[Dict[str, object]]  # az_deg, el_deg, dist_m, angular_diam_deg, theta_dot_rad_s, species
    nearest_food_az_deg: float
    nearest_food_dist_m: float
    cover_density: float
    neural_orn_ester: float
    neural_lc4_looming: float
    neural_dnp01_escape: float
    neural_dna02_steer_diff: float


class FlyPopulationEngine:
    """Verwaltet die gesamte autonome Fliegen-Population (max_slots biologische Individuen)."""

    V_REST: float = -52.0
    V_THRESH: float = -45.0

    def __init__(
        self,
        sub: FlyEcosystemSubcircuit,
        max_slots: int = 72,
        seed: int = 1001,
        looming_gain: float = 1.0,
    ) -> None:
        self.sub = sub
        self.max_slots = int(max_slots)
        self.rng = np.random.default_rng(seed)
        self.looming_gain = float(looming_gain)

        # Individuen-Zustandsarrays (vektorisiert über slots 0 .. max_slots-1)
        self.active = np.zeros(self.max_slots, dtype=bool)
        self.fly_ids = np.zeros(self.max_slots, dtype=np.int32)
        self.pos = np.zeros((self.max_slots, 3), dtype=np.float32)
        self.vel = np.zeros((self.max_slots, 3), dtype=np.float32)
        self.yaw = np.zeros(self.max_slots, dtype=np.float32)
        self.energy_mj = np.zeros(self.max_slots, dtype=np.float32)
        self.age_s = np.zeros(self.max_slots, dtype=np.float32)
        self.escape_timer_s = np.zeros(self.max_slots, dtype=np.float32)
        self.feed_cooldown_s = np.zeros(self.max_slots, dtype=np.float32)
        self.repro_cooldown_s = np.zeros(self.max_slots, dtype=np.float32)
        self.escape_vec = np.zeros((self.max_slots, 3), dtype=np.float32)
        self.state_label: List[str] = ["INACTIVE"] * self.max_slots
        self.total_escapes = np.zeros(self.max_slots, dtype=np.int32)
        self.total_feeding_s = np.zeros(self.max_slots, dtype=np.float32)
        self.last_orn_ester = np.zeros(self.max_slots, dtype=np.float32)
        self.last_lc4 = np.zeros(self.max_slots, dtype=np.float32)
        self.last_dnp01 = np.zeros(self.max_slots, dtype=np.float32)

        # Echtzeit-LIF-Zustandsmatrix (N_neurons, max_slots) für gebündelte FlyWire-Propagation
        self.v_mv = np.full((sub.n_neurons, self.max_slots), self.V_REST, dtype=np.float32)
        self.r_rate = np.zeros((sub.n_neurons, self.max_slots), dtype=np.float32)

        # Populations-Statistiken
        self._next_fly_id: int = 1
        self.total_spawned: int = 0
        self.total_births: int = 0
        self.total_captured: int = 0
        self.total_starved: int = 0
        self.captures_by_species: Dict[str, int] = {}
        self.last_looming_alerts: int = 0
        self.total_flywire_spikes: int = 0
        self.perspective_history: List[FlyPerspectiveSample] = []

    def seed_initial_population(self, world: Seestrasse43EcosystemWorld, n_flies: int = 32) -> None:
        self.active.fill(False)
        self.v_mv.fill(self.V_REST)
        self.r_rate.fill(0.0)
        self._next_fly_id = 1
        self.total_spawned = 0
        self.total_births = 0
        self.total_captured = 0
        self.total_starved = 0
        self.captures_by_species.clear()
        self.perspective_history.clear()

        # Fliegen realistisch über alle Substrate (Terrasse, Kompost, Apfel-/Pflaumenkrone, Hecke, Küche) verteilen
        for i in range(min(n_flies, self.max_slots)):
            sub_s = world.substrates[i % len(world.substrates)]
            jitter = self.rng.normal(0.0, [0.95, 0.95, 0.45]).astype(np.float32)
            p = np.asarray(sub_s.pos, dtype=np.float32) + jitter
            if sub_s.zone == "INDOOR_REFUGE":
                p[0] = np.clip(p[0], 1.5, 9.5)
                p[1] = np.clip(p[1], 1.0, 5.5)
                p[2] = np.clip(p[2], 0.4, 2.1)
            else:
                p[2] = max(0.35, float(p[2]))
                p = world.clamp_or_slide_fly(np.asarray(sub_s.pos, dtype=np.float32), p)
            e0 = float(self.rng.uniform(7.5, 11.8))
            self._spawn_at(p, e0, initial=True)

    def _spawn_at(self, pos_xyz: np.ndarray, energy_mj: float, initial: bool = False) -> Optional[int]:
        free = np.flatnonzero(~self.active)
        if len(free) == 0:
            return None
        slot = int(free[0])
        self.active[slot] = True
        self.fly_ids[slot] = self._next_fly_id
        self._next_fly_id += 1
        self.pos[slot] = pos_xyz.astype(np.float32)
        self.vel[slot] = self.rng.normal(0.0, 0.15, size=3).astype(np.float32)
        self.yaw[slot] = float(self.rng.uniform(0.0, 2.0 * math.pi))
        self.energy_mj[slot] = energy_mj
        self.age_s[slot] = 0.0
        self.escape_timer_s[slot] = 0.0
        self.feed_cooldown_s[slot] = 0.0
        self.repro_cooldown_s[slot] = 18.0 if initial else 25.0
        self.state_label[slot] = "FORAGING"
        self.total_escapes[slot] = 0
        self.total_feeding_s[slot] = 0.0
        self.last_orn_ester[slot] = 0.0
        self.last_lc4[slot] = 0.0
        self.last_dnp01[slot] = 0.0
        self.v_mv[:, slot] = self.V_REST
        self.r_rate[:, slot] = 0.0
        self.total_spawned += 1
        if not initial:
            self.total_births += 1
        return slot

    def kill_fly(self, slot: int, cause: str, species_id: Optional[str] = None) -> int:
        if not self.active[slot]:
            return 0
        fid = int(self.fly_ids[slot])
        self.active[slot] = False
        self.state_label[slot] = cause
        if species_id is not None:
            self.total_captured += 1
            self.captures_by_species[species_id] = self.captures_by_species.get(species_id, 0) + 1
        else:
            self.total_starved += 1
        return fid

    def alive_slots(self) -> np.ndarray:
        return np.flatnonzero(self.active)

    def count_alive(self) -> int:
        return int(self.active.sum())

    def zone_distribution(self, world: Seestrasse43EcosystemWorld) -> Dict[str, int]:
        slots = self.alive_slots()
        indoor = 0
        canopy = 0
        open_air = 0
        if len(slots):
            dens = world.max_canopy_density_vec(self.pos[slots])
            for idx, s in enumerate(slots):
                if world.is_inside_house(self.pos[s]):
                    indoor += 1
                elif dens[idx] >= 0.25:
                    canopy += 1
                else:
                    open_air += 1
        return {"total": len(slots), "indoor": indoor, "canopy": canopy, "open_air": open_air}

    def step(
        self,
        world: Seestrasse43EcosystemWorld,
        bird_states: List[Dict[str, object]],
        dt_s: float = 0.025,
        record_perspective_fly_idx: Optional[int] = None,
        los_matrix: Optional[np.ndarray] = None,
        fly_canopy_vec: Optional[np.ndarray] = None,
    ) -> None:
        """
        Führt alle lebenden Fliegen einen Schritt (25 ms) inkl. gebündelter
        FlyWire-v783-LIF-Propagation, Nahrungssuche, Looming-Flucht & Fortpflanzung fort.
        """
        slots = self.alive_slots()
        if len(slots) == 0:
            return

        # 1. Eingangsströme pro Fliegenslot (nur direkte Sensorik-Zeilen, spart (N,k)-Allokation)
        k = len(slots)
        p_pools = self.sub.pools

        fp_all = self.pos[slots]
        vel_all = self.vel[slots]
        yaw_all = self.yaw[slots]
        cos_y = np.cos(yaw_all)
        sin_y = np.sin(yaw_all)
        fwd_all = np.stack([cos_y, sin_y, np.zeros(k, dtype=np.float32)], axis=-1)
        left_all = np.stack([-sin_y, cos_y, np.zeros(k, dtype=np.float32)], axis=-1)
        hunger_all = np.clip(1.4 - 0.05 * self.energy_mj[slots], 0.4, 1.8).astype(np.float32)

        est_drive_l = np.zeros(k, dtype=np.float32)
        est_drive_r = np.zeros(k, dtype=np.float32)
        loom_l = np.zeros(k, dtype=np.float32)
        loom_r = np.zeros(k, dtype=np.float32)
        target_food_dirs = fwd_all.copy()
        nearest_food_dists = np.full(k, 99.0, dtype=np.float32)
        nearest_food_obj: List[Optional[EcosystemSubstrate]] = [None] * k
        escape_best_dir = np.zeros((k, 3), dtype=np.float32)
        vis_birds_for_rec: List[Dict[str, object]] = []

        # Vektorisierte Substrat-Duftgradienten (k x S)
        active_subs = [s for s in world.substrates if s.nutrients >= 1.0]
        if active_subs:
            sub_pos = np.array([s.pos for s in active_subs], dtype=np.float32)
            sub_voc = np.array([s.voc_strength for s in active_subs], dtype=np.float32)
            sub_norm = np.array(
                [s.voc_strength * (s.nutrients / s.max_nutrients) for s in active_subs],
                dtype=np.float32,
            )
            p_l_all = fp_all + np.float32(0.06) * left_all
            p_r_all = fp_all - np.float32(0.06) * left_all
            d_vec = sub_pos[None, :, :] - fp_all[:, None, :]
            d_m = np.linalg.norm(d_vec, axis=-1) + np.float32(1e-4)
            plume = sub_norm[None, :] * np.exp(-(d_m * d_m) / np.float32(22.0))
            dl = np.linalg.norm(sub_pos[None, :, :] - p_l_all[:, None, :], axis=-1) + np.float32(1e-4)
            dr = np.linalg.norm(sub_pos[None, :, :] - p_r_all[:, None, :], axis=-1) + np.float32(1e-4)
            c_l_sum = np.sum(sub_voc[None, :] * np.exp(-(dl * dl) / np.float32(14.0)), axis=1)
            c_r_sum = np.sum(sub_voc[None, :] * np.exp(-(dr * dr) / np.float32(14.0)), axis=1)

            score = plume * hunger_all[:, None]
            best_sub_idx = np.argmax(score, axis=1)
            rows_k = np.arange(k)
            nearest_food_dists = d_m[rows_k, best_sub_idx]
            target_food_dirs = d_vec[rows_k, best_sub_idx] / nearest_food_dists[:, None]
            nearest_food_obj = [active_subs[int(bi)] for bi in best_sub_idx]
            est_drive_l = np.minimum(14.0, 4.5 * np.log1p(12.0 * c_l_sum) * hunger_all).astype(np.float32)
            est_drive_r = np.minimum(14.0, 4.5 * np.log1p(12.0 * c_r_sum) * hunger_all).astype(np.float32)

        # 2. Vektorisierte 3D-Vogel-Annäherung & Optische Expansion (LC4/LPLC2 -> DNp01)!
        if len(bird_states) > 0:
            b_pos = np.array([b["pos"] for b in bird_states], dtype=np.float32)
            b_vel = np.array([b["vel"] for b in bird_states], dtype=np.float32)
            r_eff = np.array([0.5 * float(b["wingspan_m"]) for b in bird_states], dtype=np.float32)
            if los_matrix is None:
                los_mat = world.compute_los_matrix(fp_all, b_pos)
            else:
                los_mat = los_matrix

            diff_b = b_pos[None, :, :] - fp_all[:, None, :]
            dist_b = np.linalg.norm(diff_b, axis=-1)
            valid_b = (dist_b <= 9.5) & (dist_b >= 0.02) & (los_mat > 0.10)
            u_fb = diff_b / np.maximum(dist_b[..., None], np.float32(1e-6))
            v_rel = b_vel[None, :, :] - vel_all[:, None, :]
            v_app = np.maximum(0.0, -np.sum(v_rel * u_fb, axis=-1))
            theta_rad = np.arctan2(r_eff[None, :], np.maximum(dist_b, np.float32(1e-4)))
            theta_dot = (2.0 * r_eff[None, :] * v_app) / (dist_b * dist_b + (r_eff * r_eff)[None, :] + 1e-6)
            loom_drive = np.where(
                valid_b,
                (theta_dot * 2.2 + 2.8 * np.maximum(0.0, theta_rad - 0.045) * (1.0 + 0.4 * v_app))
                * los_mat
                * np.float32(self.looming_gain),
                np.float32(0.0),
            )
            az_rel = np.arctan2(
                np.sum(u_fb * left_all[:, None, :], axis=-1),
                np.sum(u_fb * fwd_all[:, None, :], axis=-1) + np.float32(1e-6),
            )
            is_left = az_rel >= 0.0
            loom_l = np.max(np.where(valid_b, np.where(is_left, loom_drive * 1.15, loom_drive * 0.45), 0.0), axis=1).astype(np.float32)
            loom_r = np.max(np.where(valid_b, np.where(is_left, loom_drive * 0.45, loom_drive * 1.15), 0.0), axis=1).astype(np.float32)

            best_b = np.argmax(loom_drive, axis=1)
            rows_k = np.arange(k)
            best_score = loom_drive[rows_k, best_b]
            has_threat = best_score > 0.0
            if np.any(has_threat):
                u_best = u_fb[rows_k, best_b]
                z_axis = np.array([0.0, 0.0, 1.0], dtype=np.float32)
                perp = np.cross(u_best, z_axis)
                perp_norm = np.linalg.norm(perp, axis=-1)
                perp = np.where(
                    (perp_norm < 0.1)[:, None],
                    left_all,
                    perp / np.maximum(perp_norm[:, None], np.float32(1e-6)),
                )
                perp = np.where((az_rel[rows_k, best_b] > 0.0)[:, None], -perp, perp)
                ev = np.float32(0.72) * perp - np.float32(0.48) * u_best + np.array([0.0, 0.0, -0.35], dtype=np.float32)
                ev_norm = np.linalg.norm(ev, axis=-1)
                ev = ev / np.maximum(ev_norm[:, None], np.float32(1e-5))
                escape_best_dir[has_threat] = ev[has_threat]

            if record_perspective_fly_idx is not None:
                rec_matches = np.where(self.fly_ids[slots] == int(record_perspective_fly_idx))[0]
                if len(rec_matches) > 0:
                    ri = int(rec_matches[0])
                    for bi, b in enumerate(bird_states):
                        if valid_b[ri, bi]:
                            el_rad = math.asin(float(np.clip(u_fb[ri, bi, 2], -1.0, 1.0)))
                            vis_birds_for_rec.append({
                                "bird_id": b["bird_id"],
                                "species": b["species_id"],
                                "az_deg": round(math.degrees(float(az_rel[ri, bi])), 1),
                                "el_deg": round(math.degrees(el_rad), 1),
                                "dist_m": round(float(dist_b[ri, bi]), 2),
                                "angular_diam_deg": round(math.degrees(2.0 * float(theta_rad[ri, bi])), 2),
                                "theta_dot_rad_s": round(float(theta_dot[ri, bi]), 3),
                                "los": round(float(los_mat[ri, bi]), 2),
                            })

        # Ströme nur auf die realen sensorischen Eingangsneuronen bündeln
        idx_orn_l = p_pools["orn_ester"]["left"]
        idx_orn_r = p_pools["orn_ester"]["right"]
        idx_loom_l = p_pools["looming"]["left"]
        idx_loom_r = p_pools["looming"]["right"]
        idx_vis = p_pools["vision_spectral"]["all"]
        cur_loom_l = np.minimum(np.float32(18.0), np.float32(4.5) * loom_l)[None, :]
        cur_loom_r = np.minimum(np.float32(18.0), np.float32(4.5) * loom_r)[None, :]
        cur_est_l = est_drive_l[None, :]
        cur_est_r = est_drive_r[None, :]
        cur_vis = np.float32(2.5 * world.daylight_uv_factor)

        # 3. Gebündelte echte FlyWire-v783-LIF-Dynamik (2 x 12,5 ms Substeps, In-Place ohne Heap-Kopien)
        v_s = np.ascontiguousarray(self.v_mv[:, slots])
        r_s = np.ascontiguousarray(self.r_rate[:, slots])
        dt_sub = np.float32(dt_s / 2.0)
        decay_m = np.float32(math.exp(-float(dt_sub) / 0.020))
        one_minus_decay = np.float32(1.0) - decay_m
        v_rest = np.float32(self.V_REST)
        v_thresh = np.float32(self.V_THRESH)
        inv_span = np.float32(1.0 / 11.0)
        w = self.sub.w_eco
        spikes_this_step = 0

        for _ in range(2):
            i_buf = w @ r_s
            i_buf *= np.float32(0.058)
            i_buf[idx_orn_l, :] += cur_est_l
            i_buf[idx_orn_r, :] += cur_est_r
            i_buf[idx_loom_l, :] += cur_loom_l
            i_buf[idx_loom_r, :] += cur_loom_r
            i_buf[idx_vis, :] += cur_vis
            i_buf += v_rest
            i_buf *= one_minus_decay
            v_s *= decay_m
            v_s += i_buf
            np.clip(v_s, np.float32(-72.0), np.float32(-34.0), out=v_s)
            spiked = v_s >= v_thresh
            n_sp = int(spiked.sum())
            spikes_this_step += n_sp
            if n_sp > 0:
                v_s[spiked] = v_rest
            np.subtract(v_s, v_rest, out=r_s)
            r_s *= inv_span
            if n_sp > 0:
                r_s[spiked] += np.float32(0.32)
            np.clip(r_s, np.float32(0.0), np.float32(1.0), out=r_s)

        self.v_mv[:, slots] = v_s
        self.r_rate[:, slots] = r_s
        self.total_flywire_spikes += spikes_this_step

        # 4. Absteigende Auslese (LC4 + DNp01 Escape & DNa02 Steer & Motor Feeding) — vektorisiert
        lc4_mean = 0.5 * (
            r_s[p_pools["looming"]["left"], :].mean(axis=0) + r_s[p_pools["looming"]["right"], :].mean(axis=0)
        )
        dnp01_mean = r_s[p_pools["dn_jump"]["all"], :].mean(axis=0) if len(p_pools["dn_jump"]["all"]) else np.zeros(k, dtype=np.float32)
        steer_diff = (
            r_s[p_pools["dn_steer"]["left"], :].mean(axis=0) - r_s[p_pools["dn_steer"]["right"], :].mean(axis=0)
        )
        orn_mean = r_s[p_pools["orn_ester"]["all"], :].mean(axis=0)
        self.last_orn_ester[slots] = orn_mean
        self.last_lc4[slots] = lc4_mean
        self.last_dnp01[slots] = dnp01_mean

        dt_f = np.float32(dt_s)
        self.age_s[slots] += dt_f
        self.repro_cooldown_s[slots] = np.maximum(np.float32(0.0), self.repro_cooldown_s[slots] - dt_f)
        esc_timer = np.maximum(np.float32(0.0), self.escape_timer_s[slots] - dt_f)

        esc_dir_norm = np.linalg.norm(escape_best_dir, axis=-1)
        if self.looming_gain > 0.0:
            escape_trigger = (
                ((dnp01_mean > 0.22) | (lc4_mean > 0.34) | ((loom_l + loom_r) > 1.25))
                & (esc_dir_norm > 0.1)
            )
        else:
            escape_trigger = np.zeros(k, dtype=bool)

        looming_alerts = int(escape_trigger.sum())
        if looming_alerts > 0:
            fresh_esc = escape_trigger & (esc_timer <= 0.02)
            self.total_escapes[slots[fresh_esc]] += 1
            esc_timer[escape_trigger] = np.float32(0.55)
            self.escape_vec[slots[escape_trigger]] = escape_best_dir[escape_trigger]
        self.escape_timer_s[slots] = esc_timer

        wind_all = world.wind_at_vec(fp_all)
        in_house_all = world._is_inside_house_vec(fp_all)

        is_escaping = esc_timer > 0.0
        has_food = np.array([obj is not None for obj in nearest_food_obj], dtype=bool)
        is_feeding = (~is_escaping) & has_food & (nearest_food_dists <= 0.65) & (self.energy_mj[slots] < 15.5)
        is_foraging = (~is_escaping) & (~is_feeding)

        desired_vel = np.empty((k, 3), dtype=np.float32)
        met_cost = np.empty(k, dtype=np.float32)
        yaw_cur = self.yaw[slots].copy()
        energy_cur = self.energy_mj[slots].copy()

        # Zustand A: ESCAPING
        if np.any(is_escaping):
            desired_vel[is_escaping] = (
                self.escape_vec[slots[is_escaping]] * np.float32(1.55)
                + np.float32(0.35) * wind_all[is_escaping]
            )
            met_cost[is_escaping] = np.float32(0.048 * dt_s)

        # Zustand B: FEEDING
        if np.any(is_feeding):
            for idx_f in np.flatnonzero(is_feeding):
                sub_s = nearest_food_obj[idx_f]
                taken = sub_s.feed_and_consume(0.45 * dt_s) if sub_s is not None else 0.0
                energy_cur[idx_f] = min(18.0, float(energy_cur[idx_f]) + taken * 1.15)
            self.total_feeding_s[slots[is_feeding]] += dt_f
            yaw_f = yaw_cur[is_feeding] + np.float32(1.8 * dt_s)
            yaw_cur[is_feeding] = yaw_f
            circ_f = np.stack([np.cos(yaw_f), np.sin(yaw_f), np.zeros(len(yaw_f), dtype=np.float32)], axis=-1)
            desired_vel[is_feeding] = (
                target_food_dirs[is_feeding] * np.float32(0.22)
                + circ_f * np.float32(0.15)
            )
            met_cost[is_feeding] = np.float32(0.008 * dt_s)

        # Zustand C: FORAGING / SHELTERED
        if np.any(is_foraging):
            n_for = int(is_foraging.sum())
            noise_turn = self.rng.normal(0.0, 0.9, size=n_for).astype(np.float32)
            turn = (
                np.float32(2.5) * steer_diff[is_foraging]
                + np.float32(0.35) * (est_drive_l[is_foraging] - est_drive_r[is_foraging])
                + noise_turn
            )
            yaw_c = np.mod(yaw_cur[is_foraging] + turn * dt_f, np.float32(2.0 * math.pi))
            yaw_cur[is_foraging] = yaw_c
            head_c = np.stack([np.cos(yaw_c), np.sin(yaw_c), np.full(n_for, 0.10, dtype=np.float32)], axis=-1)
            base_dir = np.float32(0.65) * target_food_dirs[is_foraging] + np.float32(0.35) * head_c
            bd_norm = np.linalg.norm(base_dir, axis=-1, keepdims=True)
            base_dir = np.where(bd_norm > 1e-5, base_dir / np.maximum(bd_norm, np.float32(1e-5)), base_dir)
            desired_vel[is_foraging] = base_dir * np.float32(0.58) + wind_all[is_foraging] * np.float32(0.75)
            met_cost[is_foraging] = np.float32(0.024 * dt_s)

        # Wetter- & Tageslichtkopplung (nur aktiv bei Regen oder Dämmerung -> bit-identisch bei Sonne/trocken)
        rain_cur = float(getattr(world, "rain_mm_h", 0.0))
        uv_cur = float(getattr(world, "daylight_uv_factor", 1.0))
        if rain_cur > 0.05 or uv_cur < 0.999:
            out_mask = ~in_house_all
            if np.any(out_mask):
                out_for = out_mask & is_foraging
                if rain_cur > 0.05 and np.any(out_for):
                    refuges = np.array(
                        [c.center for c in world.canopies] + [list(world.HOUSE_FLY_PORTAL_CENTER)],
                        dtype=np.float32,
                    )
                    fp_of = fp_all[out_for]
                    d_ref = refuges[None, :, :] - fp_of[:, None, :]
                    dist_ref = np.linalg.norm(d_ref, axis=-1) + np.float32(1e-4)
                    best_r = np.argmin(dist_ref, axis=1)
                    u_ref = d_ref[np.arange(len(fp_of)), best_r] / dist_ref[np.arange(len(fp_of)), best_r, None]
                    pull = np.float32(min(0.55, 0.045 * rain_cur))
                    desired_vel[out_for] = (1.0 - pull) * desired_vel[out_for] + pull * (u_ref * np.float32(0.72))
                    desired_vel[out_for, 2] -= np.float32(0.045 * min(12.0, rain_cur))
                elif uv_cur < 0.999 and np.any(out_for):
                    desired_vel[out_for] *= np.float32(max(0.45, 0.55 + 0.45 * uv_cur))

        # Trägheitsgeglättete Bewegung & Hindernisprüfung (vektorisiert)
        new_vel = (np.float32(0.65) * vel_all + np.float32(0.35) * desired_vel).astype(np.float32)
        next_pos = fp_all + new_vel * dt_f
        clamped_all = world.clamp_or_slide_fly_vec(fp_all, next_pos)

        moving_xy = (np.abs(new_vel[:, 0]) + np.abs(new_vel[:, 1])) > 0.05
        if np.any(moving_xy):
            yaw_cur[moving_xy] = np.arctan2(new_vel[moving_xy, 1], new_vel[moving_xy, 0]).astype(np.float32)

        energy_cur = energy_cur - met_cost
        self.vel[slots] = new_vel
        self.pos[slots] = clamped_all
        self.yaw[slots] = yaw_cur
        self.energy_mj[slots] = energy_cur

        # Zustandslabels nur noch kompakt zuweisen
        for i_k, slot in enumerate(slots):
            if is_escaping[i_k]:
                self.state_label[slot] = "ESCAPING"
            elif is_feeding[i_k]:
                self.state_label[slot] = "FEEDING"
            else:
                self.state_label[slot] = "SHELTERED" if in_house_all[i_k] else "FORAGING"

        # Verhungern & Reproduktion
        new_borns: List[Tuple[np.ndarray, float]] = []
        starved_mask = energy_cur <= 0.0
        if np.any(starved_mask):
            for idx_s in np.flatnonzero(starved_mask):
                self.kill_fly(int(slots[idx_s]), "STARVED", species_id=None)

        repro_mask = (
            (~starved_mask)
            & is_feeding
            & (energy_cur >= 13.8)
            & (self.repro_cooldown_s[slots] <= 0.0)
        )
        if np.any(repro_mask):
            alive_now = self.count_alive()
            for idx_r in np.flatnonzero(repro_mask):
                if (alive_now + len(new_borns)) >= (self.max_slots - 2):
                    break
                slot = int(slots[idx_r])
                self.energy_mj[slot] -= 4.5
                self.repro_cooldown_s[slot] = 30.0
                off_p = world.clamp_or_slide_fly(
                    clamped_all[idx_r],
                    clamped_all[idx_r] + self.rng.normal(0.0, 0.25, size=3).astype(np.float32),
                )
                new_borns.append((off_p, 6.5))

        if record_perspective_fly_idx is not None:
            rec_matches = np.where(self.fly_ids[slots] == int(record_perspective_fly_idx))[0]
            if len(rec_matches) > 0:
                ri = int(rec_matches[0])
                slot = int(slots[ri])
                if self.active[slot]:
                    d_to_f = target_food_dirs[ri]
                    yw = float(self.yaw[slot])
                    cl = clamped_all[ri]
                    food_az = math.atan2(
                        float(d_to_f[0] * (-math.sin(yw)) + d_to_f[1] * math.cos(yw)),
                        float(d_to_f[0] * math.cos(yw) + d_to_f[1] * math.sin(yw)) + 1e-6,
                    )
                    self.perspective_history.append(
                        FlyPerspectiveSample(
                            sim_time_s=round(world.sim_time_s, 3),
                            fly_id=int(self.fly_ids[slot]),
                            fly_pos=(round(float(cl[0]), 3), round(float(cl[1]), 3), round(float(cl[2]), 3)),
                            fly_yaw_rad=round(yw, 3),
                            fly_state=self.state_label[slot],
                            energy_mj=round(float(self.energy_mj[slot]), 3),
                            visible_birds=vis_birds_for_rec,
                            nearest_food_az_deg=round(math.degrees(food_az), 1),
                            nearest_food_dist_m=round(float(nearest_food_dists[ri]), 2),
                            cover_density=round(float(world.canopy_density_at(cl)), 2),
                            neural_orn_ester=round(float(orn_mean[ri]), 4),
                            neural_lc4_looming=round(float(lc4_mean[ri]), 4),
                            neural_dnp01_escape=round(float(dnp01_mean[ri]), 4),
                            neural_dna02_steer_diff=round(float(steer_diff[ri]), 4),
                        )
                    )

        self.last_looming_alerts = looming_alerts
        for op, oe in new_borns:
            self._spawn_at(op, oe, initial=False)
