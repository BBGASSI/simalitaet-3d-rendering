# -*- coding: utf-8 -*-
"""
Module B (Neural Engine) & E (Mushroom Body Learning & Short-Term Memory).

Verbindet das reale FlyWire-v783-Konnektom (5.764-Neuronen-Subgraph mit 134.066 echten
gerichteten Synapsen sowie Ganzhirn-Validierung auf 138.639 Neuronen / 54,49 Mio. Synapsen)
im geschlossenen Δt = 10 ms-Regelkreis mit der 3D-Umwelt Seestraße 43.

Epistemische Kennzeichnung:
- [EMPIRICAL_CONNECTOME]: FlyWire-v783-Synapsengewichte W_sub/W_full, Neurotransmitter-Vorzeichen
  (ACh +, GABA -, Glut -), identifizierte Zellpools (ORN_DM1/DM2/DM4/VA2/DA2/DC1/V/DA1,
  Kenyon_Cell, PAM/PPL1, MBON, MeTu, LC4/LPLC2, JO, TRN, HRN, DNa01/DNa02/DNp09/MDN/DNp01).
- [MODEL_ASSUMPTION]: Homogene LIF-Membranparameter (tau_m=20 ms, V_rest=-52 mV, V_thresh=-45 mV),
  Sensor-zu-ORN/MeTu/LC4-Transduktionskurven, Hunger/Durst-Zustandsgating, sowie die
  Halskonnektiv-/VNC-Dekodierung auf Schub-/Nick-/Gier- und Rüssel-Aktoren.
- [MEMORY_BOUNDARY]: Explizit NUR kurzzeitige 3-Faktor-Plastizität (KC x DAN -> MBON) mit
  exponentiellem Vergessen (tau_decay = 180 s). Keine Behauptung von Langzeitgedächtnis oder Bewusstsein.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from .body_engine import MotorOutputVector
from .connectome import FlyWireConnectome, FlyWireSubcircuit
from .seestrasse_43_world import VOC_CLASSES
from .sensory_interface import SensorInputVector


EPISTEMIC_REGISTRY: Dict[str, List[str]] = {
    "EMPIRICAL_CONNECTOME": [
        "FlyWire v783 138.639 proofread neurons / 15.091.983 directed edges / 54.492.922 synapses",
        "Induced sensorimotor-MB-DN subcircuit (100% unmodified FlyWire v783 CSR synaptic weights)",
        "Bilateral neuron identities from Schlegel et al. Nature 2024 (DM1/DM2/VA2 vs DA2 Geosmin, KC, PAM, PPL1, MBON, MeTu, LC4/LPLC2, DNa01/02, DNp09, MDN, DNp01)",
    ],
    "MODEL_ASSUMPTION": [
        "Shiu et al. 2024 uniform LIF time constants (tau_m=20 ms, tau_syn=5 ms, V_rest=-52 mV, V_thresh=-45 mV)",
        "Normalized rate+spike hybrid readout across 5 x 2 ms substeps per 10 ms world tick",
        "Neck-connective / VNC readout mapping descending neuron pools to 6-DoF flight & tripod walk commands",
        "Effective bilateral antennal sampling baseline scaling (0.045 m) for 0.25 m indoor plume filaments",
    ],
    "MEMORY_BOUNDARY": [
        "Short-term Mushroom Body associative valence shift (tau_decay = 180 s) only; decays to baseline by 1800 s",
        "No protein-synthesis-dependent LTM (CREB/LTM) and zero consciousness claim",
    ],
}


@dataclass
class NeuralTelemetryStep:
    mean_orn_ester: float
    mean_orn_da2_geosmin: float
    mean_vision_metu: float
    mean_looming_lc4: float
    mean_kc: float
    mean_pam: float
    mean_ppl1: float
    mean_dn_steer_diff: float
    mean_dn_forward: float
    mean_dn_jump: float
    mb_ester_valence: float
    total_spikes_step: int


class MushroomBodyShortTermMemory:
    """
    Modul E: Kurzzeitige assoziative Valenzplastizität (KC x DAN -> MBON).
    Implementiert explizit NUR Kurzzeitgedächtnis mit exponentiellem Vergessen (tau_decay = 180 s).
    """

    def __init__(
        self,
        enabled: bool = True,
        eta_reward: float = 0.085,
        eta_punish: float = 0.145,
        tau_decay_s: float = 180.0,
    ) -> None:
        self.enabled = bool(enabled)
        self.eta_reward = float(eta_reward)
        self.eta_punish = float(eta_punish)
        self.tau_decay_s = float(tau_decay_s)
        # gelernte Valenz-Verschiebung für [ester/ethanol/acid, terpenes, geosmin]
        self.valence_shift = np.zeros(3, dtype=np.float32)
        self.conditioning_events: int = 0
        self.cumulative_pam_signal: float = 0.0
        self.cumulative_ppl1_signal: float = 0.0

    def reset(self) -> None:
        self.valence_shift.fill(0.0)
        self.conditioning_events = 0
        self.cumulative_pam_signal = 0.0
        self.cumulative_ppl1_signal = 0.0

    def step(
        self,
        odor_features: np.ndarray,
        r_kc: float,
        r_pam: float,
        r_ppl1: float,
        dt_s: float,
    ) -> np.ndarray:
        # Vergessen wirkt unabhängig davon, ob neues Lernen aktiv ist (oder bleibt eingefroren wenn disabled)
        if not self.enabled:
            return self.valence_shift
        decay_factor = math.exp(-dt_s / max(1.0, self.tau_decay_s))
        self.valence_shift *= np.float32(decay_factor)

        if r_kc > 0.02 and (r_pam > 0.05 or r_ppl1 > 0.05):
            # 3-Faktor-Regel: präsynaptische Duftrepräsentation (KC) x modulierendes DAN (PAM/PPL1)
            f_norm = np.clip(odor_features, 0.0, 2.0) / 2.0
            delta = (
                self.eta_reward * r_pam * r_kc * f_norm
                - self.eta_punish * r_ppl1 * r_kc * f_norm
            ) * np.float32(dt_s * 12.0)
            self.valence_shift = np.clip(self.valence_shift + delta, -1.6, 1.2).astype(np.float32)
            self.conditioning_events += 1
        self.cumulative_pam_signal += float(r_pam * dt_s)
        self.cumulative_ppl1_signal += float(r_ppl1 * dt_s)
        return self.valence_shift

    def advance_retention_time(self, elapsed_s: float) -> float:
        """Simuliert reine Behaltensdauer ohne neues Training (für Experiment 6 Retentionskurve)."""
        if elapsed_s > 0.0:
            self.valence_shift *= np.float32(math.exp(-elapsed_s / max(1.0, self.tau_decay_s)))
        return float(self.valence_shift[0])


class FlyWireNeuralEngine:
    """
    Modul B: Biologisch fundierter geschlossener Regelkreis auf Basis realer FlyWire-v783-Gewichte.
    """

    V_REST: float = -52.0
    V_THRESH: float = -45.0
    TAU_M_S: float = 0.020
    TAU_SYN_S: float = 0.005

    def __init__(
        self,
        subcircuit: FlyWireSubcircuit,
        seed: int = 42,
        olfaction_gain: float = 1.0,
        vision_gain: float = 1.0,
        looming_gain: float = 1.0,
        da2_geosmin_gain: float = 1.0,
        plasticity_enabled: bool = True,
    ) -> None:
        self.sub = subcircuit
        self.n_sub = int(subcircuit.w_sub.shape[0])
        self.rng = np.random.default_rng(seed)

        # Ablations- & Versuchs-Schalter
        self.olfaction_gain = float(olfaction_gain)
        self.vision_gain = float(vision_gain)
        self.looming_gain = float(looming_gain)
        self.da2_geosmin_gain = float(da2_geosmin_gain)
        self.memory = MushroomBodyShortTermMemory(enabled=plasticity_enabled)

        self.v_mv = np.full(self.n_sub, self.V_REST, dtype=np.float32)
        self.g_syn = np.zeros(self.n_sub, dtype=np.float32)
        self.r_rate = np.zeros(self.n_sub, dtype=np.float32)
        self._casting_phase: float = 0.0
        self._avoid_cooldown_s: float = 0.0
        self.total_spikes: int = 0
        self.telemetry_history: List[NeuralTelemetryStep] = []

    def reset_state(self, reset_memory: bool = True) -> None:
        self.v_mv.fill(self.V_REST)
        self.g_syn.fill(0.0)
        self.r_rate.fill(0.0)
        self._casting_phase = 0.0
        self._avoid_cooldown_s = 0.0
        self.total_spikes = 0
        self.telemetry_history.clear()
        if reset_memory:
            self.memory.reset()

    def _pool_mean(self, pname: str, side: str = "all") -> float:
        idx = self.sub.local_pools[pname][side]
        if len(idx) == 0:
            return 0.0
        return float(self.r_rate[idx].mean())

    @staticmethod
    def run_full_brain_spike_propagation_check(conn: FlyWireConnectome, n_steps: int = 20) -> Dict[str, object]:
        """
        Führt echte Spike-/Ratenpropagation auf ALLEN 138.639 Neuronen & 15.091.983 Kanten von W_full aus,
        um ganzhirnweite FlyWire-Ausführbarkeit auf 8 GB RAM nachzuweisen.
        """
        n = conn.n_neurons
        v = np.full(n, -52.0, dtype=np.float32)
        r = np.zeros(n, dtype=np.float32)
        i_ext = np.zeros(n, dtype=np.float32)

        ester_idx = conn.pool_indices("orn_ester")
        vision_idx = conn.pool_indices("vision_spectral")
        dn_idx = conn.pool_indices("dn_forward")
        steer_idx = conn.pool_indices("dn_steer")
        kc_idx = conn.pool_indices("kc")

        i_ext[ester_idx] = 18.0
        i_ext[vision_idx] = 12.0
        spikes_total = 0
        dn_peaks = 0.0
        kc_peaks = 0.0
        dt = np.float32(0.002)
        decay_m = np.float32(math.exp(-0.002 / 0.020))

        w = conn.w_full
        for _ in range(n_steps):
            i_syn = (w @ r) * np.float32(0.045)
            dv = (np.float32(-52.0) - v + i_ext + i_syn) * (dt / np.float32(0.020))
            v = np.clip(v * decay_m + (1.0 - decay_m) * (np.float32(-52.0) + i_ext + i_syn), -70.0, -35.0)
            spiked = v >= -45.0
            spikes_total += int(spiked.sum())
            v[spiked] = -52.0
            r = np.clip((v + 52.0) / 14.0 + 0.35 * spiked, 0.0, 1.0).astype(np.float32)
            dn_peaks = max(dn_peaks, float(r[np.concatenate([dn_idx, steer_idx])].mean()))
            kc_peaks = max(kc_peaks, float(r[kc_idx].mean()))

        return {
            "n_neurons_full_brain": n,
            "n_edges_full_brain": int(w.nnz),
            "n_steps_2ms": n_steps,
            "total_spikes_138k": spikes_total,
            "peak_kc_rate": round(kc_peaks, 4),
            "peak_dn_rate": round(dn_peaks, 4),
        }

    def step(
        self,
        sensor: SensorInputVector,
        fly_energy_mj: float,
        fly_hydration_pct: float,
        dt_s: float = 0.010,
    ) -> MotorOutputVector:
        """
        10 ms sensorimotorischer Schritt über das echte FlyWire-v783-Subnetzwerk (5 x 2 ms Substeps)
        + Kurzzeitplastizität im Pilzkörper (KC x DAN -> MBON).
        """
        lp = self.sub.local_pools
        hunger_drive = float(np.clip(1.35 - 0.04 * fly_energy_mj, 0.45, 1.85))
        thirst_drive = float(np.clip((68.0 - fly_hydration_pct) / 28.0, 0.10, 2.20))

        # 1. Bilateraler Sensor-Input -> Weber-Fechner logarithmische ORN-Transduktion (3+ Dekaden Dynamik)
        def _hill_orn(raw: float, k_half: float = 0.04, gain: float = 2.6) -> float:
            if raw <= 0.0:
                return 0.0
            return gain * math.log1p(raw / k_half) / math.log1p(12.0 / k_half)

        def odor_attr(c: np.ndarray, dcdt: np.ndarray) -> float:
            raw = float(0.45 * c[0] + 0.75 * c[1] + 1.00 * c[2])
            est = _hill_orn(raw, k_half=0.015, gain=3.2)
            terp_mod = _hill_orn(float(c[3]), k_half=0.25, gain=0.8)  # Terpene/Limonen dämpfen Attraktivität leicht
            phasic = _hill_orn(float(max(0.0, 0.4 * dcdt[0] + 0.7 * dcdt[1] + dcdt[2])), k_half=0.05, gain=0.9)
            return max(0.0, (est - 0.35 * terp_mod + phasic) * hunger_drive * self.olfaction_gain)

        attr_l = odor_attr(sensor.olfaction_conc_left, sensor.olfaction_dcdt_left)
        attr_r = odor_attr(sensor.olfaction_conc_right, sensor.olfaction_dcdt_right)
        geo_l = _hill_orn(float(sensor.olfaction_conc_left[4]), k_half=0.08, gain=2.8) * self.olfaction_gain * self.da2_geosmin_gain
        geo_r = _hill_orn(float(sensor.olfaction_conc_right[4]), k_half=0.08, gain=2.8) * self.olfaction_gain * self.da2_geosmin_gain
        terp_l = _hill_orn(float(sensor.olfaction_conc_left[3]), k_half=0.15, gain=2.2) * self.olfaction_gain
        terp_r = _hill_orn(float(sensor.olfaction_conc_right[3]), k_half=0.15, gain=2.2) * self.olfaction_gain
        co2_m = max(0.0, 0.5 * float(sensor.olfaction_conc_left[5] + sensor.olfaction_conc_right[5]) - 1.2) * self.olfaction_gain

        hum_l = (max(0.0, sensor.humidity_local_pct - 52.0) * 0.04 + 2.2 * float(sensor.olfaction_conc_left[7])) * thirst_drive
        hum_r = (max(0.0, sensor.humidity_local_pct - 52.0) * 0.04 + 2.2 * float(sensor.olfaction_conc_right[7])) * thirst_drive
        heat_sig = max(0.0, sensor.temp_local_c - 25.2) * 3.5

        vis_l = float(0.55 * sensor.vision_spectral_left[0] + 0.30 * sensor.vision_spectral_left[1] + 0.15 * sensor.vision_spectral_left[2]) * self.vision_gain
        vis_r = float(0.55 * sensor.vision_spectral_right[0] + 0.30 * sensor.vision_spectral_right[1] + 0.15 * sensor.vision_spectral_right[2]) * self.vision_gain
        loom_f = float(sensor.optical_flow_looming[0]) * self.looming_gain
        loom_l = float(sensor.optical_flow_looming[1] + 0.35 * loom_f) * self.looming_gain
        loom_r = float(sensor.optical_flow_looming[2] + 0.35 * loom_f) * self.looming_gain

        sugar_sig = float(sensor.gustation_contact[0] * 14.0 + sensor.gustation_contact[2] * 4.5 * thirst_drive) if sensor.is_landed else 0.0
        bitter_sig = float(sensor.gustation_contact[3] * 18.0 + sensor.gustation_contact[1] * 2.5) if sensor.is_landed else 0.0

        i_ext = np.zeros(self.n_sub, dtype=np.float32)
        i_ext[lp["orn_ester"]["left"]] = 4.5 * attr_l
        i_ext[lp["orn_ester"]["right"]] = 4.5 * attr_r
        i_ext[lp["orn_terpene"]["left"]] = 4.2 * terp_l
        i_ext[lp["orn_terpene"]["right"]] = 4.2 * terp_r
        i_ext[lp["orn_geosmin"]["left"]] = 7.5 * geo_l
        i_ext[lp["orn_geosmin"]["right"]] = 7.5 * geo_r
        i_ext[lp["orn_co2"]["all"]] = 4.0 * co2_m
        i_ext[lp["hrn"]["left"]] = 3.2 * hum_l
        i_ext[lp["hrn"]["right"]] = 3.2 * hum_r
        i_ext[lp["trn"]["all"]] = 4.5 * heat_sig
        i_ext[lp["vision_spectral"]["left"]] = 5.5 * vis_l
        i_ext[lp["vision_spectral"]["right"]] = 5.5 * vis_r
        i_ext[lp["looming"]["left"]] = 6.0 * loom_l
        i_ext[lp["looming"]["right"]] = 6.0 * loom_r
        i_ext[lp["jo_mechano"]["all"]] = 2.8 * float(np.linalg.norm(sensor.wind_local_body))
        i_ext[lp["grn_sugar"]["all"]] = sugar_sig
        i_ext[lp["grn_bitter"]["all"]] = bitter_sig
        # Direkte DAN-Teaching-Signale bei Geschmacks-/Geosmin-Kontakt
        if bitter_sig > 1.5 or (geo_l + geo_r) > 2.2:
            i_ext[lp["dan_punish"]["all"]] += 9.5
        if sugar_sig > 2.5:
            i_ext[lp["dan_reward"]["all"]] += 8.5

        # 2. 5 x 2 ms LIF-Substeps auf den echten FlyWire-W_sub-Synapsen
        n_substeps = 5
        dt_sub = np.float32(dt_s / n_substeps)
        decay_m = np.float32(math.exp(-float(dt_sub) / self.TAU_M_S))
        w = self.sub.w_sub
        step_spikes = 0

        for _ in range(n_substeps):
            i_syn = (w @ self.r_rate) * np.float32(0.055)
            target_v = np.float32(self.V_REST) + i_ext + i_syn
            self.v_mv = np.clip(self.v_mv * decay_m + (1.0 - decay_m) * target_v, -72.0, -34.0)
            spiked = self.v_mv >= self.V_THRESH
            step_spikes += int(spiked.sum())
            self.v_mv[spiked] = self.V_REST
            self.r_rate = np.clip((self.v_mv - self.V_REST) / 11.0 + 0.30 * spiked, 0.0, 1.0).astype(np.float32)

        self.total_spikes += step_spikes

        # 3. Populationsraten aus realem Subnetzwerk + Pilzkörper-Kurzzeitplastizität (Modul E)
        r_ester_l = self._pool_mean("orn_ester", "left") + 0.5 * self._pool_mean("pn_ester", "left")
        r_ester_r = self._pool_mean("orn_ester", "right") + 0.5 * self._pool_mean("pn_ester", "right")
        r_geo_l = self._pool_mean("orn_geosmin", "left") + 0.7 * self._pool_mean("pn_geosmin", "left")
        r_geo_r = self._pool_mean("orn_geosmin", "right") + 0.7 * self._pool_mean("pn_geosmin", "right")
        r_vis_l = self._pool_mean("vision_spectral", "left")
        r_vis_r = self._pool_mean("vision_spectral", "right")
        r_loom_l = self._pool_mean("looming", "left")
        r_loom_r = self._pool_mean("looming", "right")
        r_kc = self._pool_mean("kc")
        r_pam = self._pool_mean("dan_reward")
        r_ppl1 = self._pool_mean("dan_punish")
        dn_steer_net = self._pool_mean("dn_steer", "left") - self._pool_mean("dn_steer", "right")
        dn_fwd_net = self._pool_mean("dn_forward")
        dn_back_net = self._pool_mean("dn_backward")
        dn_jump_net = self._pool_mean("dn_jump")
        mbon_diff = self._pool_mean("mbon_gaba_glut") - self._pool_mean("mbon_ach")

        odor_feat = np.array(
            [
                0.5 * (attr_l + attr_r),
                0.5 * (terp_l + terp_r),
                0.5 * (geo_l + geo_r),
            ],
            dtype=np.float32,
        )
        mb_shift = self.memory.step(odor_feat, max(r_kc, 0.08 * odor_feat.sum()), r_pam, r_ppl1, dt_s)
        ester_valence = float(1.0 + mb_shift[0])  # positiv = Annäherung, negativ = gelernte Aversion!

        # 4. Absteigende Dekodierung -> MotorOutputVector [MODEL_ASSUMPTION]
        # Stereo-Chemotaxis (ORN + PNs + direkte Antennenasymmetrie & zeitliche dC/dt-Klinokinese)
        self._casting_phase = (self._casting_phase + 2.8 * dt_s) % (2.0 * math.pi)
        raw_ester_l = float(sensor.olfaction_conc_left[1] + sensor.olfaction_conc_left[2])
        raw_ester_r = float(sensor.olfaction_conc_right[1] + sensor.olfaction_conc_right[2])
        raw_ester_mean = 0.5 * (raw_ester_l + raw_ester_r)
        raw_dcdt = 0.5 * float(sensor.olfaction_dcdt_left[1] + sensor.olfaction_dcdt_left[2] + sensor.olfaction_dcdt_right[1] + sensor.olfaction_dcdt_right[2])
        raw_grad_lr = (raw_ester_l - raw_ester_r) / max(0.05, raw_ester_mean)
        chem_asym = (8.5 * (r_ester_l - r_ester_r) + 3.2 * raw_grad_lr) * ester_valence
        chem_mean = 0.5 * (r_ester_l + r_ester_r)
        klino_turn = 2.8 * math.sin(self._casting_phase) if (self.olfaction_gain > 0.0 and raw_ester_mean > 0.05 and raw_dcdt < -0.05) else 0.0

        # Hygrotaxis (HRN L/R) & Geosmin-Aversion (DA2): Geosmin dominiert bei normaler Hydrierung über Wasser
        r_hrn_l = self._pool_mean("hrn", "left")
        r_hrn_r = self._pool_mean("hrn", "right")
        hygro_asym = 3.5 * (r_hrn_l - r_hrn_r) * thirst_drive
        geo_asym = (r_geo_r - r_geo_l) * 3.5
        geo_mean = 0.5 * (r_geo_l + r_geo_r)
        geo_repel_active = (geo_mean > 0.14 or 0.5 * (geo_l + geo_r) > 0.30) and self.da2_geosmin_gain > 0.0
        geo_urgency = 4.6 if geo_repel_active else 0.0
        net_water_vs_geo = thirst_drive * 0.45 - geo_mean * 1.8

        # Phototaxis über MeTu L/R: bei starkem Futterduft (Hunger) oder Geosmin-Flucht stark gedämpft!
        odor_photo_gate = 1.0 / ((1.0 + 3.5 * chem_mean + 2.5 * raw_ester_mean) ** 2)
        if geo_repel_active:
            odor_photo_gate = 0.05
        photo_yaw = (1.6 * (r_vis_l - r_vis_r) + 0.65 * float(sensor.light_dir_body[1]) * self.vision_gain) * odor_photo_gate

        # Hindernisvermeidung über LC4/LPLC2 L/R
        loom_yaw = 3.8 * (r_loom_r - r_loom_l) + 1.4 * float(sensor.optical_flow_looming[2] - sensor.optical_flow_looming[1]) * self.looming_gain
        front_wall_danger = float(sensor.optical_flow_looming[0]) * self.looming_gain > 0.72

        # Anemotaxis (Johnston-Organ): gegen Aufwind/Duftwind eindrehen wenn Duft vorhanden
        wind_yaw = 0.0
        wind_lat = float(sensor.wind_local_body[1])
        if chem_mean > 0.08 and self.olfaction_gain > 0.0:
            wind_yaw = 1.2 * wind_lat

        search_cast = 0.75 * math.sin(self._casting_phase) if (chem_mean < 0.12 and self.da2_geosmin_gain > 0.0 and thirst_drive < 1.2) else 0.15 * math.sin(self._casting_phase)

        tau_yaw = float(
            chem_asym
            + klino_turn
            + hygro_asym
            + geo_asym
            + geo_urgency
            + photo_yaw
            + loom_yaw
            + wind_yaw
            + 2.2 * dn_steer_net
            + 0.4 * mbon_diff
            + search_cast
        )
        if front_wall_danger:
            side_sign = 1.0 if sensor.optical_flow_looming[1] <= sensor.optical_flow_looming[2] else -1.0
            tau_yaw += side_sign * 4.2

        # Vertikale Flugsteuerung (Schubkraft F_thrust) + Treppenhaus-Abstieg im aufsteigenden Küchenplume
        z_up_loom = float(sensor.optical_flow_looming[3]) * self.looming_gain
        z_dn_loom = float(sensor.optical_flow_looming[4]) * self.looming_gain
        f_thrust = 1.005 + 0.12 * dn_fwd_net - 0.10 * z_up_loom + 0.14 * z_dn_loom
        if sensor.temp_local_c > 25.4:
            tau_yaw += 2.6
        ester_raw_mean = raw_ester_mean
        if chem_mean > 0.05 and float(sensor.wind_local_body[2]) > 0.04 and ester_valence > 0.15 and ester_raw_mean < 0.85:
            f_thrust -= 0.14
        elif chem_mean > 0.22 and ester_valence > 0.15 and self.olfaction_gain > 0.0 and ester_raw_mean < 0.95:
            f_thrust -= 0.065
        attractive_food_near = (ester_raw_mean > 1.05 and ester_valence > 0.10 and net_water_vs_geo > -0.45)
        wants_water_risk = (thirst_drive > 1.25 and sensor.humidity_local_pct > 72.0 and not geo_repel_active)
        request_landing = bool((attractive_food_near or wants_water_risk) and self.olfaction_gain > 0.0)
        if request_landing and not sensor.is_landed:
            f_thrust = 0.78

        # Vorwärtsneigung; bei Frontgefahr oder DA2-Geosmin-Kontaktwarnung aktiv abbremsen!
        tau_pitch = 0.12 + 0.08 * dn_fwd_net - 0.28 * dn_back_net - (0.35 if front_wall_danger else 0.0) - (0.38 if geo_repel_active else 0.0)

        # Rüssel-Extension strikt bei gelandetem Kontakt & positiver Valenz (nicht bei bitter / DA2-Geosmin)
        bitter_contact = float(sensor.gustation_contact[3]) > 0.25 if sensor.is_landed else False
        sugar_or_water = float(sensor.gustation_contact[0] + 0.5 * sensor.gustation_contact[2]) > 0.30 if sensor.is_landed else False
        proboscis_ext = bool(
            sensor.is_landed
            and sugar_or_water
            and not bitter_contact
            and ester_valence > -0.05
            and not geo_repel_active
        )

        # Absprung von Oberfläche, falls bitter, Geosmin-aversiv, oder gelernter negativer MB-Wert!
        trigger_jump = bool(
            sensor.is_landed
            and (
                bitter_contact
                or (ester_valence < -0.10 and sensor.contact_food_id is not None)
                or (geo_repel_active and sensor.contact_food_id == "FOOD_09")
                or dn_jump_net > 0.65
            )
        )

        # Im gelandeten Zustand auf Oberflächen (ohne Nahrungskontakt) entlang Geruchsgradient zum Substrat laufen
        walk_fwd = 0.032 if (sensor.is_landed and not proboscis_ext) else 0.0
        walk_turn = float(np.clip(tau_yaw * 0.85, -3.2, 3.2)) if sensor.is_landed else 0.0

        self.telemetry_history.append(
            NeuralTelemetryStep(
                mean_orn_ester=0.5 * (r_ester_l + r_ester_r),
                mean_orn_da2_geosmin=0.5 * (r_geo_l + r_geo_r),
                mean_vision_metu=0.5 * (r_vis_l + r_vis_r),
                mean_looming_lc4=0.5 * (r_loom_l + r_loom_r),
                mean_kc=r_kc,
                mean_pam=r_pam,
                mean_ppl1=r_ppl1,
                mean_dn_steer_diff=dn_steer_net,
                mean_dn_forward=dn_fwd_net,
                mean_dn_jump=dn_jump_net,
                mb_ester_valence=ester_valence,
                total_spikes_step=step_spikes,
            )
        )

        return MotorOutputVector(
            f_thrust_norm=float(np.clip(f_thrust, 0.45, 1.55)),
            tau_pitch=float(np.clip(tau_pitch, -0.45, 0.45)),
            tau_roll=0.0,
            tau_yaw=float(np.clip(tau_yaw, -6.5, 6.5)),
            walk_forward_mps=walk_fwd,
            walk_turn_rad_s=walk_turn,
            trigger_jump=trigger_jump,
            proboscis_extension=proboscis_ext,
            request_landing=request_landing,
  )
