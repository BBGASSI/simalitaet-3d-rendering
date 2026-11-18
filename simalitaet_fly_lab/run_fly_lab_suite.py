# -*- coding: utf-8 -*-
"""
Hauptausführung & Verifikation für SIMALITAET_FLY_LAB (Seestraße 43).
Führt Phasen 3–7 vollständig reproduzierbar auf BELOW_NORMAL_PRIORITY_CLASS aus.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

from fly_lab.body_engine import FlyBodyEngine
from fly_lab.connectome import FlyWireConnectome
from fly_lab.malecns_adapter import MaleCNSReferenceAdapter
from fly_lab.neural_and_memory import FlyWireNeuralEngine
from fly_lab.research_lab import FlyResearchLab
from fly_lab.security_guards import (
    FLY_LAB_ROOT,
    FlyLabSecurityGuard,
    get_process_rss_mb,
    set_below_normal_priority,
)
from fly_lab.seestrasse_43_world import Seestrasse43World


RESULTS_DIR = FLY_LAB_ROOT / "results"
ARTIFACT_DIR = Path(r"C:\Users\Ulric\.gemini\antigravity\brain\fcf64b6a-aa55-49c4-9aac-05bbe2d54441")


def render_seestrasse_architecture_figure(
    world: Seestrasse43World,
    suite_res: dict,
    out_png: Path,
) -> None:
    plt.rcParams.update({"font.size": 8.5, "axes.titlesize": 10, "axes.titleweight": "bold"})
    fig, axes = plt.subplots(2, 2, figsize=(14.5, 11.2), dpi=160)
    fig.suptitle(
        "SIMALITAET_FLY_LAB — Deterministisches 3D-Testuniversum Seestraße 43 (Wölfersheim)\n"
        "Architektur (13 Räume + Anbau + 38°-Satteldach), Mikroklima, 8-Klassen-VOC-Fahnen & geschlossene FlyWire-v783-Trajektorien",
        fontsize=12,
        fontweight="bold",
        y=0.98,
    )

    exps = suite_res["experiments"]

    # --- Panel A: EG (Z = 0..2.6 m) + ANBAU_HEIZ + Essigsäure/Ester-Plume & Küche/Spalt-Trajektorien ---
    ax = axes[0, 0]
    iz_eg = 2  # z ~ 0.625 m
    voc_eg = (world.voc[1, :, :, iz_eg] + world.voc[2, :, :, iz_eg]).T
    im_a = ax.imshow(
        np.log1p(voc_eg),
        origin="lower",
        extent=[0.0, 11.0, 0.0, 12.5],
        cmap="YlOrRd",
        aspect="equal",
        alpha=0.92,
    )
    fig.colorbar(im_a, ax=ax, fraction=0.04, pad=0.02, label="log(1 + Ester + Essigsäure)")

    for r in world.rooms:
        if r.floor == "EG":
            for b in r.boxes:
                rect = patches.Rectangle((b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
                                         linewidth=1.3, edgecolor="#1b263b", facecolor="none")
                ax.add_patch(rect)
            cx = sum(0.5 * (b.x_min + b.x_max) for b in r.boxes) / len(r.boxes)
            cy = sum(0.5 * (b.y_min + b.y_max) for b in r.boxes) / len(r.boxes)
            if r.room_id == "EG_SPEIS":
                cx, cy = 7.30, 6.45
            elif r.room_id == "EG_KUECHE":
                cx, cy = 7.45, 3.05
            ax.text(cx, cy, r.room_id, ha="center", va="center", fontsize=7.5, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white", alpha=0.80, edgecolor="none"))

    # Luftstrom-Quiver im EG
    step_q = 5
    ax.quiver(world.xc[::step_q], world.yc[::step_q],
              world.vel[0, ::step_q, ::step_q, iz_eg].T, world.vel[1, ::step_q, ::step_q, iz_eg].T,
              color="#0b5394", alpha=0.55, scale=0.85, width=0.003)

    # FOOD Quellen EG
    food_label_offsets = {
        "FOOD_01": (0.0, -0.45),
        "FOOD_02": (0.0, 0.35),
        "FOOD_03": (0.0, -0.42),
        "FOOD_04": (0.0, -0.45),
        "FOOD_06": (0.0, -0.45),
        "FOOD_08": (-0.65, 0.25),
    }
    for f in world.foods:
        if f.floor == "EG":
            ax.scatter(f.x, f.y, s=65, color="#198754", edgecolor="black", zorder=5)
            dx_l, dy_l = food_label_offsets.get(f.food_id, (0.0, -0.38))
            ax.text(f.x + dx_l, f.y + dy_l, f.food_id, fontsize=7, ha="center", fontweight="bold", color="#0d3b26",
                    bbox=dict(boxstyle="round,pad=0.08", facecolor="white", alpha=0.72, edgecolor="none"))

    # Markiere Türspalte 1,5 cm und 2,0 cm
    ax.plot([6.90, 7.75], [4.00, 4.00], color="#00bcd4", linewidth=3.2, label="1,5 cm Spalt EG_SPEIS")
    ax.plot([6.80, 7.70], [8.88, 8.88], color="#ff5722", linewidth=3.2, label="2,0 cm Spalt ANBAU_HEIZ")

    traj_k = np.array(exps["exp_2_chemotaxis"]["eg_kitchen_intact"]["trajectory_sample"])
    if len(traj_k):
        ax.plot(traj_k[:, 0], traj_k[:, 1], color="#111111", linewidth=1.8, linestyle="-", label="Chemotaxis EG_KUECHE")
    traj_p = np.array(exps["exp_1_phototaxis"]["intact"]["trajectory_sample"])
    if len(traj_p):
        ax.plot(traj_p[:, 0], traj_p[:, 1], color="#2563eb", linewidth=1.6, linestyle="--", label="Phototaxis Südfenster")

    ax.set_xlim(0.0, 11.0)
    ax.set_ylim(0.0, 12.5)
    ax.set_title("A. Erdgeschoss & Heizungsanbau: Ester-Plume, Türspalte & Trajektorien")
    ax.set_xlabel("X [m] (West → Ost)")
    ax.set_ylabel("Y [m] (Süd → Nord)")
    ax.legend(loc="upper left", fontsize=7, framealpha=0.88)

    # --- Panel B: OG (Z = 2.8..5.3 m) Geosmin (DA2) vs Durst in OG_BAD_2 ---
    ax = axes[0, 1]
    iz_og = 14  # z ~ 3.625 m
    geo_og = world.voc[4, :, :36, iz_og].T
    hum_og = world.humidity_pct[:, :36, iz_og].T
    ax.imshow(hum_og, origin="lower", extent=[0.0, 11.0, 0.0, 9.0], cmap="PuBu", vmin=40, vmax=95, alpha=0.75, aspect="equal")
    cs_geo = ax.contour(world.xc, world.yc[:36], geo_og, levels=[0.25, 0.75, 1.5, 2.3], colors="#9b2226", linewidths=1.2)
    ax.clabel(cs_geo, fmt="Geo %.1f", fontsize=6.5)

    for r in world.rooms:
        if r.floor == "OG":
            for b in r.boxes:
                ax.add_patch(patches.Rectangle((b.x_min, b.y_min), b.x_max - b.x_min, b.y_max - b.y_min,
                                               linewidth=1.3, edgecolor="#1b263b", facecolor="none"))
            cx = sum(0.5 * (b.x_min + b.x_max) for b in r.boxes) / len(r.boxes)
            cy = sum(0.5 * (b.y_min + b.y_max) for b in r.boxes) / len(r.boxes)
            if r.room_id == "OG_BAD_2":
                cx, cy = 4.90, 6.35
            ax.text(cx, cy, r.room_id, ha="center", va="center", fontsize=7.5, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white", alpha=0.78, edgecolor="none"))

    for f in world.foods:
        if f.floor == "OG":
            c = "#c1121f" if f.is_aversive else "#198754"
            ax.scatter(f.x, f.y, s=70, color=c, edgecolor="black", zorder=5)
            ax.text(f.x, f.y - 0.42, f.food_id, fontsize=7, ha="center", fontweight="bold", color=c)

    t_geo_on = np.array(exps["exp_5_environment_and_conflict"]["hydrated_geosmin_intact"]["trajectory_sample"])
    t_geo_off = np.array(exps["exp_5_environment_and_conflict"]["dehydrated_da2_silenced"]["trajectory_sample"])
    if len(t_geo_on):
        ax.plot(t_geo_on[:, 0], t_geo_on[:, 1], color="#d90429", linewidth=2.0, label="DA2 intakt (Geosmin-Flucht)")
    if len(t_geo_off):
        ax.plot(t_geo_off[:, 0], t_geo_off[:, 1], color="#0a9396", linewidth=1.8, linestyle="--", label="DA2 abliert (Annäherung)")
    ax.set_xlim(0.0, 11.0)
    ax.set_ylim(0.0, 9.0)
    ax.set_title("B. Obergeschoss: Feuchtefeld, Geosmin-Kontur & Exp-5 Valenzkonflikt")
    ax.set_xlabel("X [m]")
    ax.set_ylabel("Y [m]")
    ax.legend(loc="lower left", fontsize=7.5, framealpha=0.9)

    # --- Panel C: Vertikalschnitt (Ost-Treppenhaus Y ~ 6.1 m) + Temperatur T(x,z) + Abstieg OG -> EG ---
    ax = axes[1, 0]
    iy_stair = 24  # y = 6.125 m (mitten durch Ost-Treppenhaus)
    T_xz = np.where(world.air_mask[:, iy_stair, :], world.temp_c[:, iy_stair, :], np.nan).T
    im_t = ax.imshow(T_xz, origin="lower", extent=[0.0, 11.0, 0.0, 8.25], cmap="coolwarm", vmin=16.5, vmax=26.5, aspect="auto")
    fig.colorbar(im_t, ax=ax, fraction=0.04, pad=0.02, label="Temperatur T [°C]")
    ax.quiver(world.xc[::4], world.zc[::3],
              world.vel[0, ::4, iy_stair, ::3].T, world.vel[2, ::4, iy_stair, ::3].T,
              color="#111111", alpha=0.6, scale=1.2)
    t_stair = np.array(exps["exp_2_chemotaxis"]["og_stairwell_intact"]["trajectory_sample"])
    if len(t_stair):
        ax.plot(t_stair[:, 0], t_stair[:, 2], color="#ffd166", linewidth=2.5, path_effects=[], label="Exp 2 Abstieg OG_FLUR → EG")
        ax.scatter([t_stair[0, 0]], [t_stair[0, 2]], s=60, color="lime", edgecolor="black", zorder=6, label="Start OG_FLUR")
    ax.axhline(2.8, color="#333333", linestyle=":", linewidth=1.0)
    ax.axhline(5.6, color="#333333", linestyle=":", linewidth=1.0)
    ax.axvline(8.35, color="#1d3557", linestyle="--", linewidth=1.2, label="Ost-Treppenhaus (2,4x3,8 m)")
    ax.set_title("C. Vertikalschnitt (Y=6,1 m): Thermik-Kamineffekt, Geschosse & Abstieg")
    ax.set_xlabel("X [m]")
    ax.set_ylabel("Höhe Z [m]")
    ax.legend(loc="upper left", fontsize=7.5, framealpha=0.9)

    # --- Panel D: Mikroklimalandschaft der 13 Räume (T, H, UV-A) ---
    ax = axes[1, 1]
    r_ids = [r.room_id for r in world.rooms]
    t_vals, h_vals, l_vals = [], [], []
    for r_i, _ in enumerate(world.rooms):
        m = world.room_idx_grid == r_i
        t_vals.append(float(world.temp_c[m].mean()) if m.any() else 0.0)
        h_vals.append(float(world.humidity_pct[m].mean()) if m.any() else 0.0)
        l_vals.append(float(world.light[0, m].mean()) * 100.0 if m.any() else 0.0)
    x_i = np.arange(len(r_ids))
    w_bar = 0.27
    ax.bar(x_i - w_bar, t_vals, width=w_bar, label="Temp. [°C]", color="#e76f51")
    ax.bar(x_i, h_vals, width=w_bar, label="Feuchte [%]", color="#2a9d8f")
    ax.bar(x_i + w_bar, l_vals, width=w_bar, label="UV-A x100", color="#e9c46a")
    ax.set_xticks(x_i)
    ax.set_xticklabels(r_ids, rotation=42, ha="right", fontsize=7.5)
    ax.set_title("D. Gemessene Raum-Mittelwerte über alle 13 Räume der Seestraße 43")
    ax.set_ylabel("Messwert")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def render_experiments_dashboard(suite_res: dict, out_png: Path) -> None:
    plt.rcParams.update({"font.size": 8.5, "axes.titlesize": 9.8, "axes.titleweight": "bold"})
    fig, axes = plt.subplots(2, 3, figsize=(15.5, 9.6), dpi=160)
    fig.suptitle(
        "SIMALITAET_FLY_LAB — Ergebnisse aller 6 reproduzierbaren Experimente in Seestraße 43 (inkl. Ablationskontrollen)",
        fontsize=12,
        fontweight="bold",
        y=0.98,
    )
    exps = suite_res["experiments"]

    # Exp 1: Phototaxis
    ax = axes[0, 0]
    e1 = exps["exp_1_phototaxis"]
    bars = [e1["intact"]["mean_light_uv_exposed"], e1["vision_ablated_control"]["mean_light_uv_exposed"]]
    ax.bar(["MeTu Intakt", "Vision Abliert"], bars, color=["#f4a261", "#8d99ae"])
    ax.set_title(f"Exp 1: Phototaxis ({e1['status']})")
    ax.set_ylabel("Mittlere UV-A-Exposition [a.u.]")
    ax.text(0, bars[0] + 0.005, f"Dist Süd={e1['dist_to_south_window_intact_m']} m", ha="center", fontsize=7.5)
    ax.text(1, bars[1] + 0.005, f"Dist Süd={e1['dist_to_south_window_blind_m']} m", ha="center", fontsize=7.5)
    ax.grid(axis="y", alpha=0.3)

    # Exp 2: Neural Trace in FlyWire v783 + Chemotaxis
    ax = axes[0, 1]
    e2 = exps["exp_2_chemotaxis"]
    trace = e2["neural_trace_sample"]
    ts = [i * 0.25 for i in range(len(trace))]
    ax.plot(ts, [x["mean_orn_ester"] for x in trace], label="ORN_DM1/2/VA2", color="#2a9d8f", linewidth=1.8)
    ax.plot(ts, [x["mean_kc"] for x in trace], label="Kenyon Cells", color="#264653", linewidth=1.5)
    ax.plot(ts, [x["mean_looming_lc4"] for x in trace], label="LC4/LPLC2 Looming", color="#e76f51", linewidth=1.4)
    ax.set_title(f"Exp 2: FlyWire-Aktivität & Chemotaxis ({e2['status']})")
    ax.set_xlabel("Zeit [s]")
    ax.set_ylabel("Mittl. normierte Feuerrate [0..1]")
    ax.legend(fontsize=7.5, loc="upper right")
    ax.grid(alpha=0.3)

    # Exp 3: Wall Collisions & 1.5 cm EG_SPEIS Gap
    ax = axes[0, 2]
    e3 = exps["exp_3_obstacle_and_gap"]
    ax.bar(["LC4/LPLC2 Intakt", "Looming Abliert"],
           [e3["lc4_intact"]["wall_collisions"], e3["looming_ablated_control"]["wall_collisions"]],
           color=["#1d3557", "#e63946"])
    ax.set_title(f"Exp 3: Hindernisvermeidung & 1,5 cm Spalt ({e3['status']})")
    ax.set_ylabel("Wandkollisionen [Anzahl]")
    ax.text(0.5, max(1, e3["looming_ablated_control"]["wall_collisions"]) * 0.55,
            f"EG_SPEIS 1,5 cm\nSpalt passiert:\n{e3['speis_1_5cm_gap_entered']} ({e3['speis_gap_traversals']}x)",
            ha="center", bbox=dict(boxstyle="round", facecolor="#e9ecef", edgecolor="#495057"), fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # Exp 4: Body Coordination & Energy Balance
    ax = axes[1, 0]
    e4 = exps["exp_4_body_coordination"]["walk_feed_trial"]
    eb = e4["energy_hydration_balance"]
    b_l = ax.bar(["Tripod A Duty", "Tripod B Duty"], [e4["tarsal_stance_duty_a"], e4["tarsal_stance_duty_b"]],
                 color=["#457b9d", "#1d3557"])
    ax2 = ax.twinx()
    b_r = ax2.bar(["Aufgenommen [mJ]", "Verbrauch [mJ]"], [eb["ingested_energy_mj"], eb["metabolic_spent_mj"]],
                  color=["#2a9d8f", "#e76f51"], alpha=0.82)
    ax.set_ylim(0, 0.85)
    ax2.set_ylim(0, max(0.5, eb["ingested_energy_mj"] * 1.25))
    ax.text(0, e4["tarsal_stance_duty_a"] + 0.02, f"{e4['tarsal_stance_duty_a']:.3f}", ha="center", fontsize=7.5)
    ax.text(1, e4["tarsal_stance_duty_b"] + 0.02, f"{e4['tarsal_stance_duty_b']:.3f}", ha="center", fontsize=7.5)
    ax2.text(2, eb["ingested_energy_mj"] + 0.08, f"{eb['ingested_energy_mj']:.3f}", ha="center", fontsize=7.5)
    ax2.text(3, eb["metabolic_spent_mj"] + 0.08, f"{eb['metabolic_spent_mj']:.4f}", ha="center", fontsize=7.5)
    ax.set_title(f"Exp 4: Körperkoordination & Energie ({exps['exp_4_body_coordination']['status']})")
    ax.set_ylabel("Stance-Anteil [0..1]")
    ax2.set_ylabel("Energie [mJ]")
    ax.tick_params(axis="x", labelsize=7.5)

    # Exp 5: DA2 Geosmin vs Thirst Conflict
    ax = axes[1, 1]
    e5 = exps["exp_5_environment_and_conflict"]
    ax.bar(["DA2 Intakt (hydr.)", "DA2 Abliert (durstig)"],
           [e5["min_dist_food09_da2_intact_m"], e5["min_dist_food09_da2_silenced_m"]],
           color=["#9b2226", "#0a9396"])
    ax.set_title(f"Exp 5: Geosmin-DA2 vs Durst FOOD_09 ({e5['status']})")
    ax.set_ylabel("Minimalabstand zu Geosmin [m] (kleiner = Annäherung)")
    ax.grid(axis="y", alpha=0.3)

    # Exp 6: Short-Term MB Plasticity Retention Curve vs Frozen
    ax = axes[1, 2]
    e6 = exps["exp_6_learning_and_forgetting"]
    curve = e6["retention_valence_curve"]
    labels = ["10 s", "60 s", "300 s", "1800 s", "Frozen"]
    feed_s = [
        e6["trial_10s_plasticity_on"]["feeding_time_by_food_s"]["FOOD_02"],
        e6["trial_60s_plasticity_on"]["feeding_time_by_food_s"]["FOOD_02"],
        e6["trial_300s_plasticity_on"]["feeding_time_by_food_s"]["FOOD_02"],
        e6["trial_1800s_plasticity_on"]["feeding_time_by_food_s"]["FOOD_02"],
        e6["trial_frozen_control"]["feeding_time_by_food_s"]["FOOD_02"],
    ]
    ax.bar(labels, feed_s, color=["#d90429", "#ef233c", "#f4a261", "#2a9d8f", "#457b9d"])
    ax.set_title(f"Exp 6: MB-Kurzzeitlernen & Vergessen ({e6['status']})")
    ax.set_ylabel("Rüssel-Fresszeit FOOD_02 [s] (nach Aversion)")
    ax.text(0.5, max(feed_s) * 0.82, f"Valenz(10s)={curve['t_10s']:.2f}\nValenz(1800s)={curve['t_1800s']:.4f}\n(Kein LTM)",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85), fontsize=7.5)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def main() -> None:
    set_below_normal_priority()
    t_start = time.perf_counter()
    guard = FlyLabSecurityGuard()
    pre_snapshot = guard.snapshot_protected_state()

    # Phase 3: Reales FlyWire-v783-Konnektom + MaleCNS-Adapter
    conn = FlyWireConnectome(guard=guard)
    conn.export_summary(RESULTS_DIR / "connectome_summary.json")
    sub = conn.extract_sensorimotor_subcircuit()
    full_brain_check = FlyWireNeuralEngine.run_full_brain_spike_propagation_check(conn, n_steps=20)
    malecns_sample = MaleCNSReferenceAdapter.build_deterministic_vnc_bridge_sample().metadata_summary()

    # Phase 4: Deterministisches 3D-Testuniversum Seestraße 43
    world = Seestrasse43World(guard=guard)
    world.export_schema(RESULTS_DIR / "seestrasse_43_schema.json")

    # Phase 5 & 6: Geschlossener Regelkreis & Experimente 1–6
    lab = FlyResearchLab(conn, sub, world, guard=guard)
    suite_res = lab.run_all_six_experiments()

    # Visualisierungen rendern & ins Artefaktverzeichnis kopieren
    fig1_path = RESULTS_DIR / "seestrasse_43_fly_lab_architecture_and_plumes.png"
    fig2_path = RESULTS_DIR / "simalitaet_fly_lab_experiments_01_06.png"
    render_seestrasse_architecture_figure(world, suite_res, fig1_path)
    render_experiments_dashboard(suite_res, fig2_path)
    if ARTIFACT_DIR.exists():
        shutil.copy2(fig1_path, ARTIFACT_DIR / fig1_path.name)
        shutil.copy2(fig2_path, ARTIFACT_DIR / fig2_path.name)

    post_snapshot = guard.snapshot_protected_state()
    luanti_code_unchanged = (
        pre_snapshot["luanti_code_latest_mtime"] == post_snapshot["luanti_code_latest_mtime"]
        and pre_snapshot["woelfersheim_db_sha256"] == post_snapshot["woelfersheim_db_sha256"]
    )
    probe_body = FlyBodyEngine()

    validation = {
        "schema_id": "SIMALITAET_FLY_LAB_VALIDATION_V1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime_s": round(time.perf_counter() - t_start, 2),
        "peak_or_final_rss_mb": get_process_rss_mb(),
        "physics_backend": probe_body.physics_backend,
        "mujoco_status": probe_body.mujoco_status,
        "neuromechfly_morphology": {
            "source_xml": probe_body.morphology.source_xml,
            "n_bodies": probe_body.morphology.n_bodies,
            "n_joints": probe_body.morphology.n_joints,
        },
        "connectome_full_brain_check": full_brain_check,
        "subcircuit_neurons": int(sub.w_sub.shape[0]),
        "subcircuit_edges": int(sub.w_sub.nnz),
        "malecns_adapter": malecns_sample,
        "woelfersheim_anchor": world.anchor_record,
        "protected_integrity": {
            "pre_snapshot": pre_snapshot,
            "post_snapshot": post_snapshot,
            "protected_code_and_db_intact": luanti_code_unchanged,
        },
        **suite_res,
    }
    guard.safe_write_text(RESULTS_DIR / "validation_fly_lab.json", json.dumps(validation, indent=2, ensure_ascii=False))
    print(f"SUITE FINISHED in {validation['runtime_s']}s | RSS={validation['peak_or_final_rss_mb']} MB | Protected intact={luanti_code_unchanged}")
    for k, v in validation["experiments"].items():
        if isinstance(v, dict) and "status" in v:
            print(f"  {k:34s}: {v['status']}")


if __name__ == "__main__":
    main()
