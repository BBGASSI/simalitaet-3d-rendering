# -*- coding: utf-8 -*-
"""
Ausführungsskript für die vollständige SIMALITAET_ECOSYSTEM-Validierungssuite:
- Prüft Schutzintegrität vor und nach dem Lauf (Luanti + SQLite RO + FlyWire-Dateien)
- Führt Eco-Exp 1 bis 4b deterministisch bei gedrosselter Prozesspriorität aus
- Exportiert validation_ecosystem.json + kompakte validation_ecosystem_summary.json (< 40 KB)
- Rendert alle 3 hochauflösenden Forschungs-Dashboards in results/ und das Artifact-Verzeichnis
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

from fly_lab.ecosystem.simulation import EcosystemSimulation
from fly_lab.ecosystem.visualization import generate_all_ecosystem_dashboards
from fly_lab.security_guards import (
    BIODIV_DB_PATH,
    FlyLabSecurityGuard,
    WOELFERSHEIM_DB_PATH,
    set_below_normal_priority,
    sha256_file,
)


PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "results"
ARTIFACT_DIR = Path(r"C:\Users\Ulric\.gemini\antigravity\brain\fcf64b6a-aa55-49c4-9aac-05bbe2d54441")


def _build_compact_summary(report: Dict[str, Any], guard_report: Dict[str, Any], image_paths: Dict[str, str]) -> Dict[str, Any]:
    """Entfernt große Roh-Trajektorien für eine kompakte <40-KB-Übersichtsdatei."""
    compact_exps: Dict[str, Any] = {}
    for k, exp in report["experiments"].items():
        e_copy = {ek: ev for ek, ev in exp.items() if ek not in ("time_series", "tracks", "perspectives")}
        if "perspectives" in exp:
            e_copy["perspective_sample_counts"] = {
                "fly_samples": len(exp["perspectives"]["fly_samples"]),
                "bird_samples": {bk: len(bv) for bk, bv in exp["perspectives"]["bird_samples"].items()},
            }
        compact_exps[k] = e_copy

    return {
        "world_anchor": report["world_metadata"]["woelfersheim_anchor"],
        "gbif_woelfersheim_birds": report["world_metadata"]["gbif_woelfersheim_birds"],
        "subcircuit_metadata": report["subcircuit_metadata"],
        "runtime_summary": report["runtime_summary"],
        "comparisons": report["comparisons"],
        "experiments": compact_exps,
        "epistemic_chambers": report["epistemic_chambers"],
        "protected_core_integrity": guard_report,
        "generated_images": image_paths,
    }


def main() -> int:
    set_below_normal_priority()
    guard = FlyLabSecurityGuard()

    pre_snap = FlyLabSecurityGuard.snapshot_protected_state()
    pre_snap["biodiv_db_sha256"] = sha256_file(BIODIV_DB_PATH) if BIODIV_DB_PATH.exists() else None
    pre_snap["woelfersheim_db_sha256"] = sha256_file(WOELFERSHEIM_DB_PATH) if WOELFERSHEIM_DB_PATH.exists() else None

    sim = EcosystemSimulation(guard=guard)
    report = sim.run_all_experiments()

    post_snap = FlyLabSecurityGuard.snapshot_protected_state()
    post_snap["biodiv_db_sha256"] = sha256_file(BIODIV_DB_PATH) if BIODIV_DB_PATH.exists() else None
    post_snap["woelfersheim_db_sha256"] = sha256_file(WOELFERSHEIM_DB_PATH) if WOELFERSHEIM_DB_PATH.exists() else None
    intact = pre_snap == post_snap
    guard_report = {
        "protected_code_and_db_intact": intact,
        "pre": pre_snap,
        "post": post_snap,
        "audit_events": list(guard.audit_events),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    img_paths = generate_all_ecosystem_dashboards(report, RESULTS_DIR, ARTIFACT_DIR)

    full_out = copy.copy(report)
    full_out["protected_core_integrity"] = guard_report
    full_out["generated_images"] = img_paths
    (RESULTS_DIR / "validation_ecosystem.json").write_text(
        json.dumps(full_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    compact_summary = _build_compact_summary(report, guard_report, img_paths)
    summary_text = json.dumps(compact_summary, ensure_ascii=False, indent=2)
    (RESULTS_DIR / "validation_ecosystem_summary.json").write_text(summary_text, encoding="utf-8")

    exp1 = report["experiments"]["eco_exp_1_baseline_150s"]
    comp = report["comparisons"]
    print("=== SIMALITAET_ECOSYSTEM SUITE COMPLETE ===")
    print(f"Wall Time: {report['runtime_summary']['total_wall_time_s']}s | Baseline: {exp1['ms_per_tick']} ms/tick | Peak RSS: {report['runtime_summary']['peak_rss_mb']} MB")
    print(f"Determinism SHA-256 match: {comp['exp4_determinism_sha256_match']}")
    print(f"Protected DB & Luanti intact: {intact} | Summary JSON bytes: {len(summary_text)}")
    print(f"150s Baseline -> Flies alive: {exp1['flies_alive']} {exp1['fly_zones']} | Births: {exp1['fly_total_births']} | Captured: {exp1['fly_total_captured']} | Spikes: {exp1['total_flywire_spikes']}")
    for sp, bs in exp1["birds"].items():
        print(f"  {bs['bird_id']} ({bs['common_name_de']}): catches={bs['catches']}, misses={bs['missed_strikes']}, zones%={bs['zone_share_pct']}, E={bs['energy_final_j']}/{bs['energy_max_j']}J")
    print("Ablations (90s):", json.dumps(comp, ensure_ascii=False))
    return 0 if (intact and comp["exp4_determinism_sha256_match"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
