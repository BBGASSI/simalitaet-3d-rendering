# -*- coding: utf-8 -*-
"""
Deterministische Validierungssuite & Analyse-Dashboard für das SIMALITÄT Ökosystem-Observatorium.

Prüft:
1. Unveränderte Schutzintegrität (Luanti, SQLite RO-DBs, DWD-Snapshot-JSON)
2. Vollständigen 90-s-Regenzyklus (seed=42) vs. Wiederholungslauf (bit-exakter SHA-256)
3. Kausale Gegenprobe gegen TROCKEN_KONTROLLE (seed=42)
4. Kausalketten inkl. expliziter Nicht-Reaktionen (Innenboden Küche, Wurzel-Lag, Kronen-Interzeption)
5. Export von results/validation_observatory_summary.json (< 38 KB) & observatory_rain_cycle_analysis.png
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import time
from typing import Any, Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fly_lab.connectome import FlyWireConnectome
from fly_lab.ecosystem.fly_population import build_ecosystem_flywire_subcircuit
from fly_lab.ecosystem.observatory_engine import ObservatoryEngine
from fly_lab.security_guards import (
    BIODIV_DB_PATH,
    FlyLabSecurityGuard,
    SCRATCH_ROOT,
    WOELFERSHEIM_DB_PATH,
    get_process_rss_mb,
    set_below_normal_priority,
    sha256_file,
)


PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "results"
ARTIFACT_DIR = Path(r"C:\Users\Ulric\.gemini\antigravity\brain\fcf64b6a-aa55-49c4-9aac-05bbe2d54441")
DWD_SNAP_PATH = SCRATCH_ROOT / "SIMALITAET_REALDATA_RESEARCH" / "prototypes" / "latest_env_snapshot.json"


def _render_analysis_png(
    wet_frames: list,
    dry_cmp: Dict[str, Any],
    summary_metrics: Dict[str, Any],
    out_path: Path,
) -> None:
    t_w = np.array([f["t_s"] for f in wet_frames])
    rain = np.array([f["weather"]["rain_mm_h"] for f in wet_frames])
    temp = np.array([f["weather"]["temperature_c"] for f in wet_frames])
    rh = np.array([f["weather"]["humidity_pct"] for f in wet_frames])

    m_terr = np.array([f["soil_zones"]["SOIL_TERRACE_SOUTH"]["soil_moisture_pct"] for f in wet_frames])
    m_comp = np.array([f["soil_zones"]["SOIL_COMPOST_EAST"]["soil_moisture_pct"] for f in wet_frames])
    m_in = np.array([f["soil_zones"]["SOIL_INDOOR_FLOOR"]["soil_moisture_pct"] for f in wet_frames])
    p_terr = np.array([f["soil_zones"]["SOIL_TERRACE_SOUTH"]["puddle_depth_mm"] for f in wet_frames])
    p_eave = np.array([f["soil_zones"]["SOIL_ROOF_EAVE_S"]["puddle_depth_mm"] for f in wet_frames])

    wet_leaf = np.array([f["plants"]["PLANT_APPLE_TREE"]["foliage_wetness"] for f in wet_frames])
    turg_apl = np.array([f["plants"]["PLANT_APPLE_TREE"]["turgor_index"] for f in wet_frames])
    nec_flw = np.array([f["plants"]["PLANT_FLOWER_BED_SW"]["nectar_mg"] / f["plants"]["PLANT_FLOWER_BED_SW"]["max_nectar_mg"] for f in wet_frames])
    bumble_shelt = np.array([
        sum(1 for i in f["other_insects"].values() if i["guild"] == "BUMBLEBEE" and i["state"] == "SHELTERING_RAIN") / 4.0
        for f in wet_frames
    ])
    beetle_moist = np.array([
        sum(1 for i in f["other_insects"].values() if i["guild"] == "GROUND_BEETLE" and i["state"] == "FORAGING_MOIST") / 4.0
        for f in wet_frames
    ])

    fig, axes = plt.subplots(2, 2, figsize=(16.0, 9.8), dpi=180, constrained_layout=True)
    fig.suptitle(
        "SIMALITÄT Ökosystem-Observatorium: Realer 90-s-Regenzyklus, Kaskadenwirkung & Trocken-Kontrolle",
        fontsize=14,
        fontweight="bold",
    )

    # Panel 1: Wetterverlauf
    ax1 = axes[0, 0]
    ax1.fill_between(t_w, 0, rain, color="#38bdf8", alpha=0.35, label="Niederschlag [mm/h]")
    ax1.plot(t_w, rain, color="#0284c7", lw=1.8)
    ax1_r = ax1.twinx()
    ax1_r.plot(t_w, temp, color="#ea580c", lw=1.5, label="Temperatur [°C]")
    ax1_r.plot(t_w, rh / 4.0, color="#6366f1", lw=1.3, ls="--", label="rF [%] / 4")
    ax1.set_title("1. Wetter- & Tageszeitverlauf (REGENZYKLUS, Sommer)", fontsize=10.5)
    ax1.set_xlabel("Simulationszeit [s]")
    ax1.set_ylabel("Niederschlag [mm/h]", color="#0284c7")
    ax1_r.set_ylabel("Temperatur [°C] / Rel. Feuchte (÷4)")
    ax1.grid(True, linestyle=":", alpha=0.45)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax1_r.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=7.8)

    # Panel 2: Hydrologie & Pfützen + Innenraum Nicht-Reaktion
    ax2 = axes[0, 1]
    ax2.plot(t_w, m_comp, color="#15803d", lw=1.7, label="Kompost Bodenfeuchte [% Vol.]")
    ax2.plot(t_w, m_terr, color="#0369a1", lw=1.7, label="Südterrasse Feuchte [% Vol.]")
    ax2.plot(t_w, m_in, color="#475569", lw=1.5, ls="--", label="Innenboden Küche (0 % Schutz-Kontrolle)")
    ax2_r = ax2.twinx()
    ax2_r.plot(t_w, p_eave, color="#06b6d4", lw=1.4, ls=":", label="Dachtraufe Pfütze [mm]")
    ax2_r.plot(t_w, p_terr, color="#2563eb", lw=1.5, ls="-.", label="Terrasse Pfütze [mm]")
    ax2.set_title("2. Bodenfeuchte, Pfützenbildung & Haus-Schutzbarriere", fontsize=10.5)
    ax2.set_xlabel("Simulationszeit [s]")
    ax2.set_ylabel("Bodenfeuchte [% Vol.]")
    ax2_r.set_ylabel("Pfützentiefe [mm]")
    ax2.grid(True, linestyle=":", alpha=0.45)
    hh1, ll1 = ax2.get_legend_handles_labels()
    hh2, ll2 = ax2_r.get_legend_handles_labels()
    ax2.legend(hh1 + hh2, ll1 + ll2, loc="upper left", fontsize=7.5, ncol=2)

    # Panel 3: Pflanzen-Lag & Insektenreaktion
    ax3 = axes[1, 0]
    ax3.plot(t_w, wet_leaf, color="#0ea5e9", lw=1.6, label="Apfelbaum Blattnässe [0..1]")
    ax3.plot(t_w, turg_apl, color="#16a34a", lw=1.8, label="Apfelbaum Turgor (Wurzel-Lag ~14 s)")
    ax3.plot(t_w, nec_flw, color="#f59e0b", lw=1.4, ls="--", label="Blühstreifen Nektaranteil [0..1]")
    ax3.plot(t_w, bumble_shelt, color="#eab308", lw=1.3, ls=":", label="Hummeln im Regenschutz [Anteil]")
    ax3.plot(t_w, beetle_moist, color="#22c55e", lw=1.3, ls="-.", label="Laufkäfer Feucht-Aktivität [Anteil]")
    ax3.set_ylim(-0.04, 1.34)
    ax3.set_title("3. Biologische Kaskade: Blattbenetzung → Wurzel-Turgor → Insekten", fontsize=10.5)
    ax3.set_xlabel("Simulationszeit [s]")
    ax3.set_ylabel("Normierte Reaktion [0..1]")
    ax3.grid(True, linestyle=":", alpha=0.45)
    ax3.legend(loc="upper right", fontsize=7.4, ncol=2)

    # Panel 4: Regen vs. Trocken-Kontrolle + Budgetbox
    ax4 = axes[1, 1]
    cats = ["Terrasse\nFeuchte (%Vol.)", "Kompost\nFeuchte (%Vol.)", "Terrasse\nPfütze (mm)", "Apfelbaum\nTurgor (x10)"]
    wet_v = [
        dry_cmp["terrace_moisture_wet_pct"],
        dry_cmp["compost_moisture_wet_pct"],
        dry_cmp["terrace_puddle_wet_mm"],
        dry_cmp["apple_turgor_wet"] * 10.0,
    ]
    dry_v = [
        dry_cmp["terrace_moisture_dry_pct"],
        dry_cmp["compost_moisture_dry_pct"],
        dry_cmp["terrace_puddle_dry_mm"],
        dry_cmp["apple_turgor_dry"] * 10.0,
    ]
    x = np.arange(len(cats))
    bw = 0.34
    b1 = ax4.bar(x - bw / 2, wet_v, width=bw, color="#0284c7", label="Regenzyklus (90 s)")
    b2 = ax4.bar(x + bw / 2, dry_v, width=bw, color="#64748b", label="Trocken-Kontrolle (0 mm)")
    for r in b1:
        ax4.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.4, f"{r.get_height():.1f}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    for r in b2:
        ax4.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.4, f"{r.get_height():.1f}", ha="center", va="bottom", fontsize=8)
    ax4.set_xticks(x, cats, fontsize=8.5)
    ax4.set_ylim(0, max(wet_v + dry_v + [10]) * 1.28)
    ax4.set_ylabel("Zustandswert bei t = 90 s")
    ax4.set_title("4. Kausale Gegenprobe (Regen vs. Trocken, identischer Seed)", fontsize=10.5)
    ax4.grid(axis="y", linestyle=":", alpha=0.45)
    ax4.legend(loc="upper left", fontsize=8)

    info = (
        f"Determinismus SHA-256: {'PASS' if summary_metrics['determinism_verified'] else 'FAIL'}\n"
        f"Regen-Laufzeit: {summary_metrics['rain_ms_per_tick']:.2f} ms/Tick\n"
        f"Peak RSS: {summary_metrics['peak_rss_mb']:.1f} MB\n"
        f"Kausale Ereignisse: {summary_metrics['total_events']} (NR: {summary_metrics['non_reactions']})"
    )
    ax4.text(
        0.98, 0.96, info,
        transform=ax4.transAxes, ha="right", va="top", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.35", fc="#dcfce7" if summary_metrics["determinism_verified"] else "#fee2e2", ec="#16a34a"),
    )

    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main() -> int:
    set_below_normal_priority()
    guard = FlyLabSecurityGuard()
    pre_snap = FlyLabSecurityGuard.snapshot_protected_state()
    pre_snap["biodiv_db_sha256"] = sha256_file(BIODIV_DB_PATH) if BIODIV_DB_PATH.exists() else None
    pre_snap["woelfersheim_db_sha256"] = sha256_file(WOELFERSHEIM_DB_PATH) if WOELFERSHEIM_DB_PATH.exists() else None
    pre_snap["dwd_snap_sha256"] = sha256_file(DWD_SNAP_PATH) if DWD_SNAP_PATH.exists() else None

    conn = FlyWireConnectome()
    sub = build_ecosystem_flywire_subcircuit(conn)

    # 1. Hauptlauf REGENZYKLUS 90 s (Seed=42)
    t0 = time.perf_counter()
    eng_wet = ObservatoryEngine(scenario="REGENZYKLUS", season="SOMMER", seed=42, guard=guard, conn=conn, subcircuit=sub)
    eng_wet.run_until(90.0)
    wet_wall_s = time.perf_counter() - t0
    wet_sha = eng_wet.compute_state_sha256()

    # 2. Bit-exakter Wiederholungslauf (Determinismus)
    eng_rep = ObservatoryEngine(scenario="REGENZYKLUS", season="SOMMER", seed=42, guard=guard, conn=conn, subcircuit=sub)
    eng_rep.run_until(90.0)
    rep_sha = eng_rep.compute_state_sha256()
    det_match = (wet_sha == rep_sha)

    # 3. Gegenprobe vs. TROCKEN_KONTROLLE
    dry_cmp = eng_wet.compare_against_dry_control(duration_s=90.0)

    # 4. Vorher-Nachher-Diff & Kausalketten prüfen
    diff_10_55 = eng_wet.get_diff(10.0, 55.0, entity_id="SOIL_TERRACE_SOUTH")
    diff_10_90 = eng_wet.get_diff(10.0, 90.0, entity_id="PLANT_APPLE_TREE")
    # Große Arrays aus Diff für kompakte Summary entfernen
    diff_10_55_compact = {k: v for k, v in diff_10_55.items() if not k.startswith("grid_") and k != "events_in_window"}
    diff_10_55_compact["events_in_window_count"] = len(diff_10_55["events_in_window"])
    diff_10_90_compact = {k: v for k, v in diff_10_90.items() if not k.startswith("grid_") and k != "events_in_window"}
    diff_10_90_compact["events_in_window_count"] = len(diff_10_90["events_in_window"])

    ev_list = [asdict(e) for e in eng_wet.tracker.events]
    nr_events = [e for e in ev_list if e["is_non_reaction"]]
    sample_chain_target = next((e["event_id"] for e in reversed(ev_list) if len(e["cause_event_ids"]) > 0 and not e["is_non_reaction"]), "")
    sample_chain = eng_wet.get_causal_chain(sample_chain_target) if sample_chain_target else {}

    post_snap = FlyLabSecurityGuard.snapshot_protected_state()
    post_snap["biodiv_db_sha256"] = sha256_file(BIODIV_DB_PATH) if BIODIV_DB_PATH.exists() else None
    post_snap["woelfersheim_db_sha256"] = sha256_file(WOELFERSHEIM_DB_PATH) if WOELFERSHEIM_DB_PATH.exists() else None
    post_snap["dwd_snap_sha256"] = sha256_file(DWD_SNAP_PATH) if DWD_SNAP_PATH.exists() else None
    intact = pre_snap == post_snap

    n_ticks = max(1, eng_wet.tick_count)
    rain_ms_tick = round(1000.0 * wet_wall_s / n_ticks, 3)
    rss_mb = round(get_process_rss_mb(), 2)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    png_path = RESULTS_DIR / "observatory_rain_cycle_analysis.png"
    summary_metrics = {
        "determinism_verified": det_match,
        "rain_ms_per_tick": rain_ms_tick,
        "peak_rss_mb": rss_mb,
        "total_events": len(ev_list),
        "non_reactions": len(nr_events),
    }
    _render_analysis_png(eng_wet.timeline.frames, dry_cmp, summary_metrics, png_path)
    if ARTIFACT_DIR.exists():
        (ARTIFACT_DIR / png_path.name).write_bytes(png_path.read_bytes())

    summary_payload = {
        "runtime": {
            "rain_90s_wall_s": round(wet_wall_s, 3),
            "rain_ms_per_tick": rain_ms_tick,
            "peak_rss_mb": rss_mb,
            "determinism_verified": det_match,
            "rain_state_sha256": wet_sha,
            "repeat_state_sha256": rep_sha,
            "timeline_frames": len(eng_wet.timeline.frames),
        },
        "data_origins": {
            "flywire_v783": {"n_neurons": sub.n_neurons, "n_edges": sub.n_edges},
            "dwd_reference": eng_wet.world.dwd_weather_reference,
            "gbif_birds": {k: v.get("verified_occ_count", 0) for k, v in eng_wet.world.gbif_bird_records.items()},
            "gbif_extended_count": len(eng_wet.world.gbif_extended_records),
        },
        "dry_vs_rain_comparison_90s": dry_cmp,
        "diff_t10_to_t55": diff_10_55_compact,
        "diff_t10_to_t90": diff_10_90_compact,
        "causal_events_summary": {
            "total_events": len(ev_list),
            "non_reaction_events": len(nr_events),
            "non_reactions": [{"id": e["event_id"], "entity": e["entity_id"], "mechanism": e["mechanism"]} for e in nr_events],
            "sample_multi_hop_chain": sample_chain,
        },
        "protected_core_integrity": {"intact": intact, "pre": pre_snap, "post": post_snap},
    }
    sum_text = json.dumps(summary_payload, ensure_ascii=False, indent=2)
    if sum_text.count("\n") > 680:
        parts = ["{"]
        keys = list(summary_payload.keys())
        for i, k in enumerate(keys):
            comma = "," if i < len(keys) - 1 else ""
            parts.append(
                f'  {json.dumps(k, ensure_ascii=False)}: '
                f'{json.dumps(summary_payload[k], ensure_ascii=False, separators=(",", ": "))}{comma}'
            )
        parts.append("}")
        sum_text = "\n".join(parts)
    (RESULTS_DIR / "validation_observatory_summary.json").write_text(sum_text, encoding="utf-8")

    print("=== SIMALITAET OBSERVATORY VALIDATION COMPLETE ===")
    print(f"Wall Time (90s): {wet_wall_s:.2f}s ({rain_ms_tick:.2f} ms/tick) | Peak RSS: {rss_mb} MB | SHA match: {det_match}")
    print(f"Protected DB/DWD/Luanti intact: {intact} | Summary JSON bytes: {len(sum_text)}")
    print(f"Events logged: {len(ev_list)} (Non-reactions: {len(nr_events)})")
    print("Dry vs Rain 90s:", json.dumps(dry_cmp, ensure_ascii=False))
    return 0 if (intact and det_match and len(nr_events) >= 2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
