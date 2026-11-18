# -*- coding: utf-8 -*-
"""
Modul A: Realer FlyWire-v783-Konnektom-Loader (ohne umgangene WDAC-Policies).

Verarbeitet die offenen Primärdateien von Dorkenwald et al. (Nature 2024),
Schlegel et al. (Nature 2024) und Shiu et al. (Nature 2024):
- Completeness_783.csv (138.639 indizierte Neuronen)
- Connectivity_783.parquet (15.091.983 gerichtete Kanten / 54.492.922 Synapsen)
  geladen über pyarrow._parquet.ParquetReader + pyarrow.PythonFile
- Supplemental_file1_neuron_annotations.tsv (139.248 annotierte Neuronen, CC BY 4.0)
"""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
import gc
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa
import pyarrow._parquet as _pq
from scipy import sparse

from .download_flywire import CACHE_DIR, ensure_flywire_v783_cached
from .malecns_adapter import ConnectomeGraphProtocol
from .security_guards import FLY_LAB_ROOT, FlyLabSecurityGuard


RESULTS_DIR = FLY_LAB_ROOT / "results"


@dataclass
class FlyWireSubcircuit:
    """Induzierter Teilgraph aus realen FlyWire-v783-Kanten für schnelle 10-ms-Simulation."""
    full_indices: np.ndarray              # Indizes in W_full (0..138638)
    w_sub: sparse.csr_matrix              # Vorzeichenbehaftete Synapsen-Matrix (scipy.sparse.csr_matrix)
    local_pools: Dict[str, Dict[str, np.ndarray]]  # pool_name -> {"left": idx, "right": idx, "all": idx}
    root_ids: np.ndarray


class FlyWireConnectome:
    """Reales FlyWire-v783-Ganzhirn-Konnektom konform zu ConnectomeGraphProtocol."""

    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        guard: Optional[FlyLabSecurityGuard] = None,
    ) -> None:
        self._dataset_id = "flywire_fafb_v783"
        self.cache_dir = Path(cache_dir)
        self.guard = guard or FlyLabSecurityGuard()
        self.manifest = ensure_flywire_v783_cached(force_manifest=False)

        self.root_ids: np.ndarray
        self.root_to_idx: Dict[int, int]
        self.completed_flags: np.ndarray
        self.w_full: sparse.csr_matrix
        self.total_synapses: int = 0

        # Annotationen pro Dense-Index (0 .. N-1)
        self.super_class: List[str] = []
        self.cell_class: List[str] = []
        self.cell_type: List[str] = []
        self.top_nt: List[str] = []
        self.side: List[str] = []
        self.flow: List[str] = []

        self.super_class_counts: Counter = Counter()
        self.nt_counts: Counter = Counter()
        self.pools: Dict[str, Dict[str, List[int]]] = {}
        self.matched_annotations: int = 0
        self.total_annotation_rows: int = 0

        self._load_completeness()
        self._load_connectivity_parquet()
        self._load_annotations_and_pools()

    @property
    def dataset_id(self) -> str:
        return self._dataset_id

    @property
    def n_neurons(self) -> int:
        return int(len(self.root_ids))

    @property
    def signed_weight_matrix(self) -> sparse.csr_matrix:
        return self.w_full

    def _load_completeness(self) -> None:
        comp_path = self.cache_dir / "Completeness_783.csv"
        rids: List[int] = []
        flags: List[bool] = []
        with comp_path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # Header: '', 'Completed'
            for row in reader:
                rids.append(int(row[0]))
                flags.append(row[1].strip().lower() == "true")
        self.root_ids = np.asarray(rids, dtype=np.int64)
        self.completed_flags = np.asarray(flags, dtype=bool)
        self.root_to_idx = {int(rid): i for i, rid in enumerate(rids)}

    def _load_connectivity_parquet(self) -> None:
        pq_path = self.cache_dir / "Connectivity_783.parquet"
        with pq_path.open("rb") as fh:
            pf = pa.PythonFile(fh, mode="r")
            reader = _pq.ParquetReader()
            reader.open(pf)
            # Spalten: Presynaptic_Index(2), Postsynaptic_Index(3), Connectivity(4), Excitatory x Connectivity(6)
            tbl = reader.read_all(column_indices=[2, 3, 4, 6])

        pre_idx = tbl.column(0).to_numpy().astype(np.int32, copy=False)
        post_idx = tbl.column(1).to_numpy().astype(np.int32, copy=False)
        syn_abs = tbl.column(2).to_numpy().astype(np.int64, copy=False)
        signed_w = tbl.column(3).to_numpy().astype(np.float32, copy=False)

        self.total_synapses = int(syn_abs.sum())
        n = self.n_neurons
        self.w_full = sparse.csr_matrix((signed_w, (post_idx, pre_idx)), shape=(n, n), dtype=np.float32)
        del tbl, pre_idx, post_idx, syn_abs, signed_w
        pa.default_memory_pool().release_unused()
        gc.collect()

    def _load_annotations_and_pools(self) -> None:
        n = self.n_neurons
        self.super_class = [""] * n
        self.cell_class = [""] * n
        self.cell_type = [""] * n
        self.top_nt = [""] * n
        self.side = ["na"] * n
        self.flow = [""] * n

        pool_names = [
            "orn_ester", "orn_terpene", "orn_geosmin", "orn_co2", "orn_pheromone",
            "pn_ester", "pn_terpene", "pn_geosmin",
            "hrn", "trn", "grn_sugar", "grn_bitter",
            "vision_spectral", "looming", "jo_mechano",
            "kc", "dan_reward", "dan_punish", "mbon_gaba_glut", "mbon_ach",
            "lhln", "dn_steer", "dn_forward", "dn_backward", "dn_jump", "motor_feeding",
        ]
        self.pools = {p: {"left": [], "right": [], "all": []} for p in pool_names}

        ann_path = self.cache_dir / "Supplemental_file1_neuron_annotations.tsv"
        matched = 0
        total_rows = 0
        with ann_path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                total_rows += 1
                rid_str = row.get("root_id", "")
                if not rid_str:
                    continue
                idx = self.root_to_idx.get(int(rid_str))
                if idx is None:
                    continue
                matched += 1
                sc = row.get("super_class", "") or ""
                cc = row.get("cell_class", "") or ""
                ct = row.get("cell_type", "") or ""
                nt = row.get("top_nt", "") or ""
                sd = (row.get("side", "") or "na").lower()
                fl = row.get("flow", "") or ""

                self.super_class[idx] = sc
                self.cell_class[idx] = cc
                self.cell_type[idx] = ct
                self.top_nt[idx] = nt
                self.side[idx] = sd
                self.flow[idx] = fl
                self.super_class_counts[sc or "unknown"] += 1
                self.nt_counts[nt or "unknown"] += 1

                def add_pool(pname: str) -> None:
                    self.pools[pname]["all"].append(idx)
                    if sd in ("left", "right"):
                        self.pools[pname][sd].append(idx)

                if ct in ("ORN_DM1", "ORN_DM2", "ORN_DM4", "ORN_VA2", "ORN_VM2", "ORN_DP1m"):
                    add_pool("orn_ester")
                elif ct == "ORN_DC1":
                    add_pool("orn_terpene")
                elif ct == "ORN_DA2":
                    add_pool("orn_geosmin")
                elif ct == "ORN_V":
                    add_pool("orn_co2")
                elif ct == "ORN_DA1":
                    add_pool("orn_pheromone")

                if ct in ("DM1_lPN", "DM2_lPN", "DM4_adPN", "DM4_vPN", "VA2_adPN"):
                    add_pool("pn_ester")
                elif ct == "DC1_adPN":
                    add_pool("pn_terpene")
                elif ct == "DA2_lPN":
                    add_pool("pn_geosmin")

                if cc == "hygrosensory" or ct.startswith("HRN_"):
                    add_pool("hrn")
                if cc == "thermosensory" or ct.startswith("TRN_"):
                    add_pool("trn")
                if cc == "gustatory":
                    if ct in ("claw_tpGRN", "LB3a", "LB3b", "LB3c", "LB1a"):
                        add_pool("grn_sugar")
                    elif ct in ("dorsal_tpGRN", "LgAG1", "LgAG2", "LgAG3", "LgAG4"):
                        add_pool("grn_bitter")

                if ct.startswith("MeTu"):
                    add_pool("vision_spectral")
                if ct in ("LC4", "LPLC2", "LC11", "LC16"):
                    add_pool("looming")
                if ct.startswith("JO-"):
                    add_pool("jo_mechano")

                if cc == "Kenyon_Cell":
                    add_pool("kc")
                if ct.startswith("PAM"):
                    add_pool("dan_reward")
                if ct.startswith("PPL1"):
                    add_pool("dan_punish")
                if ct.startswith("MBON"):
                    if nt in ("gaba", "glutamate"):
                        add_pool("mbon_gaba_glut")
                    else:
                        add_pool("mbon_ach")
                if cc == "LHLN":
                    add_pool("lhln")

                if ct in ("DNa01", "DNa02"):
                    add_pool("dn_steer")
                if ct == "DNp09":
                    add_pool("dn_forward")
                if ct == "MDN":
                    add_pool("dn_backward")
                if ct == "DNp01":
                    add_pool("dn_jump")
                if sc == "motor":
                    add_pool("motor_feeding")

        self.matched_annotations = matched
        self.total_annotation_rows = total_rows

    def pool_indices(self, pool_name: str, side: Optional[str] = None) -> np.ndarray:
        entry = self.pools.get(pool_name)
        if entry is None:
            return np.zeros(0, dtype=np.int32)
        key = side if side in ("left", "right") else "all"
        return np.asarray(entry[key], dtype=np.int32)

    def extract_sensorimotor_subcircuit(self, max_kc: int = 1200, max_bridge: int = 600) -> FlyWireSubcircuit:
        """
        Extrahiert einen echten induzierten Teilgraphen direkt aus W_full (100% reale FlyWire-Kanten)
        für deterministische Echtzeit-Experimente auf 8 GB RAM / 2C-Hardware.
        """
        chosen: set[int] = set()
        for pname, sides in self.pools.items():
            idxs = sides["all"]
            if pname == "kc" and len(idxs) > max_kc:
                # Stratifizierte deterministische Auswahl gleichmäßig über links/rechts
                l_idx = sides["left"][: max_kc // 2]
                r_idx = sides["right"][: max_kc // 2]
                chosen.update(l_idx)
                chosen.update(r_idx)
            elif pname == "lhln" and len(idxs) > max_bridge:
                chosen.update(idxs[:max_bridge])
            else:
                chosen.update(idxs)

        full_indices = np.asarray(sorted(chosen), dtype=np.int32)
        global_to_local = {int(g): i for i, g in enumerate(full_indices)}
        w_sub = self.w_full[full_indices, :][:, full_indices].tocsr()

        local_pools: Dict[str, Dict[str, np.ndarray]] = {}
        for pname, sides in self.pools.items():
            local_pools[pname] = {}
            for sname in ("left", "right", "all"):
                loc = [global_to_local[g] for g in sides[sname] if g in global_to_local]
                local_pools[pname][sname] = np.asarray(loc, dtype=np.int32)

        return FlyWireSubcircuit(
            full_indices=full_indices,
            w_sub=w_sub,
            local_pools=local_pools,
            root_ids=self.root_ids[full_indices],
        )

    def metadata_summary(self) -> Dict[str, object]:
        pool_counts = {
            k: {"all": len(v["all"]), "left": len(v["left"]), "right": len(v["right"])}
            for k, v in self.pools.items()
        }
        return {
            "dataset_id": self._dataset_id,
            "n_neurons_completeness": self.n_neurons,
            "n_completed_true": int(self.completed_flags.sum()),
            "n_edges": int(self.w_full.nnz),
            "total_chemical_synapses": self.total_synapses,
            "n_annotation_rows": self.total_annotation_rows,
            "n_matched_annotations": self.matched_annotations,
            "super_class_counts": dict(self.super_class_counts),
            "top_nt_counts": dict(self.nt_counts),
            "functional_pools": pool_counts,
        }

    def export_summary(self, path: Path = RESULTS_DIR / "connectome_summary.json") -> Dict[str, object]:
        summary = self.metadata_summary()
        self.guard.safe_write_text(path, json.dumps(summary, indent=2, ensure_ascii=False))
        return summary
