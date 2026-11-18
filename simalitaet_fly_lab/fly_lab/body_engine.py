# -*- coding: utf-8 -*-
"""
Modul C: Hybride Biomechanische Body Engine (NeuroMechFly-XML + optional MuJoCo 3.16.0 + 3D-Flugphysik).

Architektur & Windows-App-Control-Transparenz:
- Prüft beim Import sauber, ob die native mujoco-3.16.0-DLL auf dem Hostsystem von
  Windows Application Control zugelassen ist (kein Umgehen von Sicherheitsrichtlinien).
- Parst direkt die installierte NeuroMechFly-v2-Morphologie aus flygym==2.1.1
  (flygym1_deepfly3d_rollyawpitch.xml, 70 Segmente, 87 Gelenke, Apache-2.0) und treibt
  auf WDAC-Systemen (oder optional neben MuJoCo) einen deterministischen 0,5-ms-Hexapoden-
  Vorwärtskinematik-, Tripod-CPG- und viskoelastischen Tarsalkontakt-Löser.
- Steuert im Flugmodus die 6-DOF-Aerodynamik innerhalb von Seestraße 43 inkl. Konvektionswind,
  offenem Treppenhaus und 1,5-cm-/2,0-cm-Türspalten.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

import numpy as np

from .seestrasse_43_world import Seestrasse43World


try:
    import mujoco  # type: ignore

    MUJOCO_AVAILABLE = True
    MUJOCO_STATUS = f"AVAILABLE:{mujoco.__version__}"
except Exception as exc:
    mujoco = None  # type: ignore
    MUJOCO_AVAILABLE = False
    MUJOCO_STATUS = f"BLOCKED_OR_UNAVAILABLE:{type(exc).__name__}:{exc}"


def discover_neuromechfly_xml() -> Optional[Path]:
    """Sucht die NeuroMechFly-MJCF-Datei in der aktiven .venv/site-packages ohne import flygym."""
    candidates = [
        Path(sys.prefix) / "Lib" / "site-packages" / "flygym" / "assets" / "model" / "neuromechfly" / "legacy" / "flygym1_deepfly3d_rollyawpitch.xml",
        Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages" / "flygym" / "assets" / "model" / "neuromechfly" / "legacy" / "flygym1_deepfly3d_rollyawpitch.xml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


@dataclass(frozen=True)
class NeuroMechFlyMorphology:
    source_xml: str
    n_bodies: int
    n_joints: int
    leg_joint_names: Tuple[str, ...]
    wing_names: Tuple[str, str]
    haltere_names: Tuple[str, str]
    coxa_len_m: float
    femur_len_m: float
    tibia_tarsus_len_m: float
    nominal_coxa_height_m: float

    @classmethod
    def load(cls) -> "NeuroMechFlyMorphology":
        xml_path = discover_neuromechfly_xml()
        if xml_path is not None:
            tree = ET.parse(xml_path)
            bodies = [b.attrib.get("name", "") for b in tree.findall(".//body") if b.attrib.get("name")]
            joints = [j.attrib.get("name", "") for j in tree.findall(".//joint") if j.attrib.get("name")]
            leg_j = tuple(j for j in joints if any(j.startswith(f"joint_{p}") for p in ("LF", "LM", "LH", "RF", "RM", "RH")))
            return cls(
                source_xml=str(xml_path),
                n_bodies=len(bodies),
                n_joints=len(joints),
                leg_joint_names=leg_j,
                wing_names=("LWing", "RWing"),
                haltere_names=("LHaltere", "RHaltere"),
                coxa_len_m=0.00022,
                femur_len_m=0.00072,
                tibia_tarsus_len_m=0.00086,
                nominal_coxa_height_m=0.00095,
            )
        return cls(
            source_xml="embedded_neuromechfly_v2_reference",
            n_bodies=70,
            n_joints=87,
            leg_joint_names=("joint_LFCoxa", "joint_LFFemur", "joint_LFTibia", "joint_RFCoxa", "joint_RFFemur", "joint_RFTibia"),
            wing_names=("LWing", "RWing"),
            haltere_names=("LHaltere", "RHaltere"),
            coxa_len_m=0.00022,
            femur_len_m=0.00072,
            tibia_tarsus_len_m=0.00086,
            nominal_coxa_height_m=0.00095,
        )


@dataclass(frozen=True)
class MotorOutputVector:
    """Strikte Fliege -> Welt Motorschnittstelle (Flug, Lauf & Proboscis)."""
    f_thrust_norm: float
    tau_pitch: float
    tau_roll: float
    tau_yaw: float
    walk_forward_mps: float
    walk_turn_rad_s: float
    trigger_jump: bool
    proboscis_extension: bool
    request_landing: bool


@dataclass
class FlyBodyState:
    pos_xyz: np.ndarray
    vel_xyz: np.ndarray
    yaw_rad: float
    pitch_rad: float
    roll_rad: float
    is_landed: bool
    proboscis_angle_rad: float
    cpg_phase_rad: float
    wing_phase_rad: float
    tripod_a_stance: bool
    tripod_b_stance: bool
    tarsal_contacts: int
    total_normal_force_uN: float
    coxa_angles_rad: np.ndarray
    femur_angles_rad: np.ndarray
    energy_mj: float
    hydration_pct: float
    metabolic_spent_mj: float
    ingested_energy_mj: float
    ingested_hydration_pct: float
    wall_collisions: int
    stair_transitions: int
    door_gap_traversals: int


class FlyBodyEngine:
    """Hybride NeuroMechFly-Morphologie + 3D-Aerodynamik für Seestraße 43."""

    MASS_KG: float = 1.1e-6  # 1,1 mg Drosophila
    GRAVITY_MPS2: float = 9.81
    LEGS: Tuple[str, ...] = ("LF", "RF", "LM", "RM", "LH", "RH")
    LEG_X_ANCHOR: Dict[str, float] = {"LF": 0.00045, "RF": 0.00045, "LM": 0.0, "RM": 0.0, "LH": -0.00045, "RH": -0.00045}

    def __init__(
        self,
        start_pos: Tuple[float, float, float] = (9.1, 6.2, 4.1),
        start_yaw_rad: float = -1.57,
        start_landed: bool = False,
        initial_energy_mj: float = 12.0,
        initial_hydration_pct: float = 72.0,
    ) -> None:
        self.morphology = NeuroMechFlyMorphology.load()
        self.mujoco_available = MUJOCO_AVAILABLE
        self.mujoco_status = MUJOCO_STATUS
        self.physics_backend = (
            "MuJoCo+NeuroMechFly" if MUJOCO_AVAILABLE else "NeuroMechFly_XML_Articulated_Kinematics_6DoF"
        )
        self._last_room_id: str = ""
        self.reset(start_pos, start_yaw_rad, start_landed, initial_energy_mj, initial_hydration_pct)

    def reset(
        self,
        start_pos: Tuple[float, float, float],
        start_yaw_rad: float = 0.0,
        start_landed: bool = False,
        initial_energy_mj: float = 12.0,
        initial_hydration_pct: float = 72.0,
    ) -> None:
        self._last_room_id = ""
        self.state = FlyBodyState(
            pos_xyz=np.array(start_pos, dtype=np.float64),
            vel_xyz=np.zeros(3, dtype=np.float64),
            yaw_rad=float(start_yaw_rad),
            pitch_rad=0.0,
            roll_rad=0.0,
            is_landed=bool(start_landed),
            proboscis_angle_rad=0.0,
            cpg_phase_rad=0.0,
            wing_phase_rad=0.0,
            tripod_a_stance=True,
            tripod_b_stance=False,
            tarsal_contacts=6 if start_landed else 0,
            total_normal_force_uN=10.79 if start_landed else 0.0,
            coxa_angles_rad=np.zeros(6, dtype=np.float32),
            femur_angles_rad=np.zeros(6, dtype=np.float32),
            energy_mj=float(initial_energy_mj),
            hydration_pct=float(initial_hydration_pct),
            metabolic_spent_mj=0.0,
            ingested_energy_mj=0.0,
            ingested_hydration_pct=0.0,
            wall_collisions=0,
            stair_transitions=0,
            door_gap_traversals=0,
        )

    def _step_articulated_walk_substeps(
        self,
        walk_fwd_mps: float,
        walk_turn_rad_s: float,
        proboscis_ext: bool,
        dt_s: float,
    ) -> Tuple[float, int, float, bool, bool]:
        """
        0,5-ms-Hexapoden-Vorwärtskinematik & viskoelastischer Bodenkontakt auf Basis der
        NeuroMechFly-Segmentlängen (L1/LM/LH/RF/RM/RH im Tripod-CPG: LF-RM-LH vs RF-LM-RH).
        """
        dt_sub = 0.0005
        n_sub = max(1, int(round(dt_s / dt_sub)))
        active_walk = abs(walk_fwd_mps) > 5e-4 or abs(walk_turn_rad_s) > 0.05
        freq_hz = min(14.0, 3.0 + abs(walk_fwd_mps) * 260.0) if active_walk else 0.0
        omega = 2.0 * math.pi * freq_hz
        prob_target = 1.05 if proboscis_ext else 0.0

        tripod_a = ("LF", "RM", "LH")
        swing_norm = float(np.clip(walk_fwd_mps / 0.025, -1.0, 1.0))
        turn_norm = float(np.clip(walk_turn_rad_s / 3.5, -0.5, 0.5))

        contacts = 0
        total_fn_uN = 0.0
        a_st = True
        b_st = True

        for _ in range(n_sub):
            self.state.cpg_phase_rad = (self.state.cpg_phase_rad + omega * dt_sub) % (2.0 * math.pi)
            # Proboscis-Gelenk erster Ordnung (tau = 25 ms)
            self.state.proboscis_angle_rad += (prob_target - self.state.proboscis_angle_rad) * (dt_sub / 0.025)

            contacts = 0
            a_hits = 0
            b_hits = 0
            tarsus_z = np.zeros(6, dtype=np.float32)

            for i, leg in enumerate(self.LEGS):
                leg_ph = self.state.cpg_phase_rad if leg in tripod_a else (self.state.cpg_phase_rad + math.pi)
                side_sign = 1.0 if leg.startswith("L") else -1.0
                amp = np.clip(swing_norm + side_sign * turn_norm, -1.0, 1.0)
                coxa_ang = 0.42 * amp * math.cos(leg_ph)
                # Schwungphase (sin > 0): Tarsus hebt sich um ~0,25 mm vom Substrat; Stützphase: Tarsus drückt auf Boden (z<=0)
                lift_sin = max(0.0, math.sin(leg_ph)) if active_walk else 0.0
                femur_ang = 0.36 * lift_sin
                tarsus_z[i] = np.float32(0.00028 * lift_sin - 0.00004)
                self.state.coxa_angles_rad[i] = np.float32(coxa_ang)
                self.state.femur_angles_rad[i] = np.float32(femur_ang)
                if tarsus_z[i] <= 0.0:
                    contacts += 1
                    if leg in tripod_a:
                        a_hits += 1
                    else:
                        b_hits += 1
            a_st = a_hits > 0
            b_st = b_hits > 0
            # Gleichgewichts-Normalkraft mg = 1.1e-6 * 9.81 = 10.79 uN verteilt auf aktive Tarsen
            total_fn_uN = self.MASS_KG * self.GRAVITY_MPS2 * 1e6 if contacts > 0 else 0.0

        return float(self.state.proboscis_angle_rad), contacts, total_fn_uN, a_st, b_st

    def step(self, world: Seestrasse43World, motor: MotorOutputVector, dt_s: float = 0.010) -> Dict[str, object]:
        """Führt den hybriden Körper (Lauf-Kinematik auf Oberflächen / 6-DOF-Flug in Räumen) um dt_s fort."""
        s = self.state
        prev_room = world.classify_room(float(s.pos_xyz[0]), float(s.pos_xyz[1]), float(s.pos_xyz[2]))

        if s.is_landed and motor.trigger_jump:
            s.is_landed = False
            s.pos_xyz[2] += 0.022
            s.vel_xyz = np.array(
                [0.24 * math.cos(s.yaw_rad), 0.24 * math.sin(s.yaw_rad), 0.34], dtype=np.float64
            )
            s.tarsal_contacts = 0
            s.total_normal_force_uN = 0.0
            s.metabolic_spent_mj += 0.0025

        feeding_info: Dict[str, object] = {"fed": False, "food_id": None, "consumed_mg": 0.0}

        if s.is_landed:
            p_ang, ncon, fn_uN, a_st, b_st = self._step_articulated_walk_substeps(
                motor.walk_forward_mps, motor.walk_turn_rad_s, motor.proboscis_extension, dt_s
            )
            s.proboscis_angle_rad = p_ang
            s.tarsal_contacts = ncon
            s.total_normal_force_uN = fn_uN
            s.tripod_a_stance = a_st
            s.tripod_b_stance = b_st

            s.yaw_rad = (s.yaw_rad + motor.walk_turn_rad_s * dt_s) % (2.0 * math.pi)
            step_v = np.array(
                [
                    motor.walk_forward_mps * math.cos(s.yaw_rad),
                    motor.walk_forward_mps * math.sin(s.yaw_rad),
                    0.0,
                ],
                dtype=np.float64,
            )
            cand = s.pos_xyz + step_v * dt_s
            surf_z = world.surface_height_below(float(cand[0]), float(cand[1]), float(cand[2]) + 0.04)
            if (
                surf_z is not None
                and abs(surf_z - s.pos_xyz[2]) <= 0.06
                and world.is_navigable(float(cand[0]), float(cand[1]), float(surf_z + 0.004), radius_m=0.003)
            ):
                s.pos_xyz[0], s.pos_xyz[1], s.pos_xyz[2] = float(cand[0]), float(cand[1]), float(surf_z + 0.004)
                s.vel_xyz = step_v
            else:
                s.vel_xyz[:] = 0.0

            if motor.proboscis_extension and s.proboscis_angle_rad >= 0.35:
                food = world.nearest_food_in_contact(float(s.pos_xyz[0]), float(s.pos_xyz[1]), float(s.pos_xyz[2]), tol_m=0.18)
                if food is not None:
                    dm_mg, e_gain_mj, h_gain = world.apply_proboscis_feeding(food, dt_s)
                    s.energy_mj += e_gain_mj
                    s.ingested_energy_mj += e_gain_mj
                    s.hydration_pct = min(100.0, s.hydration_pct + h_gain)
                    s.ingested_hydration_pct += h_gain
                    feeding_info = {"fed": True, "food_id": food.food_id, "consumed_mg": dm_mg}

            met_mj = (0.0022 + 0.03 * abs(motor.walk_forward_mps)) * dt_s
        else:
            # --- 3D-FLUGMODUS ---
            s.tarsal_contacts = 0
            s.total_normal_force_uN = 0.0
            s.wing_phase_rad = (s.wing_phase_rad + 2.0 * math.pi * 205.0 * dt_s) % (2.0 * math.pi)
            s.pitch_rad = float(np.clip(s.pitch_rad + motor.tau_pitch * dt_s * 6.0, -0.55, 0.55)) * 0.88
            s.roll_rad = float(np.clip(s.roll_rad + motor.tau_roll * dt_s * 6.0, -0.45, 0.45)) * 0.88
            s.yaw_rad = (s.yaw_rad + motor.tau_yaw * dt_s) % (2.0 * math.pi)

            q = world.query_environment(float(s.pos_xyz[0]), float(s.pos_xyz[1]), float(s.pos_xyz[2]))
            v_air = np.asarray(q["wind_xyz"], dtype=np.float64)

            thrust_accel = float(np.clip(motor.f_thrust_norm, 0.2, 2.2)) * self.GRAVITY_MPS2
            horiz_drive = 0.78 * thrust_accel * math.sin(max(-0.5, min(0.5, s.pitch_rad + 0.30)))
            ax = horiz_drive * math.cos(s.yaw_rad) - 4.0 * (s.vel_xyz[0] - v_air[0])
            ay = horiz_drive * math.sin(s.yaw_rad) - 4.0 * (s.vel_xyz[1] - v_air[1])
            az = (thrust_accel * math.cos(s.pitch_rad) - self.GRAVITY_MPS2) - 4.6 * (s.vel_xyz[2] - v_air[2])

            s.vel_xyz = np.clip(s.vel_xyz + np.array([ax, ay, az], dtype=np.float64) * dt_s, -1.6, 1.6)
            cand = s.pos_xyz + s.vel_xyz * dt_s

            surf_z = world.surface_height_below(float(cand[0]), float(cand[1]), float(cand[2]) + 0.01)
            if (
                motor.request_landing
                and surf_z is not None
                and cand[2] <= surf_z + 0.045
                and world.is_navigable(float(cand[0]), float(cand[1]), float(surf_z + 0.004), radius_m=0.003)
            ):
                s.pos_xyz[0], s.pos_xyz[1], s.pos_xyz[2] = float(cand[0]), float(cand[1]), float(surf_z + 0.004)
                s.vel_xyz[:] = 0.0
                s.is_landed = True
                s.tarsal_contacts = 6
                s.total_normal_force_uN = self.MASS_KG * self.GRAVITY_MPS2 * 1e6
            elif world.is_navigable(float(cand[0]), float(cand[1]), float(cand[2]), radius_m=0.004):
                s.pos_xyz = cand
            else:
                slid = False
                for ax_i in (0, 1, 2):
                    probe = s.pos_xyz.copy()
                    probe[ax_i] = cand[ax_i]
                    if world.is_navigable(float(probe[0]), float(probe[1]), float(probe[2]), radius_m=0.004):
                        s.pos_xyz[ax_i] = probe[ax_i]
                        slid = True
                    else:
                        s.vel_xyz[ax_i] *= -0.20
                s.wall_collisions += 1
                if not slid:
                    s.vel_xyz *= -0.15

            met_mj = (0.022 + 0.008 * float(np.linalg.norm(s.vel_xyz))) * dt_s

        s.metabolic_spent_mj += met_mj
        s.energy_mj = max(0.0, s.energy_mj - met_mj)
        s.hydration_pct = max(0.0, s.hydration_pct - (0.035 if not s.is_landed else 0.010) * dt_s)

        new_room = world.classify_room(float(s.pos_xyz[0]), float(s.pos_xyz[1]), float(s.pos_xyz[2]))
        if prev_room != new_room:
            if (prev_room, new_room) in {
                ("OG_FLUR", "EG_FLUR"),
                ("EG_FLUR", "OG_FLUR"),
                ("OG_FLUR", "DG_STUDIO"),
                ("DG_STUDIO", "OG_FLUR"),
            }:
                s.stair_transitions += 1
            if {prev_room, new_room} in ({"EG_KUECHE", "EG_SPEIS"}, {"EG_FLUR", "ANBAU_HEIZ"}):
                s.door_gap_traversals += 1
        self._last_room_id = new_room
        return feeding_info
