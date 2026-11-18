# -*- coding: utf-8 -*-
"""
Schritt 5: Hochauflösende Visualisierungen für SIMALITAET_ECOSYSTEM (Seestraße 43).

Erzeugt drei wissenschaftliche Dashboards ohne Überlappungen:
1. ecosystem_world_3d_and_niches.png
2. ecosystem_perspectives_and_neural.png
3. ecosystem_population_dynamics_and_experiments.png
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Rectangle
import numpy as np


SPECIES_COLORS = {
    "CYANISTES_CAERULEUS": "#1f77b4",
    "PARUS_MAJOR": "#2ca02c",
    "HIRUNDO_RUSTICA": "#d62728",
}

BIRD_ID_TO_SPECIES = {
    "BM_01": ("CYANISTES_CAERULEUS", "Blaumeise (BM_01)"),
    "KM_01": ("PARUS_MAJOR", "Kohlmeise (KM_01)"),
    "RS_01": ("HIRUNDO_RUSTICA", "Rauchschwalbe (RS_01)"),
}


def _draw_wireframe_box(ax, bmin: Tuple[float, float, float], bmax: Tuple[float, float, float], color: str, alpha: float = 0.65) -> None:
    x0, y0, z0 = bmin
    x1, y1, z1 = bmax
    corners = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ])
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    for a, b in edges:
        ax.plot(
            [corners[a, 0], corners[b, 0]],
            [corners[a, 1], corners[b, 1]],
            [corners[a, 2], corners[b, 2]],
            color=color,
            linewidth=1.1,
            alpha=alpha,
        )


def _draw_wireframe_ellipsoid(ax, center: Tuple[float, float, float], radii: Tuple[float, float, float], color: str = "#2d7f2d") -> None:
    u = np.linspace(0.0, 2.0 * np.pi, 18)
    v = np.linspace(0.0, np.pi, 10)
    x = center[0] + radii[0] * np.outer(np.cos(u), np.sin(v))
    y = center[1] + radii[1] * np.outer(np.sin(u), np.sin(v))
    z = center[2] + radii[2] * np.outer(np.ones_like(u), np.cos(v))
    ax.plot_wireframe(x, y, z, color=color, alpha=0.22, linewidth=0.6)


def render_world_3d_and_niches(report: Dict[str, Any], out_path: Path) -> None:
    """Erstellt Dashboard 1: 3D-Welt, Top-Down-Habitatkarte, Zonenteilung & Fangerfolg."""
    world_meta = report["world_metadata"]
    exp1 = report["experiments"]["eco_exp_1_baseline_150s"]
    tracks = exp1["tracks"]
    birds_summary = exp1["birds"]
    gbif = world_meta.get("gbif_woelfersheim_birds", {})

    fig = plt.figure(figsize=(17.0, 10.5), dpi=180, constrained_layout=True)
    gs = fig.add_gridspec(3, 2, width_ratios=[1.22, 1.0], height_ratios=[1.15, 0.9, 0.95])
    fig.suptitle(
        "SIMALITÄT_ECOSYSTEM (Seestraße 43): 3D-Weltgeometrie, Nischentrennung & Reale CPA-Jagdergebnisse",
        fontsize=14,
        fontweight="bold",
    )

    # Panel A: 3D-Szene über alle 3 Zeilen links
    ax3d = fig.add_subplot(gs[:, 0], projection="3d")
    _draw_wireframe_box(ax3d, (0.0, 0.0, 0.0), (11.0, 9.0, 8.2), "#4a4a4a", alpha=0.8)
    _draw_wireframe_box(ax3d, (5.5, 9.0, 0.0), (10.0, 12.5, 2.8), "#6e6e6e", alpha=0.6)
    ax3d.scatter([1.9], [0.15], [1.8], color="#ff9800", s=55, marker="D", label="Süd-Terrassenportal (Fliegen)")

    for can in world_meta["canopies"]:
        _draw_wireframe_ellipsoid(ax3d, tuple(can["center"]), tuple(can["radii"]), "#2e7d32")

    for bid, pts in tracks["birds"].items():
        if not pts:
            continue
        arr = np.asarray(pts, dtype=np.float64)
        sp_id, label_de = BIRD_ID_TO_SPECIES[bid]
        ax3d.plot(arr[:, 1], arr[:, 2], arr[:, 3], color=SPECIES_COLORS[sp_id], linewidth=1.25, alpha=0.82, label=label_de)

    for idx_f, (fid_str, fpts) in enumerate(list(tracks["flies_sample"].items())[:4]):
        farr = np.asarray(fpts, dtype=np.float64)
        ax3d.plot(
            farr[:, 1], farr[:, 2], farr[:, 3],
            color="#9c27b0", linestyle="--", linewidth=0.9, alpha=0.55,
            label="Fliegen-Trajektorien (Probe)" if idx_f == 0 else None,
        )

    catches = tracks["catch_events"]
    if catches:
        cpos = np.array([c["pos"] for c in catches])
        ax3d.scatter(cpos[:, 0], cpos[:, 1], cpos[:, 2], color="#ffd600", edgecolor="#000000", s=65, marker="*", zorder=8, label="Echte CPA-Fänge")
    misses = tracks["miss_events"]
    if misses:
        mpos = np.array([m["pos"] for m in misses])
        ax3d.scatter(mpos[:, 0], mpos[:, 1], mpos[:, 2], color="#424242", s=26, marker="x", zorder=7, label="Fehlschläge (Entkommen)")

    ax3d.set_xlim(-10, 22)
    ax3d.set_ylim(-12, 16)
    ax3d.set_zlim(0, 12)
    ax3d.set_xlabel("X [m] (Ost-West)")
    ax3d.set_ylabel("Y [m] (Nord-Süd)")
    ax3d.set_zlabel("Höhe Z [m]")
    ax3d.set_title("3D-Luftraum, Haus Seestraße 43, Baumkronen & Jagdpfade (150 s)", fontsize=11, pad=8)
    ax3d.view_init(elev=24, azim=-56)
    ax3d.legend(loc="upper left", fontsize=8, framealpha=0.9)

    # Panel B: Top-Down Grundriss & Zonen
    ax_xy = fig.add_subplot(gs[0, 1])
    ax_xy.add_patch(Rectangle((0.0, 0.0), 11.0, 9.0, facecolor="#e0e0e0", edgecolor="#333333", lw=1.4, label="Haus Seestr. 43 (Innen-Refugium)"))
    ax_xy.add_patch(Rectangle((5.5, 9.0), 4.5, 3.5, facecolor="#eeeeee", edgecolor="#555555", lw=1.1))
    ax_xy.text(5.5, 4.5, "Innenraum\n(Vogelbarriere)", ha="center", va="center", fontsize=8, color="#333333")

    for can in world_meta["canopies"]:
        c = can["center"]
        r = can["radii"]
        ax_xy.add_patch(Ellipse((c[0], c[1]), width=2 * r[0], height=2 * r[1], facecolor="#a5d6a7", edgecolor="#2e7d32", alpha=0.45, lw=1.2))
        lbl = can["canopy_id"].replace("CANOPY_", "").replace("SHRUB_", "")
        ly = (c[1] + r[1] + 0.55) if c[1] > 0 else (c[1] - r[1] - 0.85)
        ax_xy.text(
            c[0], ly, lbl,
            ha="center", va="center", fontsize=7.5, color="#1b5e20", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.82, ec="none"),
        )

    for sub in world_meta["substrates"]:
        sx, sy, _ = sub["pos"]
        ax_xy.scatter([sx], [sy], color="#e65100", s=28, marker="s", zorder=5)

    for bid, pts in tracks["birds"].items():
        if not pts:
            continue
        arr = np.asarray(pts, dtype=np.float64)
        sp_id, _ = BIRD_ID_TO_SPECIES[bid]
        ax_xy.plot(arr[:, 1], arr[:, 2], color=SPECIES_COLORS[sp_id], lw=1.05, alpha=0.75)

    if catches:
        cpos = np.array([c["pos"] for c in catches])
        ax_xy.scatter(cpos[:, 0], cpos[:, 1], color="#ffd600", edgecolor="#000000", s=55, marker="*", zorder=9)

    ax_xy.set_xlim(-11, 21)
    ax_xy.set_ylim(-13, 14)
    ax_xy.set_aspect("equal", adjustable="box")
    ax_xy.grid(True, linestyle=":", alpha=0.5)
    ax_xy.set_xlabel("X [m]")
    ax_xy.set_ylabel("Y [m]")
    ax_xy.set_title("Draufsicht: Haus-Refugium, Laubkronen, Substrate & Jagdreviere", fontsize=10.5)

    # Panel C: Zonenanteil je Vogelart
    ax_zn = fig.add_subplot(gs[1, 1])
    sp_order = ["CYANISTES_CAERULEUS", "PARUS_MAJOR", "HIRUNDO_RUSTICA"]
    sp_labels = ["Blaumeise\n(Cyanistes caeruleus)", "Kohlmeise\n(Parus major)", "Rauchschwalbe\n(Hirundo rustica)"]
    can_pct = [birds_summary[s]["zone_share_pct"]["canopy"] for s in sp_order]
    edge_pct = [birds_summary[s]["zone_share_pct"]["edge_ground"] for s in sp_order]
    open_pct = [birds_summary[s]["zone_share_pct"]["open_air"] for s in sp_order]
    y_pos = np.arange(len(sp_order))
    h = 0.54
    ax_zn.barh(y_pos, can_pct, height=h, color="#2e7d32", label="Baumkrone (Canopy >= 0.25)")
    ax_zn.barh(y_pos, edge_pct, height=h, left=can_pct, color="#f9a825", label="Siedlungsrand & Boden (Z <= 2.4 m)")
    left2 = np.array(can_pct) + np.array(edge_pct)
    ax_zn.barh(y_pos, open_pct, height=h, left=left2, color="#1e88e5", label="Offener Luftraum (Open Air)")
    for i, (c_v, e_v, o_v) in enumerate(zip(can_pct, edge_pct, open_pct)):
        if c_v >= 10:
            ax_zn.text(c_v * 0.5, i, f"{c_v:.0f}%", va="center", ha="center", color="white", fontsize=8.5, fontweight="bold")
        if e_v >= 10:
            ax_zn.text(c_v + e_v * 0.5, i, f"{e_v:.0f}%", va="center", ha="center", color="#212121", fontsize=8.5, fontweight="bold")
        if o_v >= 10:
            ax_zn.text(c_v + e_v + o_v * 0.5, i, f"{o_v:.0f}%", va="center", ha="center", color="white", fontsize=8.5, fontweight="bold")
    ax_zn.set_yticks(y_pos, sp_labels, fontsize=9)
    ax_zn.set_xlim(0, 100)
    ax_zn.set_xlabel("Aufenthaltsanteil [%] über 150 s")
    ax_zn.set_title("Emergente räumliche Nischentrennung (ohne skriptierte Zonenregeln)", fontsize=10.5)
    ax_zn.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=3, fontsize=8, frameon=True)

    # Panel D: Fänge vs. Fehlschläge + Wölfersheim GBIF
    ax_cm = fig.add_subplot(gs[2, 1])
    x = np.arange(len(sp_order))
    w_bar = 0.34
    catches_v = [birds_summary[s]["catches"] for s in sp_order]
    misses_v = [birds_summary[s]["missed_strikes"] for s in sp_order]
    b1 = ax_cm.bar(x - w_bar / 2, catches_v, width=w_bar, color="#2e7d32", label="Erfolgreiche CPA-Fänge")
    b2 = ax_cm.bar(x + w_bar / 2, misses_v, width=w_bar, color="#c62828", label="Fehlschläge (Fliege entkommen)")
    for rect in b1:
        ax_cm.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.3, f"{int(rect.get_height())}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    for rect in b2:
        ax_cm.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.3, f"{int(rect.get_height())}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    short_labels = []
    for s in sp_order:
        sc = birds_summary[s]["scientific_name"]
        occ = gbif.get(sc, {}).get("verified_occ_count", 0)
        sr = 100.0 * birds_summary[s]["strike_success_rate"]
        short_labels.append(f"{birds_summary[s]['common_name_de']}\n(GBIF n={occ}, Quote {sr:.0f}%)")
    ax_cm.set_xticks(x, short_labels, fontsize=8.5)
    ax_cm.set_ylabel("Anzahl Ereignisse (150 s)")
    ax_cm.set_ylim(0, max(catches_v + misses_v + [4]) * 1.25)
    ax_cm.grid(axis="y", linestyle=":", alpha=0.5)
    ax_cm.set_title("Jagdbilanz je Vogelart & Verifikation über GBIF Wölfersheim", fontsize=10.5)
    ax_cm.legend(loc="upper right", fontsize=8)

    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def _pick_peak_fly_sample(fly_samples: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not fly_samples:
        return None
    with_birds = [s for s in fly_samples if len(s.get("visible_birds", [])) > 0]
    if with_birds:
        return max(
            with_birds,
            key=lambda s: max(b.get("theta_dot_rad_s", 0.0) + 0.02 * b.get("angular_diam_deg", 0.0) for b in s["visible_birds"]),
        )
    return fly_samples[len(fly_samples) // 2]


def _pick_peak_bird_sample(samples: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not samples:
        return None
    active = [s for s in samples if len(s.get("visible_flies", [])) > 0 and s.get("state") in ("STRIKE_ATTEMPT", "PURSUING")]
    if active:
        return max(active, key=lambda s: (1 if s["state"] == "STRIKE_ATTEMPT" else 0, s.get("r_visual_salience", 0.0), len(s["visible_flies"])))
    with_vis = [s for s in samples if len(s.get("visible_flies", [])) > 0]
    if with_vis:
        return max(with_vis, key=lambda s: s.get("r_visual_salience", 0.0))
    return samples[len(samples) // 2]


def render_perspectives_and_neural(report: Dict[str, Any], out_path: Path) -> None:
    """Erstellt Dashboard 2: Ego-Perspektiven von Fliege & allen 3 Vogelarten + Neuralspuren."""
    exp1 = report["experiments"]["eco_exp_1_baseline_150s"]
    persp = exp1["perspectives"]
    fly_samples: List[Dict[str, Any]] = persp["fly_samples"]
    bird_samples: Dict[str, List[Dict[str, Any]]] = persp["bird_samples"]

    fig, axes = plt.subplots(2, 3, figsize=(17.5, 10.5), dpi=180, constrained_layout=True)
    fig.suptitle(
        "Ego-Perspektiven (Fliege & alle 3 Vogelarten) und Echtzeit-Neurodynamik (FlyWire v783 + Vogel-Tectum)",
        fontsize=14,
        fontweight="bold",
    )

    # Panel (0,0): Ego-Perspektive Drosophila melanogaster
    ax_fly = axes[0, 0]
    f_peak = _pick_peak_fly_sample(fly_samples)
    ax_fly.axhline(0.0, color="#9e9e9e", lw=0.8, ls="--")
    ax_fly.axvline(0.0, color="#9e9e9e", lw=0.8, ls="--")
    if f_peak is not None:
        faz = float(f_peak.get("nearest_food_az_deg", 0.0))
        ax_fly.scatter([faz], [-8.0], color="#43a047", s=140, marker="^", edgecolor="#1b5e20", zorder=5, label=f"Duftquelle ({f_peak['nearest_food_dist_m']:.1f} m)")
        for b in f_peak.get("visible_birds", []):
            az = float(b["az_deg"])
            el = float(b["el_deg"])
            diam = max(2.0, float(b["angular_diam_deg"]))
            sp_c = SPECIES_COLORS.get(b["species"], "#d32f2f")
            ax_fly.scatter([az], [el], s=min(900.0, diam * 28.0), color=sp_c, alpha=0.55, edgecolor="black", lw=1.2, zorder=6)
            ax_fly.text(
                az, min(68.0, el + 8.0),
                f"{b['bird_id']} ({b['dist_m']:.1f} m)\nθ̇={b['theta_dot_rad_s']:.2f} rad/s",
                ha="center", va="bottom", fontsize=7.5, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.85, ec=sp_c),
            )
        ax_fly.set_title(
            f"Ego-Sicht Fliege #{f_peak['fly_id']} @ t={f_peak['sim_time_s']:.2f}s [{f_peak['fly_state']}]\n"
            f"DNp01={f_peak['neural_dnp01_escape']:.2f} | LC4={f_peak['neural_lc4_looming']:.2f} | E={f_peak['energy_mj']:.1f} mJ",
            fontsize=9.5,
        )
    else:
        ax_fly.set_title("Ego-Sicht Fliege (keine Probe)", fontsize=9.5)
    ax_fly.set_xlim(-185, 185)
    ax_fly.set_ylim(-75, 80)
    ax_fly.set_xlabel("Relativer Azimut [°] (0° = Flugrichtung)")
    ax_fly.set_ylabel("Elevation [°]")
    ax_fly.grid(True, linestyle=":", alpha=0.45)
    ax_fly.legend(loc="lower right", fontsize=7.5)

    # Panels (0,1), (0,2), (1,0): Ego-Perspektiven der 3 Vogelarten
    bird_panels = [
        (axes[0, 1], "BM_01", 19.0, "Blaumeise (BM_01)"),
        (axes[0, 2], "KM_01", 17.0, "Kohlmeise (KM_01)"),
        (axes[1, 0], "RS_01", 24.0, "Rauchschwalbe (RS_01)"),
    ]
    for ax_b, bid, bino_deg, b_title in bird_panels:
        bs_list = bird_samples.get(bid, [])
        b_peak = _pick_peak_bird_sample(bs_list)
        ax_b.axvspan(-bino_deg, bino_deg, color="#fff59d", alpha=0.35, label=f"Binokulare Fovea (±{bino_deg:.0f}°)")
        ax_b.axhline(0.0, color="#9e9e9e", lw=0.7, ls="--")
        ax_b.axvline(0.0, color="#9e9e9e", lw=0.7, ls="--")
        if b_peak is not None:
            locked_id = b_peak.get("locked_fly_id")
            vflies = b_peak.get("visible_flies", [])
            for vf in vflies:
                is_lock = (vf["fly_id"] == locked_id)
                ax_b.scatter(
                    [vf["az_deg"]], [vf["el_deg"]],
                    s=130 if is_lock else 55,
                    color="#d32f2f" if is_lock else "#1976d2",
                    marker="*" if is_lock else "o",
                    edgecolor="black", lw=0.9 if is_lock else 0.5,
                    alpha=0.95 if is_lock else 0.72,
                    zorder=7 if is_lock else 5,
                )
                if is_lock:
                    ax_b.text(
                        vf["az_deg"], min(52.0, vf["el_deg"] + 7.5),
                        f"Ziel #{vf['fly_id']} ({vf['dist_m']:.2f} m)\nSalienz={vf['salience']:.3f}",
                        ha="center", va="bottom", fontsize=7.5, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.88, ec="#d32f2f"),
                    )
            ax_b.set_title(
                f"Ego-Sicht {b_title} @ t={b_peak['sim_time_s']:.2f}s [{b_peak['state']}]\n"
                f"v={b_peak['speed_mps']:.1f} m/s | Sicht-Salienz={b_peak['r_visual_salience']:.2f} | E={b_peak['energy_j']:.1f} J",
                fontsize=9.5,
            )
        else:
            ax_b.set_title(f"Ego-Sicht {b_title}", fontsize=9.5)
        ax_b.set_xlim(-148, 148)
        ax_b.set_ylim(-65, 65)
        ax_b.set_xlabel("Blickfeld-Azimut [°] (0° = Schnabelachse)")
        ax_b.set_ylabel("Elevation [°]")
        ax_b.grid(True, linestyle=":", alpha=0.45)
        ax_b.legend(loc="lower right", fontsize=7.5)

    # Panel (1,1): FlyWire-v783 Echtzeit-Neurodynamik über Zeit
    ax_fn = axes[1, 1]
    if fly_samples:
        # Zeige repräsentatives 45-s-Fenster rund um die stärkste Fluchtaktivität
        ts_f = np.array([s["sim_time_s"] for s in fly_samples])
        orn = np.array([s["neural_orn_ester"] for s in fly_samples])
        lc4 = np.array([s["neural_lc4_looming"] for s in fly_samples])
        dnp = np.array([s["neural_dnp01_escape"] for s in fly_samples])
        steer = np.array([s["neural_dna02_steer_diff"] for s in fly_samples])
        idx_max_lc4 = int(np.argmax(lc4))
        t_center = ts_f[idx_max_lc4]
        mask = (ts_f >= max(0.0, t_center - 18.0)) & (ts_f <= t_center + 18.0)
        if mask.sum() < 5:
            mask = np.ones_like(ts_f, dtype=bool)
        ax_fn.plot(ts_f[mask], orn[mask], color="#2e7d32", lw=1.4, label="ORN Ester (Duftsensorik)")
        ax_fn.plot(ts_f[mask], lc4[mask], color="#e65100", lw=1.6, label="LC4/LPLC2 (Opt. Looming)")
        ax_fn.plot(ts_f[mask], dnp[mask], color="#b71c1c", lw=1.5, ls="--", label="DNp01 (Giant-Fiber-Sprung)")
        ax_fn.plot(ts_f[mask], 0.5 + steer[mask], color="#6a1b9a", lw=1.1, alpha=0.75, label="DNa02 L-R Steer (+0.5 Offset)")
        esc_t = [s["sim_time_s"] for s, m in zip(fly_samples, mask) if m and s["fly_state"] == "ESCAPING"]
        for et in esc_t[::2]:
            ax_fn.axvline(et, color="#ef5350", alpha=0.14, lw=3.0)
        ax_fn.set_ylim(-0.02, 1.05)
        ax_fn.set_xlabel("Simulationszeit [s]")
        ax_fn.set_ylabel("Normierte Feuerrate [0..1]")
        ax_fn.set_title("FlyWire v783 Neurodynamik (Fokusfliege, Ereignisfenster)", fontsize=10)
        ax_fn.grid(True, linestyle=":", alpha=0.45)
        ax_fn.legend(loc="upper right", fontsize=7.5)

    # Panel (1,2): Vogel-Tectum/Motorik-Signale im aktiven Jagdfenster
    ax_bn = axes[1, 2]
    for bid, sp_id, label_de in [
        ("BM_01", "CYANISTES_CAERULEUS", "Blaumeise Jagd-Gate"),
        ("KM_01", "PARUS_MAJOR", "Kohlmeise Jagd-Gate"),
        ("RS_01", "HIRUNDO_RUSTICA", "Rauchschwalbe Jagd-Gate"),
    ]:
        bs = bird_samples.get(bid, [])
        if not bs:
            continue
        tb = np.array([s["sim_time_s"] for s in bs])
        pur = np.array([s["r_pursuit_gate"] for s in bs])
        vis = np.array([s["r_visual_salience"] for s in bs])
        win = tb <= 60.0
        ax_bn.plot(tb[win], pur[win], color=SPECIES_COLORS[sp_id], lw=1.45, label=f"{label_de} (Pursuit)")
        ax_bn.plot(tb[win], vis[win], color=SPECIES_COLORS[sp_id], lw=0.95, ls=":", alpha=0.7)
    ax_bn.set_xlim(0, 60)
    ax_bn.set_ylim(-0.02, 1.32)
    ax_bn.set_xlabel("Simulationszeit [s] (erste 60 s)")
    ax_bn.set_ylabel("Aktivierung [0..1] (durchgezogen=Jagd, gepunktet=Sicht)")
    ax_bn.set_title("Vogel-Sensorik & Entscheidungs-Gates (Tectum -> Motorik)", fontsize=10)
    ax_bn.grid(True, linestyle=":", alpha=0.45)
    ax_bn.legend(loc="upper right", fontsize=7.6)

    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def render_population_dynamics_and_experiments(report: Dict[str, Any], out_path: Path) -> None:
    """Erstellt Dashboard 3: Populationsdynamik, Energiebudgets & Ablations-/Gilden-Experimente."""
    exp1 = report["experiments"]["eco_exp_1_baseline_150s"]
    ts = exp1["time_series"]
    comp = report["comparisons"]
    rt = report["runtime_summary"]

    t_arr = np.array([r["t_s"] for r in ts])
    f_tot = np.array([r["flies_alive"] for r in ts])
    f_in = np.array([r["flies_indoor"] for r in ts])
    f_can = np.array([r["flies_canopy"] for r in ts])
    f_op = np.array([r["flies_open_air"] for r in ts])
    births = np.array([r["births"] for r in ts])
    captured = np.array([r["captured"] for r in ts])

    fig, axes = plt.subplots(2, 2, figsize=(16.5, 10.2), dpi=180, constrained_layout=True)
    fig.suptitle(
        "Populationsdynamik, Energetische Rückkopplung & Kausale Ablationsexperimente (Eco-Exp 1 bis 4b)",
        fontsize=14,
        fontweight="bold",
    )

    # Panel A: 150s Fliegenpopulation nach Habitaten + Geburten/Fänge
    ax_pop = axes[0, 0]
    ax_pop.plot(t_arr, f_tot, color="#111111", lw=2.0, label="Lebende Fliegen (Gesamt)")
    ax_pop.plot(t_arr, f_in, color="#8d6e63", lw=1.5, ls="--", label="Innenraum-Refugium (Küche)")
    ax_pop.plot(t_arr, f_can, color="#2e7d32", lw=1.5, label="Baumkronen-Schutz (Canopy)")
    ax_pop.plot(t_arr, f_op, color="#0288d1", lw=1.5, label="Offener Luftraum & Terrasse")
    ax_pop2 = ax_pop.twinx()
    ax_pop2.plot(t_arr, births, color="#9c27b0", lw=1.2, ls=":", label="Kum. Geburten")
    ax_pop2.plot(t_arr, captured, color="#c62828", lw=1.2, ls="-.", label="Kum. Fänge")
    ax_pop2.set_ylabel("Kumulierte Ereignisse (Geburten / Fänge)", fontsize=9, color="#4a148c")
    ax_pop.set_xlabel("Simulationszeit [s]")
    ax_pop.set_ylabel("Anzahl lebender Fliegen")
    ax_pop.set_title("150-s-Fliegenpopulation: Refugialschutz vs. Prädation", fontsize=10.5)
    ax_pop.grid(True, linestyle=":", alpha=0.45)
    h1, l1 = ax_pop.get_legend_handles_labels()
    h2, l2 = ax_pop2.get_legend_handles_labels()
    ax_pop.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7.5, ncol=2)

    # Panel B: Vogel-Energiereserven [%] über 150s
    ax_en = axes[0, 1]
    for bid, sp_id, label_de in [
        ("BM_01", "CYANISTES_CAERULEUS", "Blaumeise (E_max=100 J)"),
        ("KM_01", "PARUS_MAJOR", "Kohlmeise (E_max=145 J)"),
        ("RS_01", "HIRUNDO_RUSTICA", "Rauchschwalbe (E_max=160 J)"),
    ]:
        e_max = exp1["birds"][sp_id]["energy_max_j"]
        e_pct = [100.0 * r["bird_energy_j"][bid] / e_max for r in ts]
        ax_en.plot(t_arr, e_pct, color=SPECIES_COLORS[sp_id], lw=1.7, label=label_de)
    ax_en.axhline(92.0, color="#757575", ls="--", lw=0.9, label="Sättigungsgrenze (92% -> Sitzwarte)")
    ax_en.set_xlim(0, exp1["duration_s"])
    ax_en.set_ylim(0, 105)
    ax_en.set_xlabel("Simulationszeit [s]")
    ax_en.set_ylabel("Energiespeicher [% von E_max]")
    ax_en.set_title("Energetische Rückkopplung: Flugkosten vs. realer Beutegewinn", fontsize=10.5)
    ax_en.grid(True, linestyle=":", alpha=0.45)
    ax_en.legend(loc="lower right", fontsize=8)

    # Panel C: Kontrollierte Sensorik-Ablationen bei t = 90s
    ax_ab = axes[1, 0]
    b90 = comp["baseline_at_90s"]
    e2 = comp["exp2_fly_looming_ablation"]
    e3 = comp["exp3_bird_vision_ablation"]
    cats = ["Basis (90 s)", "Eco-Exp 2:\nOhne Fliegen-Looming", "Eco-Exp 3:\n30% Vogel-Visus"]
    cap_vals = [b90["fly_total_captured"], e2["fly_total_captured"], e3["fly_total_captured"]]
    esc_vals = [b90["fly_total_escapes"], e2["fly_total_escapes"], 0]  # Note: Escapes in exp3 not in comp? Wait let's use direct exp3 metric!
    exp3_full = report["experiments"]["eco_exp_3_bird_vision_degraded_90s"]
    esc_vals[2] = exp3_full["fly_total_escapes"]
    x_c = np.arange(len(cats))
    w_c = 0.34
    r1 = ax_ab.bar(x_c - w_c / 2, cap_vals, width=w_c, color="#d32f2f", label="Gefangene Fliegen (90 s)")
    r2 = ax_ab.bar(x_c + w_c / 2, esc_vals, width=w_c, color="#1976d2", label="LC4/DNp01-Fluchtmanöver")
    for r in r1:
        ax_ab.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.8, f"{int(r.get_height())}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    for r in r2:
        ax_ab.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.8, f"{int(r.get_height())}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    ax_ab.set_xticks(x_c, cats, fontsize=8.5)
    ax_ab.set_ylim(0, max(cap_vals + esc_vals + [10]) * 1.24)
    ax_ab.set_ylabel("Ereignisse innerhalb 90 s")
    ax_ab.set_title("Kausaler Closed-Loop-Nachweis: Fliegen-Looming & Vogel-Visus", fontsize=10.5)
    ax_ab.grid(axis="y", linestyle=":", alpha=0.45)
    ax_ab.legend(loc="upper right", fontsize=8)

    # Panel D: Gilden-Perturbation (ohne Rauchschwalbe) + System-Statusbox
    ax_gp = axes[1, 1]
    e4b = comp["exp4_no_swallow_release"]
    labels_g = ["Fänge Gesamt\n(90 s)", "Überlebende\nFreilandfliegen (90 s)", "Blaumeise +\nKohlmeise Fänge"]
    base_bm_km = b90["catches_by_species"].get("CYANISTES_CAERULEUS", 0) + b90["catches_by_species"].get("PARUS_MAJOR", 0)
    nosw_bm_km = e4b["remaining_catches"].get("CYANISTES_CAERULEUS", 0) + e4b["remaining_catches"].get("PARUS_MAJOR", 0)
    v_base = [b90["fly_total_captured"], b90["open_air_flies"], base_bm_km]
    v_nosw = [e4b["fly_total_captured"], e4b["open_air_flies_alive"], nosw_bm_km]
    xg = np.arange(len(labels_g))
    g1 = ax_gp.bar(xg - 0.18, v_base, width=0.35, color="#37474f", label="Basis (alle 3 Arten)")
    g2 = ax_gp.bar(xg + 0.18, v_nosw, width=0.35, color="#fb8c00", label="Eco-Exp 4b (ohne Rauchschwalbe)")
    for r in g1:
        ax_gp.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.6, f"{int(r.get_height())}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    for r in g2:
        ax_gp.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.6, f"{int(r.get_height())}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
    ax_gp.set_xticks(xg, labels_g, fontsize=8.5)
    ax_gp.set_ylim(0, max(v_base + v_nosw + [10]) * 1.32)
    ax_gp.set_ylabel("Anzahl bei t = 90 s")
    ax_gp.set_title("Gilden-Perturbation (Eco-Exp 4b) & Determinismus/Budget", fontsize=10.5)
    ax_gp.grid(axis="y", linestyle=":", alpha=0.45)
    ax_gp.legend(loc="upper left", fontsize=8)

    det_txt = "PASS" if rt["determinism_verified"] else "FAIL"
    info_str = (
        f"Determinismus (SHA-256): {det_txt}\n"
        f"Hash: {b90['state_sha256'][:16]}...\n"
        f"Laufzeit/Tick: {rt['baseline_ms_per_tick']:.2f} ms (< 25 ms)\n"
        f"Peak RSS: {rt['peak_rss_mb']:.1f} MB (< 650 MB)"
    )
    ax_gp.text(
        0.98, 0.96, info_str,
        transform=ax_gp.transAxes, ha="right", va="top", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.35", fc="#e8f5e9" if rt["determinism_verified"] else "#ffebee", ec="#2e7d32", alpha=0.92),
    )

    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def generate_all_ecosystem_dashboards(
    report: Dict[str, Any],
    results_dir: Path,
    artifact_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """Erstellt alle drei Ökosystem-PNGs und kopiert sie optional ins Artifact-Verzeichnis."""
    results_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "world_3d_and_niches": "ecosystem_world_3d_and_niches.png",
        "perspectives_and_neural": "ecosystem_perspectives_and_neural.png",
        "population_dynamics_and_experiments": "ecosystem_population_dynamics_and_experiments.png",
    }
    out_paths: Dict[str, str] = {}
    renderers = {
        "world_3d_and_niches": render_world_3d_and_niches,
        "perspectives_and_neural": render_perspectives_and_neural,
        "population_dynamics_and_experiments": render_population_dynamics_and_experiments,
    }
    for key, fname in files.items():
        dst = results_dir / fname
        renderers[key](report, dst)
        out_paths[key] = str(dst)
        if artifact_dir is not None and artifact_dir.exists():
            art_dst = artifact_dir / fname
            art_dst.write_bytes(dst.read_bytes())
            out_paths[f"{key}_artifact"] = str(art_dst)
    return out_paths
