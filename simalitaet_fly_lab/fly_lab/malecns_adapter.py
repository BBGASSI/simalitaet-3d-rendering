# -*- coding: utf-8 -*-
"""
Erweiterungs-Adapter für MaleCNS (male-cns:v1.0, HHMI Janelia FlyEM / Berg et al.).

Stellt ein gemeinsames ConnectomeGraphProtocol bereit, sodass SIMALITAET_FLY_LAB
neben dem primären FlyWire-v783-Ganzhirn-Konnektom (weibliches Adultgehirn) auch
das kombinierte Gehirn+VNC-Referenzmodell MaleCNS austauschbar anbinden kann.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Protocol, Sequence

import numpy as np
from scipy import sparse


NT_POLARITY_MAP: Dict[str, float] = {
    "acetylcholine": 1.0,
    "ach": 1.0,
    "gaba": -1.0,
    "glutamate": -1.0,   # Drosophila-ZNS überwiegend GluCl-inhibitorisch [EMPIRICAL_DATA]
    "glut": -1.0,
    "dopamine": 0.0,     # Modulatorisch
    "da": 0.0,
    "serotonin": 0.0,
    "5ht": 0.0,
    "octopamine": 0.0,
    "oa": 0.0,
}


class ConnectomeGraphProtocol(Protocol):
    """Einheitliche Schnittstelle für biologische Konnektome (FlyWire v783, MaleCNS v1.0)."""

    @property
    def dataset_id(self) -> str: ...

    @property
    def n_neurons(self) -> int: ...

    @property
    def signed_weight_matrix(self) -> sparse.csr_matrix: ...

    def pool_indices(self, pool_name: str, side: str | None = None) -> np.ndarray: ...

    def metadata_summary(self) -> Dict[str, object]: ...


@dataclass(frozen=True)
class MaleCNSNodeSpec:
    body_id: int
    cell_type: str
    side: str
    nt_type: str
    super_class: str  # "sensory", "central", "descending", "vnc_motor"


class MaleCNSReferenceAdapter:
    """
    Reproduzierbarer Adapter für MaleCNS (male-cns:v1.0, CC BY 4.0, neuprint.janelia.org).

    Hinweis zur Transparenz: Der vollständige MaleCNS-Export (Gehirn + Bauchmark VNC,
    ~166.000 Neuronen) benötigt ein authentifiziertes NeuPrint-Token bzw. großen Snapshot-Download.
    Dieses Modul implementiert das exakt kompatible Schema + einen deterministischen
    Brain+VNC-Referenz-Subgraph-Testadapter für vergleichende Architekturprüfungen.
    """

    SOURCE_URL = "https://neuprint.janelia.org/?dataset=male-cns:v1.0"
    LICENSE = "CC BY 4.0 (HHMI Janelia Research Campus / Berg et al.)"

    def __init__(self, nodes: Sequence[MaleCNSNodeSpec], edges: Sequence[tuple[int, int, float]]) -> None:
        self._dataset_id = "male-cns:v1.0"
        self.nodes = list(nodes)
        self._id_to_idx = {n.body_id: i for i, n in enumerate(self.nodes)}
        n = len(self.nodes)
        rows, cols, vals = [], [], []
        for pre_id, post_id, syn_w in edges:
            if pre_id in self._id_to_idx and post_id in self._id_to_idx:
                pi = self._id_to_idx[pre_id]
                pj = self._id_to_idx[post_id]
                sign = NT_POLARITY_MAP.get(self.nodes[pi].nt_type.lower(), 1.0)
                if sign == 0.0:
                    sign = 1.0
                rows.append(pj)
                cols.append(pi)
                vals.append(sign * float(syn_w))
        self._w_syn = sparse.csr_matrix(
            (np.asarray(vals, dtype=np.float32), (np.asarray(rows, dtype=np.int32), np.asarray(cols, dtype=np.int32))),
            shape=(n, n),
            dtype=np.float32,
        )
        self._pools: Dict[str, List[int]] = {}
        for i, node in enumerate(self.nodes):
            self._pools.setdefault(node.cell_type, []).append(i)

    @property
    def dataset_id(self) -> str:
        return self._dataset_id

    @property
    def n_neurons(self) -> int:
        return len(self.nodes)

    @property
    def signed_weight_matrix(self) -> sparse.csr_matrix:
        return self._w_syn

    def pool_indices(self, pool_name: str, side: str | None = None) -> np.ndarray:
        idxs = self._pools.get(pool_name, [])
        if side is not None:
            idxs = [i for i in idxs if self.nodes[i].side == side]
        return np.asarray(idxs, dtype=np.int32)

    def metadata_summary(self) -> Dict[str, object]:
        return {
            "dataset_id": self._dataset_id,
            "source_url": self.SOURCE_URL,
            "license": self.LICENSE,
            "n_neurons": self.n_neurons,
            "n_edges": int(self._w_syn.nnz),
            "supports_vnc_motor": any(n.super_class == "vnc_motor" for n in self.nodes),
            "status": "SCHEMA_AND_PROTOCOL_COMPATIBLE_ADAPTER",
        }

    @classmethod
    def build_deterministic_vnc_bridge_sample(cls) -> "MaleCNSReferenceAdapter":
        """Minimaler verifizierbarer Brain+VNC-Schema-Testgraph für Kompatibilitätsprüfungen."""
        nodes = [
            MaleCNSNodeSpec(1001, "ORN_DM1", "left", "acetylcholine", "sensory"),
            MaleCNSNodeSpec(1002, "ORN_DM1", "right", "acetylcholine", "sensory"),
            MaleCNSNodeSpec(2001, "DNa02", "left", "acetylcholine", "descending"),
            MaleCNSNodeSpec(2002, "DNa02", "right", "acetylcholine", "descending"),
            MaleCNSNodeSpec(3001, "VNC_WingSteer_L", "left", "acetylcholine", "vnc_motor"),
            MaleCNSNodeSpec(3002, "VNC_WingSteer_R", "right", "acetylcholine", "vnc_motor"),
        ]
        edges = [
            (1001, 2001, 18.0),
            (1002, 2002, 18.0),
            (2001, 3001, 24.0),
            (2002, 3002, 24.0),
        ]
        return cls(nodes, edges)
