# -*- coding: utf-8 -*-
"""
Reproduzierbarer Download und SHA-256-Verifikation des offenen FlyWire-v783-Konnektoms
(Dorkenwald et al. Nature 2024, Schlegel et al. Nature 2024, Shiu et al. Nature 2024).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from typing import Dict, List


CACHE_DIR = Path(r"C:\Users\Ulric\.gemini\antigravity\scratch\SIMALITAET_FLY_LAB\cache\flywire_v783")
MANIFEST_PATH = Path(r"C:\Users\Ulric\.gemini\antigravity\scratch\SIMALITAET_FLY_LAB\results\dataset_manifest.json")

FLYWIRE_V783_SOURCES: List[Dict[str, object]] = [
    {
        "dataset_id": "flywire_v783_completeness",
        "filename": "Completeness_783.csv",
        "url": "https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/main/Completeness_783.csv",
        "expected_bytes": 3327347,
        "license": "CC BY 4.0 (FlyWire) / MIT (Shiu et al. 2024 wrapper)",
        "citation": "Shiu et al., Nature 634, 210-219 (2024); Dorkenwald et al., Nature 634, 124-138 (2024)",
    },
    {
        "dataset_id": "flywire_v783_connectivity",
        "filename": "Connectivity_783.parquet",
        "url": "https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/main/Connectivity_783.parquet",
        "expected_bytes": 100804642,
        "license": "CC BY 4.0 (FlyWire v783 Connectome)",
        "citation": "Dorkenwald et al., Nature 634, 124-138 (2024); Zenodo 10676866",
    },
    {
        "dataset_id": "flywire_v783_annotations",
        "filename": "Supplemental_file1_neuron_annotations.tsv",
        "url": "https://raw.githubusercontent.com/flyconnectome/flywire_annotations/main/supplemental_files/Supplemental_file1_neuron_annotations.tsv",
        "expected_bytes": 31720298,
        "license": "CC BY 4.0 (Schlegel et al., Nature 2024)",
        "citation": "Schlegel et al., Nature 634, 139-152 (2024)",
    },
]


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def download_with_retry(url: str, dest: Path, expected_bytes: int | None = None, max_attempts: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and expected_bytes and dest.stat().st_size == expected_bytes:
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SIMALITAET-FlyLab/0.1"})
            with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
            if expected_bytes and tmp.stat().st_size != expected_bytes:
                raise RuntimeError(f"Byte count mismatch for {dest.name}: {tmp.stat().st_size} != {expected_bytes}")
            tmp.replace(dest)
            time.sleep(0.5)
            return
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
            last_err = exc
            if attempt < max_attempts:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Download fehlgeschlagen nach {max_attempts} Versuchen ({url}): {last_err}")


def ensure_flywire_v783_cached(force_manifest: bool = True) -> Dict[str, object]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for src in FLYWIRE_V783_SOURCES:
        dest = CACHE_DIR / str(src["filename"])
        download_with_retry(str(src["url"]), dest, int(src["expected_bytes"]))
        sha = _sha256_path(dest)
        entries.append(
            {
                "dataset_id": src["dataset_id"],
                "filename": src["filename"],
                "local_path": str(dest),
                "url": src["url"],
                "bytes": dest.stat().st_size,
                "sha256": sha,
                "license": src["license"],
                "citation": src["citation"],
            }
        )
    manifest = {
        "schema_version": "1.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "primary_connectome": "FlyWire FAFB v783 (Drosophila melanogaster adult female whole brain)",
        "secondary_connectome_adapter": "MaleCNS male-cns:v1.0 (Janelia FlyEM / Berg et al., CC BY 4.0, neuprint.janelia.org)",
        "biomechanics_reference": "NeuroMechFly v2 / FlyGym 2.1.1 (Wang-Chen et al., Nature Methods 2024, Apache-2.0) + MuJoCo 3.16.0 (Apache-2.0)",
        "files": entries,
    }
    if force_manifest or not MANIFEST_PATH.exists():
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = ensure_flywire_v783_cached()
    for item in m["files"]:
        print(f"OK {item['filename']}: {item['bytes']:,} bytes | sha256={item['sha256'][:16]}...")
