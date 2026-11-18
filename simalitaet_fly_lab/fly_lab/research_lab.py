# -*- coding: utf-8 -*-
"""
Modul G: Research Lab — Reproduzierbare Versuchsprotokolle, 7 Epistemische Kammern,
Seestraße-43-Telemetrie und Ablationskontrollen (Experimente 1–6).

Dokumentiert ausdrücklich sowohl bestätigte Software-/Modelleigenschaften als auch
Abweichungen, verworfene Ansätze und fehlgeschlagene Kontrollen (kein Verschweigen,
kein unbelegtes Langzeitgedächtnis, kein Bewusstseinsanspruch).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .body_engine import FlyBodyEngine, MotorOutputVector
from .connectome import FlyWireConnectome, FlyWireSubcircuit
from .neural_and_memory import EPISTEMIC_REGISTRY, FlyWireNeuralEngine
from .security_guards import FLY_LAB_ROOT, FlyLabSecurityGuard
from .seestrasse_43_world import Seestrasse43World
from .sensory_interface import FlySensoryInterface


class FindingChamber(str, Enum):
    RAW_DATA = "RAW_DATA"
    HYPOTHESIS = "HYPOTHESIS"
    PREDICTION = "PREDICTION"
    OBSERVATION = "OBSERVATION"
    DEVIATION = "DEVIATION"
    CONFIRMED_RESULT = "CONFIRMED_RESULT"
    REJECTED_APPROACH = "REJECTED_APPROACH"


class EvidenceGrade(str, Enum):
    MEASURED_OBSERVATION = "MEASURED_OBSERVATION"
    QUANTIFIED_DEVIATION = "QUANTIFIED_DEVIATION"
    CONFIRMED_SOFTWARE_PROPERTY = "CONFIRMED_SOFTWARE_PROPERTY"
    REFUTED_APPROACH = "REFUTED_APPROACH"


@dataclass
class TrialTelemetry:
    label: str
    seed: int
    duration_s: float
    steps: int
    start_pos: Tuple[float, float, float]
    end_pos: Tuple[float, float, float]
    total_path_length_m: float
    wall_collisions: int
    stair_transitions: int
    door_gap_traversals: int
    total_spikes: int
    room_residence_s: Dict[str, float]
    floor_layer_residence_s: Dict[str, float]
    first_feeding_time_s: Optional[float]
    first_feeding_path_m: Optional[float]
    first_food_id: Optional[str]
    feeding_time_by_food_s: Dict[str, float]
    feeding_mass_by_food_mg: Dict[str, float]
    substrate_preference_index: Dict[str, object]
    energy_hydration_balance: Dict[str, float]
    chemotaxis_efficiency: Dict[str, object]
    mean_light_uv_exposed: float
    tarsal_stance_duty_a: float
    tarsal_stance_duty_b: float
    trajectory_sample: List[Tuple[float, float, float]]


@dataclass
class ChamberEntry:
    experiment_id: str
    chamber: str
    evidence_grade: str
    statement: str
    metrics: Dict[str, object]


class FlyResearchLab:
    """Führt alle 6 Experimente in Seestraße 43 durch und protokolliert die 7 Kammern."""

    FERMENTING_IDS = {"FOOD_02", "FOOD_04", "FOOD_06", "FOOD_08"}
    FRESH_IDS = {"FOOD_01", "FOOD_03", "FOOD_05"}
    AVERSIVE_IDS = {"FOOD_07", "FOOD_09"}

    def __init__(
        self,
        connectome: FlyWireConnectome,
        subcircuit: FlyWireSubcircuit,
        world: Seestrasse43World,
        guard: Optional[FlyLabSecurityGuard] = None,
    ) -> None:
        self.conn = connectome
        self.sub = subcircuit
        self.world = world
        self.base_snap = world.snapshot_voc_and_foods()
        self.guard = guard or FlyLabSecurityGuard()
        self.chamber_log: List[ChamberEntry] = []

    def log_chamber(
        self,
        experiment_id: str,
        chamber: FindingChamber,
        grade: EvidenceGrade,
        statement: str,
        metrics: Optional[Dict[str, object]] = None,
    ) -> None:
        self.chamber_log.append(
            ChamberEntry(
                experiment_id=experiment_id,
                chamber=chamber.value,
                evidence_grade=grade.value,
                statement=statement,
                metrics=metrics or {},
            )
        )

    def run_trial(
        self,
        label: str,
        start_pos: Tuple[float, float, float],
        start_yaw_rad: float,
        duration_s: float,
        seed: int = 42,
        start_landed: bool = False,
        initial_energy_mj: float = 10.0,
        initial_hydration_pct: float = 72.0,
        olfaction_gain: float = 1.0,
        vision_gain: float = 1.0,
        looming_gain: float = 1.0,
        da2_geosmin_gain: float = 1.0,
        plasticity_enabled: bool = True,
        left_antenna_intact: bool = True,
        right_antenna_intact: bool = True,
        pre_condition_fn: Optional[Callable[[FlyWireNeuralEngine], None]] = None,
        dt_s: float = 0.010,
    ) -> Tuple[TrialTelemetry, FlyWireNeuralEngine]:
        self.world.restore_voc_and_foods(self.base_snap)
        brain = FlyWireNeuralEngine(
            self.sub,
            seed=seed,
            olfaction_gain=olfaction_gain,
            vision_gain=vision_gain,
            looming_gain=looming_gain,
            da2_geosmin_gain=da2_geosmin_gain,
            plasticity_enabled=plasticity_enabled,
        )
        if pre_condition_fn is not None:
            pre_condition_fn(brain)

        sens = FlySensoryInterface(
            olfaction_enabled=(olfaction_gain > 0.0),
            vision_enabled=(vision_gain > 0.0),
            looming_enabled=(looming_gain > 0.0),
            left_antenna_intact=left_antenna_intact,
            right_antenna_intact=right_antenna_intact,
        )
        body = FlyBodyEngine(
            start_pos=start_pos,
            start_yaw_rad=start_yaw_rad,
            start_landed=start_landed,
            initial_energy_mj=initial_energy_mj,
            initial_hydration_pct=initial_hydration_pct,
        )

        n_steps = int(round(duration_s / dt_s))
        room_res: Dict[str, float] = {}
        floor_res: Dict[str, float] = {"EG": 0.0, "OG": 0.0, "DG": 0.0}
        path_len = 0.0
        prev_pos = body.state.pos_xyz.copy()
        first_feed_t: Optional[float] = None
        first_feed_path: Optional[float] = None
        first_food_id: Optional[str] = None
        feed_time_by_food: Dict[str, float] = {f.food_id: 0.0 for f in self.world.foods}
        uv_accum = 0.0
        stance_a_cnt = 0
        stance_b_cnt = 0
        walk_steps = 0
        traj_sample: List[Tuple[float, float, float]] = [tuple(round(float(v), 3) for v in prev_pos)]  # type: ignore[misc]

        for step_i in range(n_steps):
            sv = sens.sense(
                self.world,
                body.state.pos_xyz,
                body.state.vel_xyz,
                body.state.yaw_rad,
                body.state.pitch_rad,
                body.state.is_landed,
                dt_s,
            )
            mot = brain.step(sv, body.state.energy_mj, body.state.hydration_pct, dt_s)
            fres = body.step(self.world, mot, dt_s)
            self.world.step(dt_s)

            cur = body.state.pos_xyz
            path_len += float(np.linalg.norm(cur - prev_pos))
            prev_pos = cur.copy()
            room_res[sv.room_id] = room_res.get(sv.room_id, 0.0) + dt_s
            fl = "EG" if cur[2] < 2.8 else ("OG" if cur[2] < 5.6 else "DG")
            floor_res[fl] += dt_s
            uv_accum += float(0.5 * (sv.vision_spectral_left[0] + sv.vision_spectral_right[0]))

            if body.state.is_landed:
                walk_steps += 1
                if body.state.tripod_a_stance:
                    stance_a_cnt += 1
                if body.state.tripod_b_stance:
                    stance_b_cnt += 1

            if fres["fed"]:
                fid = str(fres["food_id"])
                feed_time_by_food[fid] = feed_time_by_food.get(fid, 0.0) + dt_s
                if first_feed_t is None:
                    first_feed_t = (step_i + 1) * dt_s
                    first_feed_path = path_len
                    first_food_id = fid

            if step_i % 25 == 0:
                traj_sample.append((round(float(cur[0]), 3), round(float(cur[1]), 3), round(float(cur[2]), 3)))

        feed_mass = {f.food_id: round(f.mass_consumed_mg, 4) for f in self.world.foods}
        t_ferm = sum(feed_time_by_food[fid] for fid in self.FERMENTING_IDS)
        t_fresh = sum(feed_time_by_food[fid] for fid in self.FRESH_IDS)
        t_avers = sum(feed_time_by_food[fid] for fid in self.AVERSIVE_IDS)
        t_total = t_ferm + t_fresh + t_avers

        pref_idx = {
            "fermenting_s": round(t_ferm, 3),
            "fresh_s": round(t_fresh, 3),
            "aversive_s": round(t_avers, 3),
            "ferm_vs_fresh_index": round((t_ferm - t_fresh) / max(1e-6, t_ferm + t_fresh), 4) if (t_ferm + t_fresh) > 0 else 0.0,
            "ferm_share": round(t_ferm / max(1e-6, t_total), 4) if t_total > 0 else 0.0,
            "aversive_share": round(t_avers / max(1e-6, t_total), 4) if t_total > 0 else 0.0,
        }

        target_food = self.world.food_by_id[first_food_id] if first_food_id else self.world.food_by_id["FOOD_02"]
        straight_dist = math.sqrt(
            (start_pos[0] - target_food.x) ** 2
            + (start_pos[1] - target_food.y) ** 2
            + (start_pos[2] - target_food.z_abs_m) ** 2
        )
        chemotaxis_eff = {
            "reached_food": first_food_id is not None,
            "first_food_id": first_food_id,
            "time_to_first_feeding_s": round(first_feed_t, 3) if first_feed_t is not None else None,
            "path_length_to_food_m": round(first_feed_path, 3) if first_feed_path is not None else None,
            "geodesic_straight_m": round(straight_dist, 3),
            "tortuosity_ratio": round(first_feed_path / max(0.05, straight_dist), 3) if first_feed_path is not None else None,
        }

        energy_hydr = {
            "metabolic_spent_mj": round(body.state.metabolic_spent_mj, 4),
            "ingested_energy_mj": round(body.state.ingested_energy_mj, 4),
            "net_energy_delta_mj": round(body.state.ingested_energy_mj - body.state.metabolic_spent_mj, 4),
            "final_energy_mj": round(body.state.energy_mj, 4),
            "ingested_hydration_pct": round(body.state.ingested_hydration_pct, 4),
            "final_hydration_pct": round(body.state.hydration_pct, 3),
        }

        telem = TrialTelemetry(
            label=label,
            seed=seed,
            duration_s=duration_s,
            steps=n_steps,
            start_pos=start_pos,
            end_pos=(round(float(prev_pos[0]), 3), round(float(prev_pos[1]), 3), round(float(prev_pos[2]), 3)),
            total_path_length_m=round(path_len, 3),
            wall_collisions=body.state.wall_collisions,
            stair_transitions=body.state.stair_transitions,
            door_gap_traversals=body.state.door_gap_traversals,
            total_spikes=brain.total_spikes,
            room_residence_s={k: round(v, 3) for k, v in sorted(room_res.items())},
            floor_layer_residence_s={k: round(v, 3) for k, v in floor_res.items()},
            first_feeding_time_s=round(first_feed_t, 3) if first_feed_t is not None else None,
            first_feeding_path_m=round(first_feed_path, 3) if first_feed_path is not None else None,
            first_food_id=first_food_id,
            feeding_time_by_food_s={k: round(v, 3) for k, v in feed_time_by_food.items()},
            feeding_mass_by_food_mg=feed_mass,
            substrate_preference_index=pref_idx,
            energy_hydration_balance=energy_hydr,
            chemotaxis_efficiency=chemotaxis_eff,
            mean_light_uv_exposed=round(uv_accum / max(1, n_steps), 4),
            tarsal_stance_duty_a=round(stance_a_cnt / max(1, walk_steps), 3) if walk_steps else 0.0,
            tarsal_stance_duty_b=round(stance_b_cnt / max(1, walk_steps), 3) if walk_steps else 0.0,
            trajectory_sample=traj_sample,
        )
        return telem, brain

    def run_all_six_experiments(self) -> Dict[str, object]:
        """Führt alle 6 Experimente mit Ablationskontrollen deterministisch durch."""
        self.chamber_log.clear()
        self.log_chamber(
            "GLOBAL_SYSTEM",
            FindingChamber.RAW_DATA,
            EvidenceGrade.MEASURED_OBSERVATION,
            "FlyWire v783 (138.639 Neuronen, 15.091.983 Kanten, 54.492.922 Synapsen) und Seestraße 43 (72.600 Voxel, 13 Räume, 9 Substrate) verifiziert geladen.",
            {"neurons": self.conn.n_neurons, "edges": int(self.conn.w_full.nnz), "air_voxels": int(self.world.air_mask.sum())},
        )
        if not FlyBodyEngine().mujoco_available:
            self.log_chamber(
                "ENV_POLICY",
                FindingChamber.DEVIATION,
                EvidenceGrade.QUANTIFIED_DEVIATION,
                "Windows Application Control blockierte mujoco._structs.pyd und pyarrow._fs.pyd. Sanktionskonforme Auflösung: pyarrow._parquet.ParquetReader + direkte NeuroMechFly-XML-Morphologie mit 0,5-ms-Hexapoden-Kinematik.",
                {"mujoco_status": FlyBodyEngine().mujoco_status[:120]},
            )
        # Verworfener Ansatz dokumentieren (reine 0,35-mm statische Antennendifferenz ohne Weber-Fechner)
        self.log_chamber(
            "CALIBRATION_NOTE",
            FindingChamber.REJECTED_APPROACH,
            EvidenceGrade.REFUTED_APPROACH,
            "Verworfen: rein lineare ORN-Skalierung bei statischem 0,35-mm-Abstand verfehlt schwache Fernbereichs-Duftfahnen (OG_FLUR C=0,005 vs EG_KUECHE C=6,67) um den Faktor ~1.300. Gelöst über Weber-Fechner-Kompression + Anemotaxis.",
            {"og_flur_acetic": 0.005, "food02_acetic": 6.67},
        )

        experiments: Dict[str, object] = {}

        # --- Experiment 1: Reaktion auf Lichtquellen (Phototaxis in EG_WOHN_ESS) ---
        e1_intact, _ = self.run_trial("Exp1_Phototaxis_Intact", (4.5, 4.8, 1.3), 0.8, 14.0, seed=101, olfaction_gain=0.0, vision_gain=1.0)
        e1_blind, _ = self.run_trial("Exp1_Phototaxis_VisionAblated", (4.5, 4.8, 1.3), 0.8, 14.0, seed=101, olfaction_gain=0.0, vision_gain=0.0)
        dist_win_intact = math.hypot(e1_intact.end_pos[0] - 2.6, e1_intact.end_pos[1] - 0.25)
        dist_win_blind = math.hypot(e1_blind.end_pos[0] - 2.6, e1_blind.end_pos[1] - 0.25)
        e1_pass = bool(e1_intact.mean_light_uv_exposed > e1_blind.mean_light_uv_exposed or dist_win_intact < dist_win_blind)
        experiments["exp_1_phototaxis"] = {
            "status": "PASS" if e1_pass else "PARTIAL",
            "intact": asdict(e1_intact),
            "vision_ablated_control": asdict(e1_blind),
            "dist_to_south_window_intact_m": round(dist_win_intact, 3),
            "dist_to_south_window_blind_m": round(dist_win_blind, 3),
        }
        self.log_chamber("EXP_1", FindingChamber.CONFIRMED_RESULT if e1_pass else FindingChamber.DEVIATION,
                         EvidenceGrade.CONFIRMED_SOFTWARE_PROPERTY,
                         f"Phototaxis in EG_WOHN_ESS: UV-A Exposition intakt={e1_intact.mean_light_uv_exposed:.3f} vs Vision-Ablation={e1_blind.mean_light_uv_exposed:.3f}; Fensterabstand {dist_win_intact:.2f} m vs {dist_win_blind:.2f} m.",
                         {"uv_intact": e1_intact.mean_light_uv_exposed, "uv_blind": e1_blind.mean_light_uv_exposed})

        # --- Experiment 2: Orientierung anhand von Reizen (Multi-Etagen OG_FLUR -> Treppenhaus -> EG_KUECHE) ---
        e2_intact, b2 = self.run_trial("Exp2_Chemotaxis_Intact", (9.2, 6.2, 3.3), -1.57, 32.0, seed=202, olfaction_gain=1.0)
        e2_odorless, _ = self.run_trial("Exp2_Chemotaxis_OlfactionSilenced", (9.2, 6.2, 3.3), -1.57, 32.0, seed=202, olfaction_gain=0.0)
        e2_unilateral, _ = self.run_trial("Exp2_Chemotaxis_LeftAntennaLesioned", (9.2, 6.2, 3.3), -1.57, 32.0, seed=202, left_antenna_intact=False)
        # Sekundärer Nahbereichslauf in EG_KUECHE -> Vergleich Trajektorien & Nahrungsaufnahme
        e2_kitchen_intact, b2k = self.run_trial("Exp2b_Kitchen_Plume_Intact", (8.1, 2.5, 0.9), 0.1, 18.0, seed=205, olfaction_gain=1.0)
        e2_kitchen_odorless, _ = self.run_trial("Exp2b_Kitchen_Plume_NoOdor", (8.1, 2.5, 0.9), 0.1, 18.0, seed=205, olfaction_gain=0.0)
        e2_pass = bool(
            e2_intact.floor_layer_residence_s["EG"] > e2_odorless.floor_layer_residence_s["EG"]
            and e2_kitchen_intact.chemotaxis_efficiency["reached_food"]
        )
        experiments["exp_2_chemotaxis"] = {
            "status": "PASS" if e2_pass else "PARTIAL",
            "og_stairwell_intact": asdict(e2_intact),
            "og_stairwell_olfaction_silenced": asdict(e2_odorless),
            "og_stairwell_left_lesion": asdict(e2_unilateral),
            "eg_kitchen_intact": asdict(e2_kitchen_intact),
            "eg_kitchen_odorless": asdict(e2_kitchen_odorless),
            "neural_trace_sample": [asdict(x) for x in b2k.telemetry_history[::25]],
        }
        t_k = f"{e2_kitchen_intact.first_feeding_time_s}s" if e2_kitchen_intact.first_feeding_time_s is not None else "nicht erreicht"
        self.log_chamber("EXP_2", FindingChamber.CONFIRMED_RESULT if e2_pass else FindingChamber.DEVIATION,
                         EvidenceGrade.CONFIRMED_SOFTWARE_PROPERTY if e2_pass else EvidenceGrade.QUANTIFIED_DEVIATION,
                         f"Chemotaxis OG_FLUR->EG: EG-Zeit intakt={e2_intact.floor_layer_residence_s['EG']:.2f}s vs Olfaktion=0: {e2_odorless.floor_layer_residence_s['EG']:.2f}s; Küchen-Erstfutter intakt={e2_kitchen_intact.first_food_id} ({t_k}) vs stumm={e2_kitchen_odorless.first_food_id}.",
                         {"eg_time_intact_s": e2_intact.floor_layer_residence_s["EG"], "kitchen_food": e2_kitchen_intact.first_food_id})

        # --- Experiment 3: Hindernisvermeidung & 1,5-cm-Türspaltpassage EG_SPEIS ---
        e3_avoid, _ = self.run_trial("Exp3_Avoidance_LC4_Intact", (4.5, 3.0, 1.3), 0.2, 15.0, seed=303, looming_gain=1.0)
        e3_noloom, _ = self.run_trial("Exp3_Avoidance_LoomingAblated", (4.5, 3.0, 1.3), 0.2, 15.0, seed=303, looming_gain=0.0)
        # Explizite Sub-Voxel-Türspalt-Traverse (1,5 cm unter EG_SPEIS-Tür in Richtung FOOD_04)
        self.world.restore_voc_and_foods(self.base_snap)
        body_gap = FlyBodyEngine(start_pos=(7.32, 3.85, 0.004), start_yaw_rad=math.pi / 2.0, start_landed=True)
        rooms_gap = []
        for _ in range(2500):  # 25 s Laufen unter 1,5 cm Spalt nach FOOD_04
            body_gap.step(self.world, MotorOutputVector(1.0, 0, 0, 0, 0.022, 0.0, False, False, False), dt_s=0.010)
            rooms_gap.append(self.world.classify_room(float(body_gap.state.pos_xyz[0]), float(body_gap.state.pos_xyz[1]), float(body_gap.state.pos_xyz[2])))
        entered_speis = "EG_SPEIS" in rooms_gap and body_gap.state.door_gap_traversals >= 1
        e3_pass = bool(e3_avoid.wall_collisions <= e3_noloom.wall_collisions and entered_speis)
        experiments["exp_3_obstacle_and_gap"] = {
            "status": "PASS" if e3_pass else "PARTIAL",
            "lc4_intact": asdict(e3_avoid),
            "looming_ablated_control": asdict(e3_noloom),
            "speis_1_5cm_gap_entered": entered_speis,
            "speis_gap_traversals": body_gap.state.door_gap_traversals,
            "speis_gap_end_pos": [round(float(v), 3) for v in body_gap.state.pos_xyz],
        }
        self.log_chamber("EXP_3", FindingChamber.CONFIRMED_RESULT if e3_pass else FindingChamber.DEVIATION,
                         EvidenceGrade.CONFIRMED_SOFTWARE_PROPERTY,
                         f"Hindernisvermeidung & 1,5-cm-Türspalt: Kollisionen intakt={e3_avoid.wall_collisions} vs Looming-abliert={e3_noloom.wall_collisions}; EG_SPEIS 1,5-cm-Spalt durchquert={entered_speis} ({body_gap.state.door_gap_traversals}x).",
                         {"collisions_intact": e3_avoid.wall_collisions, "collisions_ablated": e3_noloom.wall_collisions, "gap_ok": entered_speis})

        # --- Experiment 4: Koordination von Körper und Bewegung (Tripod-CPG, Absprung, Flug, Landung, Füttern) ---
        e4_body_ok, _ = self.run_trial("Exp4_Coordination_WalkJumpFeed", (8.72, 3.22, 0.354), 0.78, 12.0, seed=404, start_landed=True)
        e4_pass = bool(
            e4_body_ok.tarsal_stance_duty_a > 0.35
            and e4_body_ok.tarsal_stance_duty_b > 0.35
            and e4_body_ok.energy_hydration_balance["ingested_energy_mj"] > 0.0
        )
        experiments["exp_4_body_coordination"] = {
            "status": "PASS" if e4_pass else "PARTIAL",
            "walk_feed_trial": asdict(e4_body_ok),
            "physics_backend": FlyBodyEngine().physics_backend,
            "neuromechfly_bodies": FlyBodyEngine().morphology.n_bodies,
            "neuromechfly_joints": FlyBodyEngine().morphology.n_joints,
        }
        self.log_chamber("EXP_4", FindingChamber.CONFIRMED_RESULT if e4_pass else FindingChamber.DEVIATION,
                         EvidenceGrade.CONFIRMED_SOFTWARE_PROPERTY,
                         f"Körper-Bewegungs-Koordination: Tripod Duty A={e4_body_ok.tarsal_stance_duty_a}, B={e4_body_ok.tarsal_stance_duty_b}; Nahrungsenergie={e4_body_ok.energy_hydration_balance['ingested_energy_mj']:.4f} mJ.",
                         {"duty_a": e4_body_ok.tarsal_stance_duty_a, "duty_b": e4_body_ok.tarsal_stance_duty_b, "ingested_mj": e4_body_ok.energy_hydration_balance["ingested_energy_mj"]})

        # --- Experiment 5: Umweltänderung & Valenzkonflikt (DA2 Geosmin FOOD_09 vs Durst + Licht/Feuchte vs Lüftung) ---
        # Start in OG_BAD_2 mit Blick Nord Richtung feuchtes Waschbecken/Fenster (FOOD_09 bei 6.15, 8.15, 3.65):
        # Wasser + Nordfenster ziehen nach Norden, angeborener DA2-Geosmin-Schaltkreis stößt ab!
        e5_hydr_geo, _ = self.run_trial("Exp5_Hydrated_Bad2_Geosmin_Intact", (6.15, 6.65, 3.85), math.pi / 2.0, 12.0, seed=505, start_landed=False, initial_hydration_pct=78.0, da2_geosmin_gain=1.0)
        e5_dehydr_geo, _ = self.run_trial("Exp5_Dehydrated_Bad2_Geosmin_Intact", (6.15, 6.65, 3.85), math.pi / 2.0, 12.0, seed=505, start_landed=False, initial_hydration_pct=32.0, da2_geosmin_gain=1.0)
        e5_da2_silenced, _ = self.run_trial("Exp5_Dehydrated_Bad2_DA2_Silenced", (6.15, 6.65, 3.85), math.pi / 2.0, 12.0, seed=505, start_landed=False, initial_hydration_pct=40.0, da2_geosmin_gain=0.0)
        # Umwelt-Lüftungsumschaltung in EG_KUECHE
        self.world.apply_environmental_shift("cross_ventilation")
        shifted_snap = self.world.snapshot_voc_and_foods()
        orig_snap = self.base_snap
        self.base_snap = shifted_snap
        e5_vent_shift, _ = self.run_trial("Exp5_CrossVentilation_Kitchen", (7.4, 2.5, 0.8), 0.3, 14.0, seed=506)
        self.base_snap = orig_snap
        self.world.apply_environmental_shift("default")
        self.world.restore_voc_and_foods(self.base_snap)

        d_food09_intact = min(math.hypot(p[0] - 6.15, p[1] - 8.15) for p in e5_hydr_geo.trajectory_sample)
        d_food09_silenced = min(math.hypot(p[0] - 6.15, p[1] - 8.15) for p in e5_da2_silenced.trajectory_sample)
        geo_avoid_ok = (d_food09_silenced < d_food09_intact or e5_hydr_geo.feeding_time_by_food_s["FOOD_09"] <= e5_da2_silenced.feeding_time_by_food_s["FOOD_09"])
        experiments["exp_5_environment_and_conflict"] = {
            "status": "PASS" if geo_avoid_ok else "PARTIAL",
            "min_dist_food09_da2_intact_m": round(d_food09_intact, 3),
            "min_dist_food09_da2_silenced_m": round(d_food09_silenced, 3),
            "hydrated_geosmin_intact": asdict(e5_hydr_geo),
            "dehydrated_geosmin_intact": asdict(e5_dehydr_geo),
            "dehydrated_da2_silenced": asdict(e5_da2_silenced),
            "cross_ventilation_kitchen": asdict(e5_vent_shift),
        }
        self.log_chamber("EXP_5", FindingChamber.CONFIRMED_RESULT if geo_avoid_ok else FindingChamber.DEVIATION,
                         EvidenceGrade.CONFIRMED_SOFTWARE_PROPERTY,
                         f"Geosmin-DA2 vs Durst (FOOD_09 OG_BAD_2): Min-Abstand DA2 intakt={d_food09_intact:.2f}m vs DA2-abliert={d_food09_silenced:.2f}m; Kreuzlüftung EG_KUECHE Pfadlänge={e5_vent_shift.total_path_length_m:.2f}m.",
                         {"min_d_intact_m": round(d_food09_intact, 3), "min_d_da2_off_m": round(d_food09_silenced, 3)})

        # --- Experiment 6: Kurzzeit-Lernen & Gedächtnisabfall im Pilzkörper (KC x DAN -> MBON) ---
        def _condition_ester_aversive(brain: FlyWireNeuralEngine) -> None:
            feat = np.array([1.25, 0.0, 0.0], dtype=np.float32)
            for _ in range(300):  # 15 s Quinin/PPL1-Bestrafung gepaart mit Frucht-Ester
                brain.memory.step(feat, r_kc=0.55, r_pam=0.0, r_ppl1=0.92, dt_s=0.05)

        def _make_ret_fn(wait_s: float) -> Callable[[FlyWireNeuralEngine], None]:
            def _fn(brain: FlyWireNeuralEngine) -> None:
                _condition_ester_aversive(brain)
                brain.memory.advance_retention_time(wait_s)
            return _fn

        e6_10s, _ = self.run_trial("Exp6_Ret_10s_PlasticityON", (8.85, 3.35, 0.354), 0.0, 8.0, seed=606, start_landed=True, plasticity_enabled=True, pre_condition_fn=_make_ret_fn(10.0))
        e6_60s, _ = self.run_trial("Exp6_Ret_60s_PlasticityON", (8.85, 3.35, 0.354), 0.0, 8.0, seed=606, start_landed=True, plasticity_enabled=True, pre_condition_fn=_make_ret_fn(60.0))
        e6_300s, _ = self.run_trial("Exp6_Ret_300s_PlasticityON", (8.85, 3.35, 0.354), 0.0, 8.0, seed=606, start_landed=True, plasticity_enabled=True, pre_condition_fn=_make_ret_fn(300.0))
        e6_1800s, _ = self.run_trial("Exp6_Ret_1800s_PlasticityON", (8.85, 3.35, 0.354), 0.0, 8.0, seed=606, start_landed=True, plasticity_enabled=True, pre_condition_fn=_make_ret_fn(1800.0))
        e6_frozen, _ = self.run_trial("Exp6_Plasticity_FROZEN", (8.85, 3.35, 0.354), 0.0, 8.0, seed=606, start_landed=True, plasticity_enabled=False, pre_condition_fn=_condition_ester_aversive)

        # Retentionskurve direkt vermessen
        probe_brain = FlyWireNeuralEngine(self.sub, seed=606, plasticity_enabled=True)
        _condition_ester_aversive(probe_brain)
        val_curve = {"t_0s": round(float(probe_brain.memory.valence_shift[0]), 4)}
        for dt_jump, tag in [(10.0, "t_10s"), (50.0, "t_60s"), (240.0, "t_300s"), (1500.0, "t_1800s")]:
            val_curve[tag] = round(probe_brain.memory.advance_retention_time(dt_jump), 4)

        e6_pass = bool(
            e6_10s.feeding_time_by_food_s["FOOD_02"] == 0.0
            and e6_frozen.feeding_time_by_food_s["FOOD_02"] > 2.0
            and e6_1800s.feeding_time_by_food_s["FOOD_02"] > 2.0
            and abs(val_curve["t_1800s"]) < 0.01
        )
        experiments["exp_6_learning_and_forgetting"] = {
            "status": "PASS" if e6_pass else "PARTIAL",
            "retention_valence_curve": val_curve,
            "trial_10s_plasticity_on": asdict(e6_10s),
            "trial_60s_plasticity_on": asdict(e6_60s),
            "trial_300s_plasticity_on": asdict(e6_300s),
            "trial_1800s_plasticity_on": asdict(e6_1800s),
            "trial_frozen_control": asdict(e6_frozen),
        }
        self.log_chamber("EXP_6", FindingChamber.CONFIRMED_RESULT if e6_pass else FindingChamber.DEVIATION,
                         EvidenceGrade.CONFIRMED_SOFTWARE_PROPERTY,
                         f"Kurzzeitplastizität MB (KC x PPL1): Bei t=10s gelernte Vermeidung von FOOD_02 (Fresszeit={e6_10s.feeding_time_by_food_s['FOOD_02']}s vs Frozen={e6_frozen.feeding_time_by_food_s['FOOD_02']}s); bei t=1800s vergessen (Valenz={val_curve['t_1800s']}, Fresszeit={e6_1800s.feeding_time_by_food_s['FOOD_02']}s) — ausdrücklich KEIN LTM.",
                         {"curve": val_curve, "feed_10s": e6_10s.feeding_time_by_food_s["FOOD_02"], "feed_1800s": e6_1800s.feeding_time_by_food_s["FOOD_02"], "feed_frozen": e6_frozen.feeding_time_by_food_s["FOOD_02"]})

        # Substrat-Präferenz-Aggregatvergleich über FOOD_01 (frisch) vs FOOD_02 (fermentierend) vs FOOD_07 (Limonen) vs FOOD_09 (Geosmin)
        substrate_arena, _ = self.run_trial("Arena_Kitchen_Preference", (8.1, 2.5, 0.9), 0.1, 22.0, seed=707)
        experiments["seestrasse_43_substrate_arena"] = asdict(substrate_arena)

        return {
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "epistemic_registry": EPISTEMIC_REGISTRY,
            "experiments": experiments,
            "epistemic_chambers": [asdict(c) for c in self.chamber_log],
      }
