# -*- coding: utf-8 -*-
"""
Schritt 1: Gemeinsame 3D-Welt Seestraße 43 + Garten + Luftraum (36 x 36 x 18 m).

Integriert:
- Das solide Seestraße-43-Haus (11,0 x 9,0 m + Nord-Anbau 4,5 x 3,5 m, Z 0..8,2 m):
  für Vögel unpassierbare Sicht- und Flugbarriere, für Fliegen über das offene
  Süd-Terrassentür-/Küchenfenster-Portal (X in [1.0, 2.8], Z in [1.4, 2.2]) als
  Innenraum-Refugium mit Innen-Nahrungsquelle betretbar.
- Realen Read-Only-Zugriff (?mode=ro + SQLITE_DENY) auf:
  * HOME_SEESTRASSE_43 in grossgemeinde_woelfersheim.sqlite3
  * reale Wölfersheimer GBIF-Vorkommen von Cyanistes caeruleus (19), Parus major (20)
    und Hirundo rustica (5) aus simalitaet_biodiversitaet.sqlite3.
- 3D-Baumkronen & Hecken mit räumlichem Dichteprofil und analytischer
  Sichtlinien-Transmittanz (Ray-Box Hausokklusion + Ray-Ellipsoid Laubdämpfung).
- Artspezifische Sitzwarten (Feinzweige / Äste & Geländer / Dachfirst & Leitung).
- Gekoppelte Nahrungs- & Brutsubstrate + thermische Aufwinde über Terrasse/Kompost.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..security_guards import (
    BIODIV_DB_PATH,
    WOELFERSHEIM_DB_PATH,
    FlyLabSecurityGuard,
)


@dataclass(frozen=True)
class TreeCanopy:
    canopy_id: str
    label_de: str
    center: Tuple[float, float, float]
    radii: Tuple[float, float, float]      # rx, ry, rz [m]
    outer_density: float                   # Laubdichte im äußeren Mantel (0..1)
    core_density: float                    # Laubdichte im inneren Kern (0..1)
    kappa_attenuation: float               # Optischer Dämpfungskoeffizient [1/m]

    def density_at(self, pos: np.ndarray) -> float:
        dx = (float(pos[0]) - self.center[0]) / self.radii[0]
        dy = (float(pos[1]) - self.center[1]) / self.radii[1]
        dz = (float(pos[2]) - self.center[2]) / self.radii[2]
        r2 = dx * dx + dy * dy + dz * dz
        if r2 > 1.0:
            return 0.0
        if r2 <= 0.36:
            return self.core_density
        # Sanfter Übergang zwischen Kern (r=0.6) und Außenmantel (r=1.0)
        frac = (math.sqrt(r2) - 0.6) / 0.4
        return self.core_density * (1.0 - frac) + self.outer_density * frac


@dataclass(frozen=True)
class PerchNode:
    perch_id: str
    kind: str               # "fine_twig", "branch_or_rail", "roof_eave_wire"
    preferred_species: Tuple[str, ...]
    pos: Tuple[float, float, float]
    radius_m: float


@dataclass
class EcosystemSubstrate:
    substrate_id: str
    label_de: str
    zone: str               # "INDOOR_REFUGE", "CANOPY_CROWN", "TERRACE_OPEN", "COMPOST_EDGE", "SHRUB_EDGE"
    pos: Tuple[float, float, float]
    radius_m: float
    voc_strength: float
    nutrients: float
    max_nutrients: float
    regen_per_s: float
    canopy_cover: float     # Typische Schutzwirkung am Substrat

    def feed_and_consume(self, amount: float) -> float:
        taken = min(self.nutrients, amount)
        self.nutrients = max(0.0, self.nutrients - taken)
        return taken


class Seestrasse43EcosystemWorld:
    """Geteilte 3D-Welt für Fliegen und drei Vogelarten rund um Seestraße 43."""

    # Weltgrenzen [m]: Haus liegt in X=[0,11], Y=[0,12.5], Z=[0,8.2]
    BOUNDS_MIN: Tuple[float, float, float] = (-12.0, -14.0, 0.0)
    BOUNDS_MAX: Tuple[float, float, float] = (24.0, 22.0, 18.0)

    # Haupthaus + Nord-Anbau als solide AABBs (für Vögel und Sichtstrahlen undurchdringlich)
    HOUSE_BOX_MAIN: Tuple[Tuple[float, float, float], Tuple[float, float, float]] = (
        (0.0, 0.0, 0.0),
        (11.0, 9.0, 8.2),
    )
    HOUSE_BOX_ANNEX: Tuple[Tuple[float, float, float], Tuple[float, float, float]] = (
        (5.5, 9.0, 0.0),
        (10.0, 12.5, 2.8),
    )
    # Offenes Süd-Terrassen- & Küchen-Portal für Fliegen (Refugium-Ein-/Ausgang!)
    HOUSE_FLY_PORTAL_CENTER: Tuple[float, float, float] = (1.9, 0.15, 1.8)
    HOUSE_FLY_PORTAL_HALF: Tuple[float, float, float] = (0.95, 0.35, 0.45)

    def __init__(self, guard: Optional[FlyLabSecurityGuard] = None) -> None:
        self.guard = guard or FlyLabSecurityGuard()
        self.sim_time_s: float = 0.0
        self.daylight_uv_factor: float = 1.0  # Sonniger Frühsommernachmittag Wölfersheim

        self.woelfersheim_anchor, self.gbif_bird_records = self._load_readonly_empirical_anchors()
        self.canopies: List[TreeCanopy] = self._build_canopies()
        self.perches: List[PerchNode] = self._build_perches()
        self.substrates: List[EcosystemSubstrate] = self._build_substrates()

    def _load_readonly_empirical_anchors(self) -> Tuple[Dict[str, object], Dict[str, Dict[str, object]]]:
        anchor: Dict[str, object] = {"building_id": "HOME_SEESTRASSE_43", "verified_ro": False}
        if WOELFERSHEIM_DB_PATH.exists():
            con = self.guard.open_readonly_sqlite(WOELFERSHEIM_DB_PATH)
            try:
                row = con.execute(
                    "SELECT building_id, osm_way_id, street, housenumber, lat_deg, lon_deg, alt_nhn_m "
                    "FROM buildings WHERE building_id='HOME_SEESTRASSE_43'"
                ).fetchone()
                if row:
                    anchor.update(dict(row))
                    anchor["verified_ro"] = True
            finally:
                con.close()

        gbif: Dict[str, Dict[str, object]] = {}
        if BIODIV_DB_PATH.exists():
            con_b = self.guard.open_readonly_sqlite(BIODIV_DB_PATH)
            try:
                for sp in ("Cyanistes caeruleus", "Parus major", "Hirundo rustica"):
                    prof = con_b.execute(
                        "SELECT taxon_key, species, vernacular_de, total_count, recent_count, min_year, max_year, primary_habitat, licenses_used "
                        "FROM species_profiles WHERE species = ?",
                        (sp,),
                    ).fetchone()
                    occ = con_b.execute(
                        "SELECT COUNT(*), MIN(event_date), MAX(event_date), ROUND(AVG(dist_to_lake_m), 1) "
                        "FROM occurrences WHERE species = ?",
                        (sp,),
                    ).fetchone()
                    if prof:
                        d = dict(prof)
                        d["verified_occ_count"] = int(occ[0]) if occ else 0
                        d["first_date"] = occ[1] if occ else None
                        d["last_date"] = occ[2] if occ else None
                        d["avg_dist_lake_m"] = float(occ[3]) if (occ and occ[3] is not None) else 0.0
                        gbif[sp] = d
            finally:
                con_b.close()
        return anchor, gbif

    @staticmethod
    def _build_canopies() -> List[TreeCanopy]:
        return [
            TreeCanopy("CANOPY_APPLE_SW", "Alter Apfelbaum (Südwest)", (-4.5, -5.0, 4.1), (3.2, 3.0, 2.4), 0.36, 0.85, 0.65),
            TreeCanopy("CANOPY_PLUM_SE", "Pflaumenbaum (Südost)", (15.5, -4.5, 4.5), (3.4, 3.2, 2.5), 0.34, 0.82, 0.62),
            TreeCanopy("SHRUB_BERRY_W", "Beerenhecke (West)", (-6.0, 5.0, 1.6), (2.4, 3.5, 1.4), 0.42, 0.88, 0.72),
        ]

    @staticmethod
    def _build_perches() -> List[PerchNode]:
        return [
            # Blaumeise: Feinzweige in äußerer Baumkrone
            PerchNode("PERCH_APPLE_CROWN_E", "fine_twig", ("CYANISTES_CAERULEUS",), (-2.0, -4.2, 4.8), 0.3),
            PerchNode("PERCH_APPLE_CROWN_S", "fine_twig", ("CYANISTES_CAERULEUS",), (-4.5, -7.2, 4.2), 0.3),
            PerchNode("PERCH_PLUM_CROWN_W", "fine_twig", ("CYANISTES_CAERULEUS",), (12.8, -4.0, 5.2), 0.3),
            PerchNode("PERCH_PLUM_CROWN_N", "fine_twig", ("CYANISTES_CAERULEUS",), (15.2, -1.8, 4.6), 0.3),
            # Kohlmeise: Kräftige Äste, Terrassengeländer, Kompostzaun
            PerchNode("PERCH_TERRACE_RAIL", "branch_or_rail", ("PARUS_MAJOR", "CYANISTES_CAERULEUS"), (3.5, -1.2, 1.4), 0.3),
            PerchNode("PERCH_APPLE_LOW", "branch_or_rail", ("PARUS_MAJOR",), (-2.5, -2.6, 2.4), 0.3),
            PerchNode("PERCH_COMPOST_POST", "branch_or_rail", ("PARUS_MAJOR",), (12.2, 4.2, 1.8), 0.3),
            PerchNode("PERCH_BERRY_EDGE", "branch_or_rail", ("PARUS_MAJOR", "CYANISTES_CAERULEUS"), (-3.6, 4.8, 2.1), 0.3),
            # Rauchschwalbe: Hausdach-First/Traufe & hohe Freileitung
            PerchNode("PERCH_ROOF_RIDGE_W", "roof_eave_wire", ("HIRUNDO_RUSTICA",), (1.5, 4.5, 8.45), 0.3),
            PerchNode("PERCH_ROOF_RIDGE_E", "roof_eave_wire", ("HIRUNDO_RUSTICA",), (9.5, 4.5, 8.45), 0.3),
            PerchNode("PERCH_WIRE_SOUTH", "roof_eave_wire", ("HIRUNDO_RUSTICA",), (6.0, -10.5, 9.20), 0.3),
        ]

    @staticmethod
    def _build_substrates() -> List[EcosystemSubstrate]:
        return [
            EcosystemSubstrate("SUB_INDOOR_KITCHEN", "Seestraße 43 Küche (Obst/Biomüll)", "INDOOR_REFUGE", (8.8, 3.3, 0.7), 0.8, 2.8, 120.0, 120.0, 0.35, 1.0),
            EcosystemSubstrate("SUB_TERRACE_FRUIT", "Terrassentisch (Obstteller, sonnig)", "TERRACE_OPEN", (3.5, -2.5, 0.85), 0.7, 2.2, 90.0, 90.0, 0.25, 0.0),
            EcosystemSubstrate("SUB_COMPOST", "Garten-Komposter (Gärende Schalen)", "COMPOST_EDGE", (13.5, 5.5, 0.65), 0.9, 3.4, 150.0, 150.0, 0.45, 0.15),
            EcosystemSubstrate("SUB_APPLE_DROP", "Fallobst unter Apfelbaum", "CANOPY_CROWN", (-4.2, -5.2, 0.35), 0.8, 2.1, 100.0, 100.0, 0.30, 0.65),
            EcosystemSubstrate("SUB_PLUM_CROWN", "Reife Pflaumen in Baumkrone", "CANOPY_CROWN", (15.2, -4.2, 4.40), 0.8, 2.4, 110.0, 110.0, 0.30, 0.75),
            EcosystemSubstrate("SUB_BERRY_HEDGE", "Reife Beeren an Westhecke", "SHRUB_EDGE", (-5.8, 4.8, 1.50), 0.7, 1.7, 80.0, 80.0, 0.22, 0.70),
        ]

    def reset_dynamic_state(self) -> None:
        self.sim_time_s = 0.0
        for s in self.substrates:
            s.nutrients = s.max_nutrients

    def step(self, dt_s: float) -> None:
        self.sim_time_s += dt_s
        for s in self.substrates:
            if s.nutrients < s.max_nutrients:
                s.nutrients = min(s.max_nutrients, s.nutrients + s.regen_per_s * dt_s)

    @classmethod
    def is_inside_house(cls, pos: np.ndarray, margin: float = 0.0) -> bool:
        x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
        b1_min, b1_max = cls.HOUSE_BOX_MAIN
        if (b1_min[0] - margin <= x <= b1_max[0] + margin
                and b1_min[1] - margin <= y <= b1_max[1] + margin
                and b1_min[2] - margin <= z <= b1_max[2] + margin):
            return True
        b2_min, b2_max = cls.HOUSE_BOX_ANNEX
        if (b2_min[0] - margin <= x <= b2_max[0] + margin
                and b2_min[1] - margin <= y <= b2_max[1] + margin
                and b2_min[2] - margin <= z <= b2_max[2] + margin):
            return True
        return False

    @classmethod
    def near_house_portal(cls, pos: np.ndarray, tol: float = 0.25) -> bool:
        px, py, pz = cls.HOUSE_FLY_PORTAL_CENTER
        hx, hy, hz = cls.HOUSE_FLY_PORTAL_HALF
        return (
            abs(float(pos[0]) - px) <= hx + tol
            and abs(float(pos[1]) - py) <= hy + tol
            and abs(float(pos[2]) - pz) <= hz + tol
        )

    @classmethod
    def _is_inside_house_vec(cls, pos: np.ndarray, margin: float = 0.0) -> np.ndarray:
        """Vektorisierte Prüfung auf Hausinnenraum für N 3D-Punkte (shape=(N, 3))."""
        b1_min, b1_max = cls.HOUSE_BOX_MAIN
        in1 = (
            (pos[:, 0] >= b1_min[0] - margin) & (pos[:, 0] <= b1_max[0] + margin)
            & (pos[:, 1] >= b1_min[1] - margin) & (pos[:, 1] <= b1_max[1] + margin)
            & (pos[:, 2] >= b1_min[2] - margin) & (pos[:, 2] <= b1_max[2] + margin)
        )
        b2_min, b2_max = cls.HOUSE_BOX_ANNEX
        in2 = (
            (pos[:, 0] >= b2_min[0] - margin) & (pos[:, 0] <= b2_max[0] + margin)
            & (pos[:, 1] >= b2_min[1] - margin) & (pos[:, 1] <= b2_max[1] + margin)
            & (pos[:, 2] >= b2_min[2] - margin) & (pos[:, 2] <= b2_max[2] + margin)
        )
        return in1 | in2

    @classmethod
    def _near_house_portal_vec(cls, pos: np.ndarray, tol: float = 0.25) -> np.ndarray:
        """Vektorisierte Prüfung am offenen Süd-Terrassenportal (shape=(N, 3))."""
        px, py, pz = cls.HOUSE_FLY_PORTAL_CENTER
        hx, hy, hz = cls.HOUSE_FLY_PORTAL_HALF
        return (
            (np.abs(pos[:, 0] - px) <= hx + tol)
            & (np.abs(pos[:, 1] - py) <= hy + tol)
            & (np.abs(pos[:, 2] - pz) <= hz + tol)
        )

    @staticmethod
    def _segments_intersect_aabb_mat(
        pa: np.ndarray,
        pb: np.ndarray,
        bmin: Tuple[float, float, float],
        bmax: Tuple[float, float, float],
    ) -> np.ndarray:
        """Vektorisierte Slab-Methode für alle Paare (M, N) zwischen pa (M,3) und pb (N,3)."""
        d = pb[None, :, :] - pa[:, None, :]
        bmin_arr = np.asarray(bmin, dtype=np.float64)
        bmax_arr = np.asarray(bmax, dtype=np.float64)
        parallel = np.abs(d) < 1e-9
        safe_d = np.where(parallel, 1.0, d)
        inv = np.where(parallel, 0.0, 1.0 / safe_d)
        t1 = (bmin_arr - pa[:, None, :]) * inv
        t2 = (bmax_arr - pa[:, None, :]) * inv
        tmin_ax = np.minimum(t1, t2)
        tmax_ax = np.maximum(t1, t2)
        inside_par = (pa[:, None, :] >= bmin_arr) & (pa[:, None, :] <= bmax_arr)
        tmin_ax = np.where(parallel, np.where(inside_par, 0.0, 2.0), tmin_ax)
        tmax_ax = np.where(parallel, np.where(inside_par, 1.0, -1.0), tmax_ax)
        tmin = np.maximum(0.0, np.max(tmin_ax, axis=-1))
        tmax = np.minimum(1.0, np.min(tmax_ax, axis=-1))
        return tmax > tmin

    def compute_los_matrix(self, pos_a: np.ndarray, pos_b: np.ndarray) -> np.ndarray:
        """
        Vektorisierte (M, N)-Transmittanzmatrix [0..1] zwischen pos_a (M,3) und pos_b (N,3):
        identisch zur Skalarfunktion line_of_sight_transmittance (Haus-Okklusion + Beer-Lambert Laubdämpfung).
        """
        pa = np.asarray(pos_a, dtype=np.float64)
        pb = np.asarray(pos_b, dtype=np.float64)
        m, n = len(pa), len(pb)
        if m == 0 or n == 0:
            return np.ones((m, n), dtype=np.float32)

        in_a = self._is_inside_house_vec(pa, margin=-0.05)[:, None]
        in_b = self._is_inside_house_vec(pb, margin=-0.05)[None, :]
        diff_side = in_a != in_b
        portal_ok = self._near_house_portal_vec(pa, tol=1.2)[:, None] & self._near_house_portal_vec(pb, tol=1.2)[None, :]
        blocked = diff_side & (~portal_ok)

        both_in = in_a & in_b
        need_box = (~both_in) & (~portal_ok)
        if np.any(need_box):
            hit_main = self._segments_intersect_aabb_mat(pa, pb, *self.HOUSE_BOX_MAIN)
            hit_annex = self._segments_intersect_aabb_mat(pa, pb, *self.HOUSE_BOX_ANNEX)
            blocked = blocked | (need_box & (hit_main | hit_annex))

        d = pb[None, :, :] - pa[:, None, :]
        seg_len = np.linalg.norm(d, axis=-1)
        tau = np.zeros((m, n), dtype=np.float64)
        for c in self.canopies:
            inv_r = 1.0 / np.asarray(c.radii, dtype=np.float64)
            c_arr = np.asarray(c.center, dtype=np.float64)
            o = (pa - c_arr) * inv_r
            dc = d * inv_r
            a = np.sum(dc * dc, axis=-1)
            b = 2.0 * np.sum(o[:, None, :] * dc, axis=-1)
            q = np.sum(o * o, axis=-1)[:, None] - 1.0
            disc = b * b - 4.0 * a * q
            valid = (disc > 0.0) & (a >= 1e-12) & (seg_len >= 1e-6)
            if np.any(valid):
                sqrt_d = np.sqrt(np.where(valid, disc, 0.0))
                inv_2a = np.where(valid, 1.0 / (2.0 * np.where(valid, a, 1.0)), 0.0)
                t0 = np.maximum(0.0, (-b - sqrt_d) * inv_2a)
                t1 = np.minimum(1.0, (-b + sqrt_d) * inv_2a)
                dl = np.where(valid & (t1 > t0), (t1 - t0) * seg_len, 0.0)
                tau += c.kappa_attenuation * dl

        return np.where(blocked, 0.0, np.exp(-tau)).astype(np.float32)

    def canopy_density_at(self, pos: np.ndarray) -> float:
        return max((c.density_at(pos) for c in self.canopies), default=0.0)

    def max_canopy_density_vec(self, positions: np.ndarray) -> np.ndarray:
        """Vektorisierte Laubdichte (0..0,88) für N Positionen (shape=(N, 3))."""
        if len(positions) == 0:
            return np.zeros(0, dtype=np.float32)
        out = np.zeros(len(positions), dtype=np.float32)
        for c in self.canopies:
            dx = (positions[:, 0] - c.center[0]) / c.radii[0]
            dy = (positions[:, 1] - c.center[1]) / c.radii[1]
            dz = (positions[:, 2] - c.center[2]) / c.radii[2]
            r2 = dx * dx + dy * dy + dz * dz
            inside = r2 <= 1.0
            if np.any(inside):
                d_arr = np.zeros(len(positions), dtype=np.float32)
                core = r2 <= 0.36
                d_arr[core] = c.core_density
                shell = inside & (~core)
                if np.any(shell):
                    frac = (np.sqrt(r2[shell]) - 0.6) / 0.4
                    d_arr[shell] = c.core_density * (1.0 - frac) + c.outer_density * frac
                out = np.maximum(out, d_arr)
        return out

    @staticmethod
    def _segment_intersects_aabb(p0: np.ndarray, p1: np.ndarray, bmin: Tuple[float, float, float], bmax: Tuple[float, float, float]) -> bool:
        """Slab-Methode: prüft exakt, ob Sichtstrahl p0 -> p1 durch AABB verläuft."""
        d = p1 - p0
        tmin, tmax = 0.0, 1.0
        for ax in (0, 1, 2):
            if abs(float(d[ax])) < 1e-9:
                if p0[ax] < bmin[ax] or p0[ax] > bmax[ax]:
                    return False
            else:
                inv = 1.0 / float(d[ax])
                t1 = (bmin[ax] - float(p0[ax])) * inv
                t2 = (bmax[ax] - float(p0[ax])) * inv
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin = max(tmin, t1)
                tmax = min(tmax, t2)
                if tmin > tmax:
                    return False
        return tmax > tmin

    @staticmethod
    def _segment_ellipsoid_path_length(p0: np.ndarray, p1: np.ndarray, center: Tuple[float, float, float], radii: Tuple[float, float, float]) -> float:
        """Berechnet exakt die durchquerte Wegstrecke [m] innerhalb einer Baumkrone (Ellipsoid)."""
        c = np.asarray(center, dtype=np.float64)
        inv_r = 1.0 / np.asarray(radii, dtype=np.float64)
        o = (p0 - c) * inv_r
        d_raw = p1 - p0
        seg_len = float(np.linalg.norm(d_raw))
        if seg_len < 1e-6:
            return 0.0
        d = d_raw * inv_r
        a = float(np.dot(d, d))
        b = 2.0 * float(np.dot(o, d))
        q = float(np.dot(o, o)) - 1.0
        disc = b * b - 4.0 * a * q
        if disc <= 0.0 or a < 1e-12:
            return 0.0
        sqrt_d = math.sqrt(disc)
        t0 = max(0.0, (-b - sqrt_d) / (2.0 * a))
        t1 = min(1.0, (-b + sqrt_d) / (2.0 * a))
        if t1 <= t0:
            return 0.0
        return (t1 - t0) * seg_len

    def line_of_sight_transmittance(self, p_from: np.ndarray, p_to: np.ndarray) -> float:
        """
        Reale Sichttransparenz [0..1] zwischen zwei 3D-Punkten:
        - Haus Seestraße 43 blockiert Sicht vollständig (0,0), sofern nicht beide im Haus sind.
        - Laubkronen dämpfen Sicht exponentiell (Beer-Lambert exp(-kappa * d_foliage)).
        """
        in_a = self.is_inside_house(p_from, margin=-0.05)
        in_b = self.is_inside_house(p_to, margin=-0.05)
        portal_ok = self.near_house_portal(p_from, tol=1.2) and self.near_house_portal(p_to, tol=1.2)
        if in_a != in_b and not portal_ok:
            return 0.0
        if not (in_a and in_b) and not portal_ok:
            if self._segment_intersects_aabb(p_from, p_to, *self.HOUSE_BOX_MAIN) or self._segment_intersects_aabb(
                p_from, p_to, *self.HOUSE_BOX_ANNEX
            ):
                return 0.0

        tau = 0.0
        for c in self.canopies:
            dl = self._segment_ellipsoid_path_length(p_from, p_to, c.center, c.radii)
            if dl > 0.0:
                tau += c.kappa_attenuation * dl
        return float(math.exp(-tau))

    def wind_at(self, pos: np.ndarray) -> np.ndarray:
        """Thermikaufwinde über sonniger Südterrasse und Kompost tragen Insekten in den offenen Luftraum."""
        x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
        if self.is_inside_house(pos):
            return np.array([0.02, -0.02, 0.03], dtype=np.float32)
        # Südwest-Brise (0,4 m/s) + thermischer Auftrieb über Terrasse (3.5,-2.5) & Kompost (13.5,5.5)
        thermal_terr = math.exp(-((x - 3.5) ** 2 / 9.0 + (y + 2.5) ** 2 / 9.0))
        thermal_comp = math.exp(-((x - 13.5) ** 2 / 7.5 + (y - 5.5) ** 2 / 7.5))
        vz = 0.24 * (thermal_terr + 0.9 * thermal_comp) * math.exp(-max(0.0, z - 5.0) / 8.0)
        return np.array([0.32, 0.16, vz], dtype=np.float32)

    def wind_at_vec(self, positions: np.ndarray) -> np.ndarray:
        """Vektorisierte Thermik- & Brisenberechnung für N Positionen (shape=(N, 3))."""
        n = len(positions)
        if n == 0:
            return np.zeros((0, 3), dtype=np.float32)
        x = positions[:, 0]
        y = positions[:, 1]
        z = positions[:, 2]
        thermal_terr = np.exp(-((x - 3.5) ** 2 / 9.0 + (y + 2.5) ** 2 / 9.0))
        thermal_comp = np.exp(-((x - 13.5) ** 2 / 7.5 + (y - 5.5) ** 2 / 7.5))
        vz = 0.24 * (thermal_terr + 0.9 * thermal_comp) * np.exp(-np.maximum(0.0, z - 5.0) / 8.0)
        wind = np.empty((n, 3), dtype=np.float32)
        wind[:, 0] = 0.32
        wind[:, 1] = 0.16
        wind[:, 2] = vz
        in_house = self._is_inside_house_vec(positions)
        if np.any(in_house):
            wind[in_house, 0] = 0.02
            wind[in_house, 1] = -0.02
            wind[in_house, 2] = 0.03
        return wind

    def clamp_or_slide_fly(self, pos: np.ndarray, next_pos: np.ndarray) -> np.ndarray:
        """Erzwingt Weltgrenzen + Wandblockade des Hauses (Passage nur über Süd-Portal)."""
        cand = np.array(
            [
                np.clip(next_pos[0], self.BOUNDS_MIN[0] + 0.2, self.BOUNDS_MAX[0] - 0.2),
                np.clip(next_pos[1], self.BOUNDS_MIN[1] + 0.2, self.BOUNDS_MAX[1] - 0.2),
                np.clip(next_pos[2], 0.08, self.BOUNDS_MAX[2] - 0.2),
            ],
            dtype=np.float32,
        )
        was_in = self.is_inside_house(pos)
        now_in = self.is_inside_house(cand)
        if was_in == now_in:
            if now_in and cand[2] > 2.5:
                cand[2] = 2.45  # Erdgeschoss-Decke für Innenflug
            return cand
        # Übergang Haus <-> Garten nur am Süd-Terrassenportal erlaubt!
        if self.near_house_portal(pos, tol=0.35) or self.near_house_portal(cand, tol=0.35):
            return cand
        return pos.astype(np.float32)

    def clamp_or_slide_fly_vec(self, pos: np.ndarray, next_pos: np.ndarray) -> np.ndarray:
        """Vektorisierte Wandblockade & Weltgrenzen für N Fliegen (shape=(N, 3))."""
        if len(pos) == 0:
            return pos.astype(np.float32)
        cand = next_pos.astype(np.float32).copy()
        cand[:, 0] = np.clip(cand[:, 0], self.BOUNDS_MIN[0] + 0.2, self.BOUNDS_MAX[0] - 0.2)
        cand[:, 1] = np.clip(cand[:, 1], self.BOUNDS_MIN[1] + 0.2, self.BOUNDS_MAX[1] - 0.2)
        cand[:, 2] = np.clip(cand[:, 2], 0.08, self.BOUNDS_MAX[2] - 0.2)

        was_in = self._is_inside_house_vec(pos)
        now_in = self._is_inside_house_vec(cand)
        same_side = was_in == now_in
        ceiling_cap = same_side & now_in & (cand[:, 2] > 2.5)
        if np.any(ceiling_cap):
            cand[ceiling_cap, 2] = 2.45

        cross = ~same_side
        if np.any(cross):
            portal_ok = self._near_house_portal_vec(pos, tol=0.35) | self._near_house_portal_vec(cand, tol=0.35)
            revert = cross & (~portal_ok)
            if np.any(revert):
                cand[revert] = pos[revert]
        return cand

    def clamp_bird_outside_obstacles(self, pos: np.ndarray, vel: np.ndarray, margin: float = 0.18) -> Tuple[np.ndarray, np.ndarray]:
        """Hält Vögel außerhalb solider Hauswände & Weltgrenzen (weiches Abprall-/Ausweich-Gleiten)."""
        p = pos.astype(np.float64).copy()
        v = vel.astype(np.float64).copy()
        p[0] = np.clip(p[0], self.BOUNDS_MIN[0] + 0.5, self.BOUNDS_MAX[0] - 0.5)
        p[1] = np.clip(p[1], self.BOUNDS_MIN[1] + 0.5, self.BOUNDS_MAX[1] - 0.5)
        p[2] = np.clip(p[2], 0.18, self.BOUNDS_MAX[2] - 0.5)

        for bmin, bmax in (self.HOUSE_BOX_MAIN, self.HOUSE_BOX_ANNEX):
            if (bmin[0] - margin <= p[0] <= bmax[0] + margin
                    and bmin[1] - margin <= p[1] <= bmax[1] + margin
                    and bmin[2] - margin <= p[2] <= bmax[2] + margin):
                # Auf nächste Außenfläche zurückschieben & Normalkomponente drehen
                dists = [
                    (abs(p[0] - (bmin[0] - margin)), 0, bmin[0] - margin - 0.05),
                    (abs(p[0] - (bmax[0] + margin)), 0, bmax[0] + margin + 0.05),
                    (abs(p[1] - (bmin[1] - margin)), 1, bmin[1] - margin - 0.05),
                    (abs(p[1] - (bmax[1] + margin)), 1, bmax[1] + margin + 0.05),
                    (abs(p[2] - (bmax[2] + margin)), 2, bmax[2] + margin + 0.05),
                ]
                _, ax, val = min(dists, key=lambda x: x[0])
                p[ax] = val
                v[ax] = abs(v[ax]) if val > 0 else -abs(v[ax])
        return p, v

    def export_metadata(self) -> Dict[str, object]:
        return {
            "world_bounds_m": {"min": list(self.BOUNDS_MIN), "max": list(self.BOUNDS_MAX)},
            "woelfersheim_anchor": self.woelfersheim_anchor,
            "gbif_woelfersheim_birds": self.gbif_bird_records,
            "canopies": [asdict(c) for c in self.canopies],
            "perches": [asdict(p) for p in self.perches],
            "substrates": [
                {
                    "substrate_id": s.substrate_id,
                    "label_de": s.label_de,
                    "zone": s.zone,
                    "pos": list(s.pos),
                    "canopy_cover": s.canopy_cover,
                }
                for s in self.substrates
            ],
  }
