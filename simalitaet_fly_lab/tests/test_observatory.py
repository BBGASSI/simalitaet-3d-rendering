# -*- coding: utf-8 -*-
"""
Automatisierte pytest-Suite für das SIMALITÄT Ökosystem-Observatorium.

Prüft:
1. Read-Only-Laden der Wölfersheim-/GBIF-/DWD-Anker & Schreibschutz
2. Hydrologie (Bodenfeuchte, Pfützen, Hangabfluss, Innenboden-Schutz)
3. Pflanzenphysiologie (Blattnässe, Turgor-Lag) & Sekundärinsekten (Hummel-Schutz, Käfer)
4. Kausale Ereignisketten (inkl. expliziter Nicht-Reaktionen) & Vorher-Nachher-Diffs
5. Bit-exakten SHA-256-Determinismus (Regen) vs. Abgrenzung zur Trocken-Kontrolle
6. Lokalen HTTP-Observatorium-Server (/api/meta, /api/control, /api/state, /api/object, /api/diff, /api/causal_chain)
"""

from __future__ import annotations

import json
import urllib.request

import numpy as np
import pytest

from fly_lab.connectome import FlyWireConnectome
from fly_lab.ecosystem.ecosystem_world import Seestrasse43EcosystemWorld
from fly_lab.ecosystem.environment_dynamics import EnvironmentDynamics
from fly_lab.ecosystem.fly_population import build_ecosystem_flywire_subcircuit
from fly_lab.ecosystem.observatory_engine import ObservatoryEngine
from fly_lab.ecosystem.observatory_server import ObservatoryServer
from fly_lab.security_guards import BIODIV_DB_PATH, FlyLabSecurityGuard, FlyLabWriteLockError


@pytest.fixture(scope="module")
def shared_obs_deps():
    guard = FlyLabSecurityGuard()
    conn = FlyWireConnectome()
    sub = build_ecosystem_flywire_subcircuit(conn)
    return guard, conn, sub


def test_ro_extended_gbif_and_dwd_snapshot() -> None:
    guard = FlyLabSecurityGuard()
    world = Seestrasse43EcosystemWorld(guard=guard)

    assert "Bombus pascuorum" in world.gbif_extended_records
    assert "Carabus auratus" in world.gbif_extended_records
    assert "Sambucus ebulus" in world.gbif_extended_records
    assert world.dwd_weather_reference.get("available") is True
    assert world.dwd_weather_reference.get("source") == "DWD_ICON_D2_LIVE"

    with pytest.raises(FlyLabWriteLockError):
        guard.assert_write_allowed(BIODIV_DB_PATH)


def test_hydrology_rain_puddles_flow_and_indoor_non_reaction() -> None:
    world = Seestrasse43EcosystemWorld()
    env = EnvironmentDynamics(world, scenario="REGENZYKLUS", season="SOMMER", seed=42)
    z0 = {z.zone_id: z for z in env.hydro.summarize_zones()}

    for _ in range(int(round(52.0 / 0.025))):
        world.step(0.025)
        env.step(world, 0.025)

    z_peak = {z.zone_id: z for z in env.hydro.summarize_zones()}
    assert z_peak["SOIL_TERRACE_SOUTH"].soil_moisture_pct > z0["SOIL_TERRACE_SOUTH"].soil_moisture_pct + 4.0
    assert z_peak["SOIL_TERRACE_SOUTH"].puddle_depth_mm > 1.0
    assert z_peak["SOIL_ROOF_EAVE_S"].flow_speed_cms > 0.2
    # Hausboden Küche muss komplett trocken bleiben
    assert z_peak["SOIL_INDOOR_FLOOR"].soil_moisture_pct == 0.0
    assert z_peak["SOIL_INDOOR_FLOOR"].puddle_depth_mm == 0.0


def test_vegetation_turgor_lag_and_secondary_insects_react() -> None:
    world = Seestrasse43EcosystemWorld()
    env = EnvironmentDynamics(world, scenario="REGENZYKLUS", season="SOMMER", seed=42)
    apl0 = next(p for p in env.vegetation.plants if p.plant_id == "PLANT_APPLE_TREE").turgor_index

    bumbles_sheltered_peak = 0
    beetles_moist_seen = 0
    for tick in range(int(round(65.0 / 0.025))):
        world.step(0.025)
        w = env.step(world, 0.025)
        if w.rain_mm_h >= 5.0:
            bumbles_sheltered_peak = max(
                bumbles_sheltered_peak,
                sum(1 for i in env.other_insects.insects if i.guild == "BUMBLEBEE" and i.state == "SHELTERING_RAIN"),
            )
            beetles_moist_seen = max(
                beetles_moist_seen,
                sum(1 for i in env.other_insects.insects if i.guild == "GROUND_BEETLE" and i.state in ("FORAGING_MOIST", "AVOIDING_PUDDLE")),
            )

    apl_end = next(p for p in env.vegetation.plants if p.plant_id == "PLANT_APPLE_TREE")
    assert apl_end.turgor_index > apl0 + 0.05
    assert bumbles_sheltered_peak >= 2
    assert beetles_moist_seen >= 2


def test_observatory_causal_chains_non_reactions_and_diff(shared_obs_deps) -> None:
    guard, conn, sub = shared_obs_deps
    eng = ObservatoryEngine(scenario="REGENZYKLUS", season="SOMMER", seed=42, guard=guard, conn=conn, subcircuit=sub)
    eng.run_until(65.0)

    events = eng.tracker.events
    assert len(events) >= 12
    non_reactions = [e for e in events if e.is_non_reaction]
    assert len(non_reactions) >= 2
    assert any(e.entity_id == "SOIL_INDOOR_FLOOR" for e in non_reactions)

    linked = [e for e in events if len(e.cause_event_ids) > 0 and not e.is_non_reaction]
    assert len(linked) >= 8
    chain = eng.get_causal_chain(linked[-1].event_id)
    assert len(chain["ancestors"]) >= 1

    diff = eng.get_diff(10.0, 55.0, entity_id="SOIL_TERRACE_SOUTH")
    assert diff["weather_delta"]["cum_rain_delta_mm"] > 0.05
    assert diff["zone_diffs"]["SOIL_TERRACE_SOUTH"]["delta_moisture_pct"] > 3.0
    assert diff["zone_diffs"]["SOIL_INDOOR_FLOOR"]["delta_moisture_pct"] == 0.0


def test_observatory_determinism_vs_dry_control(shared_obs_deps) -> None:
    guard, conn, sub = shared_obs_deps
    e1 = ObservatoryEngine(scenario="REGENZYKLUS", season="SOMMER", seed=42, guard=guard, conn=conn, subcircuit=sub)
    e1.run_until(36.0)
    sha1 = e1.compute_state_sha256()

    e2 = ObservatoryEngine(scenario="REGENZYKLUS", season="SOMMER", seed=42, guard=guard, conn=conn, subcircuit=sub)
    e2.run_until(36.0)
    sha2 = e2.compute_state_sha256()
    assert sha1 == sha2

    e_dry = ObservatoryEngine(scenario="TROCKEN_KONTROLLE", season="SOMMER", seed=42, guard=guard, conn=conn, subcircuit=sub)
    e_dry.run_until(36.0)
    assert e_dry.compute_state_sha256() != sha1
    z_wet = e1.timeline.get_frame(36.0)["soil_zones"]["SOIL_TERRACE_SOUTH"]
    z_dry = e_dry.timeline.get_frame(36.0)["soil_zones"]["SOIL_TERRACE_SOUTH"]
    assert z_wet["puddle_depth_mm"] > z_dry["puddle_depth_mm"]


def test_observatory_live_http_endpoints(shared_obs_deps) -> None:
    guard, conn, sub = shared_obs_deps
    eng = ObservatoryEngine(scenario="REGENZYKLUS", season="SOMMER", seed=42, guard=guard, conn=conn, subcircuit=sub)
    srv = ObservatoryServer(engine=eng, host="127.0.0.1", port=0)
    port = srv.start()
    try:
        base = f"http://127.0.0.1:{port}"
        meta = json.loads(urllib.request.urlopen(f"{base}/api/meta", timeout=5).read().decode("utf-8"))
        assert meta["flywire_subcircuit"]["n_neurons"] == 1993

        req = urllib.request.Request(
            f"{base}/api/control",
            data=json.dumps({"action": "step", "seconds": 35.0}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        ctrl = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
        assert ctrl["live_sim_time_s"] >= 35.0

        det = json.loads(urllib.request.urlopen(f"{base}/api/object?id=SOIL_TERRACE_SOUTH", timeout=5).read().decode("utf-8"))
        assert det["entity_id"] == "SOIL_TERRACE_SOUTH"
        assert len(det["metrics"]) >= 4

        diff = json.loads(urllib.request.urlopen(f"{base}/api/diff?t1=0&t2=35&entity_id=SOIL_TERRACE_SOUTH", timeout=5).read().decode("utf-8"))
        assert diff["t2_s"] >= 35.0
    finally:
        srv.stop()
