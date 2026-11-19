# -*- coding: utf-8 -*-
"""
Thread-sichere Echtzeit- & Time-Travel-Observatorium-Engine für SIMALITÄT.

Koppelt Seestrasse43EcosystemWorld, FlyWire-v783-Fliegenpopulation,
3 GBIF-Vogelarten sowie EnvironmentDynamics (Wetter/Hydrologie/Pflanzen/Insekten)
mit kausaler Ereignisverfolgung und Vorher-Nachher-Vergleichen.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

from ..connectome import FlyWireConnectome
from ..security_guards import FlyLabSecurityGuard, get_process_rss_mb
from .bird_models import BirdAgent
from .causal_tracker import CausalTracker, ObservatoryTimeline
from .ecosystem_world import Seestrasse43EcosystemWorld
from .environment_dynamics import EnvironmentDynamics, SEASON_PRESETS
from .fly_population import (
    FlyEcosystemSubcircuit,
    FlyPopulationEngine,
    build_ecosystem_flywire_subcircuit,
)
from .simulation import _create_birds


class ObservatoryEngine:
    """Zentrale Simulations- und Abfrage-Engine des interaktiven Ökosystem-Observatoriums."""

    MAX_DURATION_S: float = 120.0
    DT_S: float = 0.025

    def __init__(
        self,
        scenario: str = "REGENZYKLUS",
        season: str = "SOMMER",
        seed: int = 42,
        guard: Optional[FlyLabSecurityGuard] = None,
        conn: Optional[FlyWireConnectome] = None,
        subcircuit: Optional[FlyEcosystemSubcircuit] = None,
    ) -> None:
        self._lock = threading.RLock()
        self.guard = guard or FlyLabSecurityGuard()
        self.world = Seestrasse43EcosystemWorld(guard=self.guard)
        self.conn = conn or FlyWireConnectome()
        self.subcircuit = subcircuit or build_ecosystem_flywire_subcircuit(self.conn)

        self.scenario = scenario.upper()
        self.season = season.upper() if season.upper() in SEASON_PRESETS else "SOMMER"
        self.seed = int(seed)

        self.env = EnvironmentDynamics(self.world, scenario=self.scenario, season=self.season, seed=self.seed)
        self.fly_pop = FlyPopulationEngine(sub=self.subcircuit, max_slots=72, seed=self.seed, looming_gain=1.0)
        self.birds: List[BirdAgent] = []
        self.tracker = CausalTracker()
        self.timeline = ObservatoryTimeline()

        self.tick_count: int = 0
        self.running: bool = False
        self.auto_stop_at_s: Optional[float] = None
        self._stop_flag: bool = False
        self._bg_thread: Optional[threading.Thread] = None
        self.last_tick_ms: float = 0.0
        self.ema_tick_ms: float = 12.0
        self._compare_running: bool = False
        self._cached_dry_comparison: Optional[Dict[str, Any]] = None

        self.reset(scenario=self.scenario, season=self.season, seed=self.seed)

    def reset(
        self,
        scenario: Optional[str] = None,
        season: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> None:
        with self._lock:
            self.running = False
            self.auto_stop_at_s = None
            if scenario is not None:
                self.scenario = scenario.upper()
            if season is not None and season.upper() in SEASON_PRESETS:
                self.season = season.upper()
            if seed is not None:
                self.seed = int(seed)
            self._compare_running = False
            self._cached_dry_comparison = None

            self.world.reset_dynamic_state()
            self.env.reset(self.world, scenario=self.scenario, season=self.season, seed=self.seed)
            self.fly_pop = FlyPopulationEngine(sub=self.subcircuit, max_slots=72, seed=self.seed, looming_gain=1.0)
            self.fly_pop.seed_initial_population(self.world, n_flies=34)
            self.birds = _create_birds(vision_gain=1.0)
            self.tracker.reset()
            self.timeline.clear()
            self.tick_count = 0

            # t = 0.0 s Initialzustand erfassen
            zones0 = self.env.hydro.summarize_zones()
            self.tracker.observe_step(
                0.0,
                self.env.weather_engine.current,
                zones0,
                self.env.vegetation.plants,
                self.world.substrates,
                self.env.other_insects.insects,
                self.fly_pop.zone_distribution(self.world),
                self.birds,
                [],
            )
            self.timeline.record_frame(
                0.0,
                self.env.weather_engine.current,
                self.env.hydro,
                zones0,
                self.env.vegetation.plants,
                self.world.substrates,
                self.fly_pop,
                self.env.other_insects.insects,
                self.birds,
                self.world,
                self.tracker,
            )

    def step_one_tick(self) -> None:
        with self._lock:
            limit_s = self.auto_stop_at_s if self.auto_stop_at_s is not None else self.MAX_DURATION_S
            if self.world.sim_time_s >= limit_s - 1e-6:
                self.running = False
                self.auto_stop_at_s = None
                return
            t0 = time.perf_counter()
            dt = self.DT_S
            self.world.step(dt)
            weather = self.env.step(self.world, dt)
            self.tick_count += 1

            slots = self.fly_pop.alive_slots()
            b_pos = np.array([b.pos for b in self.birds], dtype=np.float64) if self.birds else np.zeros((0, 3), dtype=np.float64)
            los_mat = (
                self.world.compute_los_matrix(self.fly_pop.pos[slots], b_pos)
                if (len(slots) and len(self.birds))
                else np.zeros((len(slots), len(self.birds)), dtype=np.float32)
            )
            fly_canopy = (
                self.world.max_canopy_density_vec(self.fly_pop.pos[slots])
                if len(slots)
                else np.zeros(0, dtype=np.float32)
            )
            bird_states = [
                {
                    "bird_id": b.bird_id,
                    "species_id": b.profile.species_id,
                    "pos": b.pos,
                    "vel": b.vel,
                    "wingspan_m": b.profile.wingspan_m,
                }
                for b in self.birds
            ]
            self.fly_pop.step(self.world, bird_states, dt_s=dt, los_matrix=los_mat, fly_canopy_vec=fly_canopy)

            slots_after = self.fly_pop.alive_slots()
            if len(slots_after) != len(slots) or not np.array_equal(slots_after, slots):
                los_mat = (
                    self.world.compute_los_matrix(self.fly_pop.pos[slots_after], b_pos)
                    if (len(slots_after) and len(self.birds))
                    else np.zeros((len(slots_after), len(self.birds)), dtype=np.float32)
                )
                fly_canopy = (
                    self.world.max_canopy_density_vec(self.fly_pop.pos[slots_after])
                    if len(slots_after)
                    else np.zeros(0, dtype=np.float32)
                )

            bird_events: List[Dict[str, Any]] = []
            for bi, b in enumerate(self.birds):
                ev = b.step(
                    self.world,
                    self.fly_pop,
                    dt_s=dt,
                    alive_slots=slots_after,
                    los_vec=los_mat[:, bi] if len(slots_after) else np.zeros(0, dtype=np.float32),
                    fly_canopy_vec=fly_canopy,
                )
                if ev["catch"] or ev["miss"]:
                    ev["bird_id"] = b.bird_id
                    ev["species_id"] = b.profile.species_id
                    bird_events.append(ev)

            if self.tick_count % 20 == 0:  # alle 0,5 s Kausalprüfung
                zones = self.env.hydro.summarize_zones()
                fz = self.fly_pop.zone_distribution(self.world)
                self.tracker.observe_step(
                    self.world.sim_time_s,
                    weather,
                    zones,
                    self.env.vegetation.plants,
                    self.world.substrates,
                    self.env.other_insects.insects,
                    fz,
                    self.birds,
                    bird_events,
                )
            elif bird_events:
                # Sofortige Dokumentation realer CPA-Fänge zwischen 0,5-s-Prüfungen
                zones = self.env.hydro.summarize_zones()
                fz = self.fly_pop.zone_distribution(self.world)
                self.tracker.observe_step(
                    self.world.sim_time_s,
                    weather,
                    zones,
                    self.env.vegetation.plants,
                    self.world.substrates,
                    self.env.other_insects.insects,
                    fz,
                    self.birds,
                    bird_events,
                )

            if self.tick_count % 40 == 0:  # alle 1,0 s Timeline-Frame
                zones = self.env.hydro.summarize_zones()
                self.timeline.record_frame(
                    self.world.sim_time_s,
                    weather,
                    self.env.hydro,
                    zones,
                    self.env.vegetation.plants,
                    self.world.substrates,
                    self.fly_pop,
                    self.env.other_insects.insects,
                    self.birds,
                    self.world,
                    self.tracker,
                )

            dt_ms = 1000.0 * (time.perf_counter() - t0)
            self.last_tick_ms = round(dt_ms, 2)
            self.ema_tick_ms = round(0.88 * self.ema_tick_ms + 0.12 * dt_ms, 2)

    def run_for_seconds(self, seconds: float) -> None:
        steps = max(1, int(round(seconds / self.DT_S)))
        for _ in range(steps):
            if self.world.sim_time_s >= self.MAX_DURATION_S:
                break
            self.step_one_tick()

    def run_until(self, target_t_s: float) -> None:
        target = min(self.MAX_DURATION_S, float(target_t_s))
        while self.world.sim_time_s < target - 1e-6:
            self.step_one_tick()

    def _bg_loop(self) -> None:
        while not self._stop_flag:
            if self.running:
                self.step_one_tick()
                time.sleep(0.001)
            else:
                time.sleep(0.05)

    def ensure_bg_thread(self) -> None:
        if self._bg_thread is None or not self._bg_thread.is_alive():
            self._stop_flag = False
            self._bg_thread = threading.Thread(target=self._bg_loop, name="ObservatorySimThread", daemon=True)
            self._bg_thread.start()

    def start_background(self) -> None:
        self.ensure_bg_thread()
        with self._lock:
            self.auto_stop_at_s = None
            self.running = True

    def start_cycle_async(self, target_t_s: float = 90.0) -> None:
        self.ensure_bg_thread()
        with self._lock:
            target = min(self.MAX_DURATION_S, float(target_t_s))
            if self.world.sim_time_s < target - 1e-6:
                self.auto_stop_at_s = target
                self.running = True
            else:
                self.auto_stop_at_s = None
                self.running = False

    def pause_background(self) -> None:
        with self._lock:
            self.running = False
            self.auto_stop_at_s = None

    def stop_background(self) -> None:
        self._stop_flag = True
        with self._lock:
            self.running = False

    def compute_state_sha256(self) -> str:
        with self._lock:
            slots = self.fly_pop.alive_slots()
            payload = {
                "t_s": round(float(self.world.sim_time_s), 4),
                "weather": asdict(self.env.weather_engine.current),
                "moisture": np.round(self.env.hydro.moisture_frac, 4).tolist(),
                "puddle": np.round(self.env.hydro.puddle_mm, 4).tolist(),
                "plants": [(p.plant_id, p.foliage_wetness, p.turgor_index, p.nectar_mg) for p in self.env.vegetation.plants],
                "other_insects": [(i.insect_id, i.pos, i.state) for i in self.env.other_insects.insects],
                "fly_pos": np.round(self.fly_pop.pos[slots], 4).tolist(),
                "fly_energy": np.round(self.fly_pop.energy_mj[slots], 4).tolist(),
                "birds": [(b.bird_id, np.round(b.pos, 4).tolist(), round(b.energy_j, 4), b.catches, b.missed_strikes) for b in self.birds],
            }
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return hashlib.sha256(raw).hexdigest()

    def get_meta(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "world_bounds": {"min": list(self.world.BOUNDS_MIN), "max": list(self.world.BOUNDS_MAX)},
                "house_main": [list(self.world.HOUSE_BOX_MAIN[0][:2]), list(self.world.HOUSE_BOX_MAIN[1][:2])],
                "house_annex": [list(self.world.HOUSE_BOX_ANNEX[0][:2]), list(self.world.HOUSE_BOX_ANNEX[1][:2])],
                "house_portal": list(self.world.HOUSE_FLY_PORTAL_CENTER),
                "grid": {
                    "nx": self.env.hydro.NX,
                    "ny": self.env.hydro.NY,
                    "cell_size_m": self.env.hydro.CELL_SIZE_M,
                    "x_min": self.env.hydro.x_min,
                    "y_min": self.env.hydro.y_min,
                    "elevation_m": np.round(self.env.hydro.elevation_m, 2).tolist(),
                    "roof_mask": self.env.hydro.roof_mask.astype(int).tolist(),
                },
                "canopies": [asdict(c) for c in self.world.canopies],
                "perches": [asdict(p) for p in self.world.perches],
                "woelfersheim_anchor": self.world.woelfersheim_anchor,
                "gbif_birds": self.world.gbif_bird_records,
                "gbif_extended": self.world.gbif_extended_records,
                "dwd_weather_reference": self.world.dwd_weather_reference,
                "flywire_subcircuit": {"n_neurons": self.subcircuit.n_neurons, "n_edges": self.subcircuit.n_edges},
                "scenarios": ["REGENZYKLUS", "TROCKEN_KONTROLLE", "STARKREGEN"],
                "seasons": list(SEASON_PRESETS.keys()),
                "max_duration_s": self.MAX_DURATION_S,
            }

    def get_state_payload(self, t_s: Optional[float] = None) -> Dict[str, Any]:
        with self._lock:
            frame = self.timeline.get_frame(t_s)
            t_cur = frame["t_s"] if frame else 0.0
            events_up_to = [asdict(e) for e in self.tracker.events if e.sim_time_s <= t_cur + 1e-6]
            return {
                "running": self.running,
                "auto_stop_at_s": self.auto_stop_at_s,
                "compare_running": self._compare_running,
                "dry_comparison": self._cached_dry_comparison,
                "live_sim_time_s": round(float(self.world.sim_time_s), 2),
                "available_times_s": [f["t_s"] for f in self.timeline.frames],
                "scenario": self.scenario,
                "season": self.season,
                "seed": self.seed,
                "ms_per_tick": self.ema_tick_ms,
                "rss_mb": round(get_process_rss_mb(), 2),
                "state_sha256": self.compute_state_sha256(),
                "frame": frame,
                "events": events_up_to,
                "total_events_logged": len(self.tracker.events),
            }

    def get_object_detail(self, entity_id: str, t_s: Optional[float] = None) -> Dict[str, Any]:
        with self._lock:
            frame = self.timeline.get_frame(t_s)
            if frame is None:
                return {"error": "Kein Frame verfügbar"}
            t_cur = frame["t_s"]
            frames_upto = [f for f in self.timeline.frames if f["t_s"] <= t_cur + 1e-6]
            times = [f["t_s"] for f in frames_upto]

            detail: Dict[str, Any] = {
                "entity_id": entity_id,
                "t_s": t_cur,
                "label_de": entity_id,
                "category": "UNBEKANNT",
                "data_origin": "MODELLWERT",
                "reference_note": "",
                "metrics": [],
                "series": {"times": times, "values": [], "label": "", "unit": ""},
                "events": [],
            }

            if entity_id in frame["soil_zones"]:
                z = frame["soil_zones"][entity_id]
                detail["label_de"] = z["label_de"]
                detail["category"] = "Bodenfläche (Hydrologie)"
                detail["data_origin"] = "MODELLWERT"
                detail["reference_note"] = "18x18-Hydrologie-Zellmittel über Mikro-Topographie & Infiltration"
                detail["metrics"] = [
                    {"name": "Bodenfeuchte", "value": z["soil_moisture_pct"], "unit": "% Vol.", "origin": "MODELLWERT"},
                    {"name": "Pfützentiefe", "value": z["puddle_depth_mm"], "unit": "mm", "origin": "MODELLWERT"},
                    {"name": "Wasserfluss", "value": z["flow_speed_cms"], "unit": "cm/s", "origin": "MODELLWERT"},
                    {"name": "Infiltration", "value": z["infiltration_mm_h"], "unit": "mm/h", "origin": "MODELLWERT"},
                    {"name": "Innenraum-Schutz", "value": "Ja (Dach)" if z["is_indoor"] else "Nein (Freiland)", "unit": "", "origin": "MODELLWERT"},
                ]
                detail["series"] = {
                    "times": times,
                    "values": [f["soil_zones"][entity_id]["soil_moisture_pct"] for f in frames_upto],
                    "label": "Bodenfeuchte",
                    "unit": "% Vol.",
                }
            elif entity_id in frame["plants"]:
                p = frame["plants"][entity_id]
                detail["label_de"] = p["label_de"]
                detail["category"] = "Pflanze (Vegetation)"
                detail["data_origin"] = "GBIF_REFERENZ + MODELLWERT" if p["gbif_occ_ref"] > 0 else "MODELLWERT"
                detail["reference_note"] = f"Botanische Referenz: {p['species_ref']} (Wölfersheim GBIF n={p['gbif_occ_ref']})"
                detail["metrics"] = [
                    {"name": "Blattnässe", "value": p["foliage_wetness"], "unit": "Index [0..1]", "origin": "MODELLWERT"},
                    {"name": "Zell-Turgor (verzögert)", "value": p["turgor_index"], "unit": "Index [0..1]", "origin": "MODELLWERT"},
                    {"name": "Vitalität / Grünfrische", "value": p["lushness_index"], "unit": "Index [0..1]", "origin": "MODELLWERT"},
                    {"name": "Nektarvorrat", "value": p["nectar_mg"], "unit": "mg", "origin": "MODELLWERT"},
                    {"name": "Stomata-Leitfähigkeit", "value": p["stomatal_conductance"], "unit": "Index [0..1]", "origin": "MODELLWERT"},
                    {"name": "Lokale Bodenfeuchte", "value": p["local_soil_moisture_pct"], "unit": "% Vol.", "origin": "MODELLWERT"},
                ]
                detail["series"] = {
                    "times": times,
                    "values": [f["plants"][entity_id]["turgor_index"] for f in frames_upto],
                    "label": "Turgor-Index",
                    "unit": "Index [0..1]",
                }
            elif entity_id in frame["substrates"]:
                s = frame["substrates"][entity_id]
                detail["label_de"] = s["label_de"]
                detail["category"] = "Lebensraum / Nahrungssubstrat"
                detail["data_origin"] = "MODELLWERT"
                detail["reference_note"] = f"Gekoppelt an FlyWire-ORN-Chemotaxis (Zone: {s['zone']})"
                detail["metrics"] = [
                    {"name": "VOC-Duftstärke", "value": s["voc_strength"], "unit": "Relativ (Basis " + str(s["base_voc_strength"]) + ")", "origin": "MODELLWERT"},
                    {"name": "Nährstoffvorrat", "value": s["nutrients"], "unit": "mg", "origin": "MODELLWERT"},
                    {"name": "Regenerationsrate", "value": s["regen_per_s"], "unit": "mg/s", "origin": "MODELLWERT"},
                ]
                detail["series"] = {
                    "times": times,
                    "values": [f["substrates"][entity_id]["voc_strength"] for f in frames_upto],
                    "label": "VOC-Duftstärke",
                    "unit": "Relativ",
                }
            elif entity_id in frame["birds"]:
                b = frame["birds"][entity_id]
                gb = self.world.gbif_bird_records.get(b["scientific_name"], {})
                occ = gb.get("verified_occ_count", 0)
                detail["label_de"] = f"{b['common_name_de']} ({b['bird_id']})"
                detail["category"] = "Vogel (Prädator)"
                detail["data_origin"] = "GBIF_REFERENZ + MODELLWERT"
                detail["reference_note"] = f"{b['scientific_name']} (Taxon {b['gbif_occ_ref']}, Wölfersheim GBIF n={occ}, CC BY 4.0)"
                detail["metrics"] = [
                    {"name": "Verhalten", "value": b["state"], "unit": "", "origin": "MODELLWERT"},
                    {"name": "Geschwindigkeit", "value": b["speed_mps"], "unit": "m/s", "origin": "MODELLWERT"},
                    {"name": "Flughöhe Z", "value": b["pos"][2], "unit": "m", "origin": "MODELLWERT"},
                    {"name": "Energiespeicher", "value": b["energy_j"], "unit": f"J (Max {b['energy_max_j']} J)", "origin": "MODELLWERT"},
                    {"name": "CPA-Fänge", "value": b["catches"], "unit": "Stk", "origin": "MODELLWERT"},
                    {"name": "Fehlschläge", "value": b["missed_strikes"], "unit": "Stk", "origin": "MODELLWERT"},
                ]
                detail["series"] = {
                    "times": times,
                    "values": [f["birds"][entity_id]["energy_j"] for f in frames_upto],
                    "label": "Energie",
                    "unit": "J",
                }
            elif entity_id in frame["other_insects"]:
                ins = frame["other_insects"][entity_id]
                detail["label_de"] = f"{ins['label_de']} ({ins['species']})"
                detail["category"] = "Insekt (GBIF-Gilde)"
                detail["data_origin"] = "GBIF_REFERENZ + MODELLWERT"
                detail["reference_note"] = f"{ins['species']} (Wölfersheim GBIF n={ins['gbif_occ_ref']})"
                detail["metrics"] = [
                    {"name": "Zustand", "value": ins["state"], "unit": "", "origin": "MODELLWERT"},
                    {"name": "Aktivitätsindex", "value": ins["activity_index"], "unit": "[0..1]", "origin": "MODELLWERT"},
                    {"name": "Energie", "value": ins["energy_pct"], "unit": "%", "origin": "MODELLWERT"},
                    {"name": "Position (X, Y, Z)", "value": str(ins["pos"]), "unit": "m", "origin": "MODELLWERT"},
                ]
                detail["series"] = {
                    "times": times,
                    "values": [f["other_insects"][entity_id]["activity_index"] for f in frames_upto],
                    "label": "Aktivitätsindex",
                    "unit": "[0..1]",
                }
            elif entity_id.startswith("FLY_"):
                fl = next((x for x in frame["flies"] if x["id"] == entity_id), None)
                if fl is not None:
                    detail["label_de"] = f"Fruchtfliege #{fl['fly_num']} (Drosophila)"
                    detail["category"] = "Fruchtfliege (FlyWire v783)"
                    detail["data_origin"] = "FLYWIRE_V783 + MODELLWERT"
                    detail["reference_note"] = f"Gekoppelt an realen FlyWire-v783-Teilgraphen ({self.subcircuit.n_neurons}n / {self.subcircuit.n_edges}e)"
                    detail["metrics"] = [
                        {"name": "Verhalten", "value": fl["state"], "unit": "", "origin": "MODELLWERT"},
                        {"name": "Energie", "value": fl["energy_mj"], "unit": "mJ", "origin": "MODELLWERT"},
                        {"name": "Position (X, Y, Z)", "value": str(fl["pos"]), "unit": "m", "origin": "MODELLWERT"},
                        {"name": "ORN Ester (Feuerrate)", "value": fl["orn_ester"], "unit": "[0..1]", "origin": "FLYWIRE_V783"},
                        {"name": "LC4 Looming (Feuerrate)", "value": fl["lc4"], "unit": "[0..1]", "origin": "FLYWIRE_V783"},
                        {"name": "DNp01 Escape (Feuerrate)", "value": fl["dnp01"], "unit": "[0..1]", "origin": "FLYWIRE_V783"},
                        {"name": "Fluchtmanöver gesamt", "value": fl["escapes"], "unit": "Stk", "origin": "FLYWIRE_V783"},
                    ]
                    e_vals = []
                    for f in frames_upto:
                        hit = next((x["energy_mj"] for x in f["flies"] if x["id"] == entity_id), None)
                        e_vals.append(hit if hit is not None else (e_vals[-1] if e_vals else 0.0))
                    detail["series"] = {"times": times, "values": e_vals, "label": "Energie", "unit": "mJ"}

            # Zugehörige kausale Ereignisse (inkl. Gilden-Ereignisse)
            rel = []
            for e in self.tracker.events:
                if e.sim_time_s > t_cur + 1e-6:
                    continue
                if (
                    e.entity_id == entity_id
                    or (entity_id.startswith("BUMBLE_") and e.entity_id == "GUILD_BUMBLEBEE")
                    or (entity_id.startswith("BEETLE_") and e.entity_id == "GUILD_BEETLE")
                    or (entity_id.startswith("FLY_") and e.entity_id == "POP_DROSOPHILA")
                ):
                    rel.append(asdict(e))
            detail["events"] = rel
            return detail

    def get_diff(self, t1_s: float, t2_s: float, entity_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            return self.timeline.compute_diff(t1_s, t2_s, self.tracker, entity_id=entity_id)

    def get_causal_chain(self, event_id: str) -> Dict[str, Any]:
        with self._lock:
            return self.tracker.trace_chain(event_id)

    def compare_against_dry_control(self, duration_s: float = 90.0) -> Dict[str, Any]:
        """Führt einen isolierten, seed-identischen Trocken-Kontrolllauf durch und vergleicht direkt."""
        self.run_until(duration_s)
        with self._lock:
            wet_frame = self.timeline.get_frame(duration_s)
            wet_sha = self.compute_state_sha256()

        dry_eng = ObservatoryEngine(
            scenario="TROCKEN_KONTROLLE",
            season=self.season,
            seed=self.seed,
            guard=self.guard,
            conn=self.conn,
            subcircuit=self.subcircuit,
        )
        dry_eng.run_until(duration_s)
        dry_frame = dry_eng.timeline.get_frame(duration_s)
        dry_sha = dry_eng.compute_state_sha256()

        if wet_frame is None or dry_frame is None:
            return {"error": "Vergleichsframes fehlen"}

        w_terr = wet_frame["soil_zones"]["SOIL_TERRACE_SOUTH"]
        d_terr = dry_frame["soil_zones"]["SOIL_TERRACE_SOUTH"]
        w_comp = wet_frame["soil_zones"]["SOIL_COMPOST_EAST"]
        d_comp = dry_frame["soil_zones"]["SOIL_COMPOST_EAST"]
        w_apl = wet_frame["plants"]["PLANT_APPLE_TREE"]
        d_apl = dry_frame["plants"]["PLANT_APPLE_TREE"]

        out = {
            "duration_s": round(float(wet_frame["t_s"]), 1),
            "seed": self.seed,
            "season": self.season,
            "rain_scenario": self.scenario,
            "rain_cum_mm": wet_frame["weather"]["cumulative_rain_mm"],
            "dry_cum_mm": dry_frame["weather"]["cumulative_rain_mm"],
            "terrace_moisture_wet_pct": w_terr["soil_moisture_pct"],
            "terrace_moisture_dry_pct": d_terr["soil_moisture_pct"],
            "terrace_puddle_wet_mm": w_terr["puddle_depth_mm"],
            "terrace_puddle_dry_mm": d_terr["puddle_depth_mm"],
            "compost_moisture_wet_pct": w_comp["soil_moisture_pct"],
            "compost_moisture_dry_pct": d_comp["soil_moisture_pct"],
            "apple_turgor_wet": w_apl["turgor_index"],
            "apple_turgor_dry": d_apl["turgor_index"],
            "indoor_moisture_wet_pct": wet_frame["soil_zones"]["SOIL_INDOOR_FLOOR"]["soil_moisture_pct"],
            "indoor_moisture_dry_pct": dry_frame["soil_zones"]["SOIL_INDOOR_FLOOR"]["soil_moisture_pct"],
            "fly_captured_wet": wet_frame["fly_summary"]["captured"],
            "fly_captured_dry": dry_frame["fly_summary"]["captured"],
            "fly_open_air_wet": wet_frame["fly_summary"]["open_air"],
            "fly_open_air_dry": dry_frame["fly_summary"]["open_air"],
            "sha256_wet": wet_sha,
            "sha256_dry": dry_sha,
        }
        with self._lock:
            self._cached_dry_comparison = out
        return out

    def start_compare_dry_async(self, duration_s: float = 90.0) -> None:
        with self._lock:
            if self._compare_running:
                return
            self._compare_running = True

        def _worker() -> None:
            try:
                self.compare_against_dry_control(duration_s=duration_s)
            finally:
                with self._lock:
                    self._compare_running = False

        threading.Thread(target=_worker, name="ObservatoryDryCompare", daemon=True).start()
