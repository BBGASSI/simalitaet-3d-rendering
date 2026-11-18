# -*- coding: utf-8 -*-
"""
Unit- und Integrationstests für SIMALITAET_FLY_LAB (Seestraße 43).
Prüft Schutzgrenzen (SplitBrain/ROT/RO-SQLite), FlyWire-v783-Datenintegrität,
Seestraße-43-Geometrie inkl. 1,5-cm/2,0-cm-Türspalten, Mikroklima, Sensorik,
NeuroMechFly-Körperphysik, MB-Plastizität und Forschungsmetriken.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fly_lab.body_engine import FlyBodyEngine, MotorOutputVector
from fly_lab.connectome import FlyWireConnectome
from fly_lab.malecns_adapter import MaleCNSReferenceAdapter
from fly_lab.neural_and_memory import FlyWireNeuralEngine, MushroomBodyShortTermMemory
from fly_lab.security_guards import (
    WOELFERSHEIM_DB_PATH,
    FlyLabSecurityGuard,
    FlyLabWriteLockError,
)
from fly_lab.seestrasse_43_world import Seestrasse43World, roof_ceiling_z
from fly_lab.sensory_interface import FlySensoryInterface


@pytest.fixture(scope="module")
def shared_connectome():
    return FlyWireConnectome()


@pytest.fixture(scope="module")
def shared_world_and_snap():
    w = Seestrasse43World()
    return w, w.snapshot_voc_and_foods()


def test_security_guard_blocks_external_writes_and_rot():
    guard = FlyLabSecurityGuard()
    with pytest.raises(FlyLabWriteLockError):
        guard.assert_write_allowed(Path(r"C:\Users\Ulric\.gemini\antigravity\scratch\SIMALITAET_LUANTI\test.txt"))
    with pytest.raises(FlyLabWriteLockError):
        guard.assert_write_allowed(Path(r"C:\Users\Ulric\.gemini\antigravity\scratch\outside.txt"))

    if WOELFERSHEIM_DB_PATH.exists():
        con = guard.open_readonly_sqlite(WOELFERSHEIM_DB_PATH)
        try:
            row = con.execute("SELECT building_id FROM buildings WHERE building_id='HOME_SEESTRASSE_43'").fetchone()
            assert row is not None and row["building_id"] == "HOME_SEESTRASSE_43"
            with pytest.raises(sqlite3.DatabaseError):
                con.execute("CREATE TABLE forbidden_hack (x INT)")
        finally:
            con.close()

    guard.activate_rot("TEST_LOCK")
    with pytest.raises(FlyLabWriteLockError):
        guard.assert_write_allowed(ROOT / "results" / "blocked.txt")


def test_flywire_v783_integrity_and_malecns_protocol(shared_connectome):
    c = shared_connectome
    assert c.n_neurons == 138639
    assert c.signed_weight_matrix.nnz == 15091983
    assert c.total_synapses == 54492922
    assert c.matched_annotations >= 138600
    assert len(c.pool_indices("orn_geosmin")) == 39
    assert len(c.pool_indices("pn_geosmin")) == 11
    assert len(c.pool_indices("dn_steer")) == 4
    assert len(c.pool_indices("kc")) == 5177

    sub = c.extract_sensorimotor_subcircuit()
    assert sub.w_sub.shape[0] > 5000
    assert sub.w_sub.nnz > 100000

    mc = MaleCNSReferenceAdapter.build_deterministic_vnc_bridge_sample()
    assert mc.n_neurons == 6
    assert mc.metadata_summary()["supports_vnc_motor"] is True


def test_seestrasse_43_geometry_microclimate_and_door_gaps(shared_world_and_snap):
    w, snap = shared_world_and_snap
    w.restore_voc_and_foods(snap)
    assert len(w.rooms) == 13
    assert len(w.foods) == 9
    assert int(w.air_mask.sum()) > 40000
    # 38°-Satteldach & 1,1 m Kniestock
    assert pytest.approx(6.7, abs=0.05) == roof_ceiling_z(0.0)
    assert pytest.approx(8.2, abs=0.05) == roof_ceiling_z(4.5)
    assert w.is_navigable(5.0, 0.4, 7.6) is False
    assert w.is_navigable(5.0, 4.5, 7.6) is True

    # 1,5 cm Speisekammer-Spalt & 2,0 cm Heizraum-Spalt
    assert w.is_navigable(7.30, 4.00, 0.008, 0.003) is True
    assert w.is_navigable(7.30, 4.00, 0.45, 0.003) is False
    assert w.is_navigable(7.25, 8.88, 0.012, 0.003) is True
    assert w.is_navigable(7.25, 8.88, 0.50, 0.003) is False

    # Mikroklima: ANBAU_HEIZ 26,5 °C, EG ~21 °C, DG_STUDIO ~23,5 °C, OG_BAD_2 >= 75% Feuchte
    t_heiz = w.query_environment(7.5, 10.5, 1.0)["temp_c"]
    t_eg = w.query_environment(4.5, 4.0, 1.2)["temp_c"]
    t_dg = w.query_environment(5.5, 4.5, 6.4)["temp_c"]
    h_bad2 = w.query_environment(6.15, 8.15, 3.65)["humidity_pct"]
    assert t_heiz > 26.0
    assert t_dg > t_eg + 1.5
    assert h_bad2 >= 75.0


def test_sensory_isolation_and_body_feeding(shared_world_and_snap):
    w, snap = shared_world_and_snap
    w.restore_voc_and_foods(snap)
    sens = FlySensoryInterface()

    # In der Luft: Gustatorik muss strikt 0 sein!
    sv_air = sens.sense(w, np.array([8.85, 3.35, 1.0]), np.zeros(3), 0.0, 0.0, is_landed=False)
    assert sv_air.contact_food_id is None
    assert float(sv_air.gustation_contact.sum()) == 0.0

    # Gelandet auf FOOD_02 -> Zucker/Wasser aktiv & Rüssel baut Masse ab
    body = FlyBodyEngine(start_pos=(8.85, 3.35, 0.354), start_landed=True)
    m0 = w.food_by_id["FOOD_02"].mass_g
    for _ in range(12):
        res = body.step(w, MotorOutputVector(1.0, 0, 0, 0, 0.012, 0.1, False, True, False), dt_s=0.010)
    assert body.state.ingested_energy_mj > 0.0
    assert w.food_by_id["FOOD_02"].mass_g < m0
    assert body.state.tarsal_contacts >= 3


def test_short_term_memory_learning_and_forgetting():
    mb = MushroomBodyShortTermMemory(enabled=True, tau_decay_s=180.0)
    feat = np.array([1.2, 0.0, 0.0], dtype=np.float32)
    # Quinin-PPL1 Bestrafung an Ethern lernen
    for _ in range(250):
        mb.step(feat, r_kc=0.5, r_pam=0.0, r_ppl1=0.9, dt_s=0.05)
    v_10s = mb.advance_retention_time(10.0)
    v_60s = mb.advance_retention_time(50.0)
    v_1800s = mb.advance_retention_time(1740.0)
    assert v_10s < -0.5
    assert abs(v_60s) < abs(v_10s)
    # Nach 30 Minuten ohne Konsolidierung abgeklungen -> kein unbewiesenes LTM!
    assert abs(v_1800s) < 0.01
