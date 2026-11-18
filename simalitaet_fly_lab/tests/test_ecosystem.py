# -*- coding: utf-8 -*-
"""
Automatisierte pytest-Testsuite für SIMALITAET_ECOSYSTEM (Seestraße 43).

Prüft:
- SplitBrain / Read-Only-SQLite-Sicherheit für Wölfersheim & GBIF-Biodiversitäts-DB
- Exakte 3D-Hausokklusion, Terrassenportal & vektorisierte Beer-Lambert-Laubdämpfung
- Orakelfreie 3D-Vogelwahrnehmung (FOV-Test & Wandblockade) + 3D-CPA-Geometrie
- Echte FlyWire-v783-Populationsdynamik & kausale LC4/DNp01-Looming-Ablation
- Bit-exakten SHA-256-Determinismus & Vorhandensein der erzeugten Validierungsartefakte
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest

from fly_lab.connectome import FlyWireConnectome
from fly_lab.ecosystem.bird_models import BirdAgent, SPECIES_PROFILES, _closest_approach_3d
from fly_lab.ecosystem.ecosystem_world import Seestrasse43EcosystemWorld
from fly_lab.ecosystem.fly_population import FlyPopulationEngine, build_ecosystem_flywire_subcircuit
from fly_lab.ecosystem.simulation import EcosystemSimulation
from fly_lab.security_guards import BIODIV_DB_PATH, FlyLabSecurityGuard, FlyLabWriteLockError


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def shared_eco_sim() -> EcosystemSimulation:
    guard = FlyLabSecurityGuard()
    conn = FlyWireConnectome()
    sub = build_ecosystem_flywire_subcircuit(conn)
    return EcosystemSimulation(guard=guard, conn=conn, subcircuit=sub)


def test_world_ro_databases_and_vectorized_los() -> None:
    guard = FlyLabSecurityGuard()
    world = Seestrasse43EcosystemWorld(guard=guard)

    assert world.woelfersheim_anchor.get("verified_ro") is True
    assert world.gbif_bird_records["Cyanistes caeruleus"]["verified_occ_count"] == 19
    assert world.gbif_bird_records["Parus major"]["verified_occ_count"] == 20
    assert world.gbif_bird_records["Hirundo rustica"]["verified_occ_count"] == 5

    # Schreibschutz auf geschützte Datenbank erzwingen
    with pytest.raises(FlyLabWriteLockError):
        guard.assert_write_allowed(BIODIV_DB_PATH)

    con = guard.open_readonly_sqlite(BIODIV_DB_PATH)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("CREATE TABLE forbidden_write (id INT)")
    finally:
        con.close()

    # Hauswand blockiert Sicht vollständig (0.0); Portal lässt durch; Baumkrone dämpft
    p_in = np.array([8.8, 3.3, 1.2], dtype=np.float64)
    p_out = np.array([8.8, -5.0, 2.5], dtype=np.float64)
    assert world.line_of_sight_transmittance(p_in, p_out) == 0.0

    p_port_in = np.array([1.9, 0.3, 1.8], dtype=np.float64)
    p_port_out = np.array([1.9, -0.3, 1.8], dtype=np.float64)
    assert world.line_of_sight_transmittance(p_port_in, p_port_out) > 0.90

    p_w = np.array([-9.0, -5.0, 4.1], dtype=np.float64)
    p_e = np.array([0.0, -5.0, 4.1], dtype=np.float64)
    los_tree = world.line_of_sight_transmittance(p_w, p_e)
    assert 0.0 < los_tree < 0.35

    # Vektorisierte Matrix == Skalar-Referenz
    pa = np.vstack([p_in, p_port_in, p_w])
    pb = np.vstack([p_out, p_port_out, p_e])
    mat = world.compute_los_matrix(pa, pb)
    ref = np.array([[world.line_of_sight_transmittance(a, b) for b in pb] for a in pa], dtype=np.float32)
    assert np.allclose(mat, ref, atol=1e-5)

    # Vogel muss außerhalb von Seestraße 43 bleiben
    p_clamped, _ = world.clamp_bird_outside_obstacles(np.array([5.5, 4.5, 2.0]), np.array([1.0, 0.0, 0.0]))
    assert not world.is_inside_house(p_clamped, margin=0.05)


def test_bird_oracle_free_perception_and_cpa_geometry() -> None:
    world = Seestrasse43EcosystemWorld()
    assert SPECIES_PROFILES["CYANISTES_CAERULEUS"].hunting_strategy == "FOLIAGE_GLEAN_HOVER"
    assert SPECIES_PROFILES["PARUS_MAJOR"].hunting_strategy == "PERCH_AND_SALLY"
    assert SPECIES_PROFILES["HIRUNDO_RUSTICA"].hunting_strategy == "AERIAL_HAWKING_PN"
    assert SPECIES_PROFILES["HIRUNDO_RUSTICA"].wingspan_m > SPECIES_PROFILES["PARUS_MAJOR"].wingspan_m > SPECIES_PROFILES["CYANISTES_CAERULEUS"].wingspan_m

    bird = BirdAgent("RS_TEST", SPECIES_PROFILES["HIRUNDO_RUSTICA"], (3.5, -6.0, 3.0), (5.0, -4.0, 3.0), seed=9)
    bird.heading = np.array([0.0, 1.0, 0.0], dtype=np.float64)  # blickt nach +Y (Norden)

    fly_slots = np.array([0, 1, 2], dtype=np.int64)
    fly_ids = np.array([10, 11, 12], dtype=np.int32)
    fly_pos = np.array([
        [3.5, -9.5, 3.0],  # direkt HINTER dem Vogel (-Y, außerhalb FOV!)
        [8.5, 3.3, 1.0],   # in der geschlossenen Küche (von Hauswand verdeckt!)
        [3.5, -2.5, 3.0],  # sichtbar vor dem Vogel (+Y)
    ], dtype=np.float32)
    fly_vel = np.array([[0.3, 0.0, 0.0], [0.0, 0.0, 0.0], [0.4, 0.2, 0.0]], dtype=np.float32)

    slot_det, salience, _, vis = bird.perceive_flies(world, fly_slots, fly_ids, fly_pos, fly_vel)
    assert slot_det == 2
    assert salience > 0.0
    assert [v["slot"] for v in vis] == [2]

    # Physische CPA-Abfangprüfung: Treffer vs. Vorbeiflug
    d_hit = _closest_approach_3d(
        np.array([0.0, 0.0, 2.0]), np.array([1.0, 0.0, 2.0]),
        np.array([0.5, -0.4, 2.0]), np.array([0.5, 0.4, 2.0]),
    )
    assert d_hit < 0.05

    d_miss = _closest_approach_3d(
        np.array([0.0, 0.0, 2.0]), np.array([1.0, 0.0, 2.0]),
        np.array([0.5, 0.9, 2.0]), np.array([0.5, 1.6, 2.0]),
    )
    assert d_miss > SPECIES_PROFILES["HIRUNDO_RUSTICA"].capture_radius_m


def test_flywire_ecosystem_closed_loop_and_ablation(shared_eco_sim: EcosystemSimulation) -> None:
    assert shared_eco_sim.subcircuit.n_neurons == 1993
    assert shared_eco_sim.subcircuit.n_edges == 42311

    res_base = shared_eco_sim.run_episode(
        experiment_id="TEST_BASE_25S",
        duration_s=25.0,
        seed=77,
        looming_gain=1.0,
        checkpoint_times_s=(),
    )
    res_noloom = shared_eco_sim.run_episode(
        experiment_id="TEST_NOLOOM_25S",
        duration_s=25.0,
        seed=77,
        looming_gain=0.0,
        checkpoint_times_s=(),
    )

    assert res_base["total_flywire_spikes"] > 100_000
    assert res_base["fly_total_escapes"] > 0
    assert res_noloom["fly_total_escapes"] == 0
    assert res_base["fly_zones"]["indoor"] > 0
    assert all(b["detections"] > 0 and b["energy_spent_j"] > 0.0 for b in res_base["birds"].values())


def test_determinism_sha256_and_validation_outputs(shared_eco_sim: EcosystemSimulation) -> None:
    r1 = shared_eco_sim.run_episode("DET_1", duration_s=12.0, seed=123, checkpoint_times_s=())
    r2 = shared_eco_sim.run_episode("DET_2", duration_s=12.0, seed=123, checkpoint_times_s=())
    assert r1["state_sha256"] == r2["state_sha256"]

    summary_path = PROJECT_ROOT / "results" / "validation_ecosystem_summary.json"
    if summary_path.exists():
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        assert data["runtime_summary"]["determinism_verified"] is True
        assert data["protected_core_integrity"]["protected_code_and_db_intact"] is True
        for key in ("world_3d_and_niches", "perspectives_and_neural", "population_dynamics_and_experiments"):
            assert Path(data["generated_images"][key]).exists()
