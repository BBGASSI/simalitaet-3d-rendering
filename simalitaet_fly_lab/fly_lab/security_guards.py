# -*- coding: utf-8 -*-
"""
SplitBrain-, ROT- und BDG-0-konforme Schutzschicht für SIMALITAET_FLY_LAB.

Erlaubt Schreibzugriffe ausschließlich innerhalb von SIMALITAET_FLY_LAB (sowie einem
explizit registrierten Export-Artefaktpfad) und erzwingt für alle vorgelagerten
Simalität-Datenbanken (Großgemeinde Wölfersheim, Baustein 01/02) strikte
Read-Only-Verbindungen (?mode=ro + SQLITE_DENY-Authorizer).
"""

from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import sqlite3
from typing import Dict, Iterable, List, Optional, Tuple


FLY_LAB_ROOT = Path(r"C:\Users\Ulric\.gemini\antigravity\scratch\SIMALITAET_FLY_LAB").resolve()
SCRATCH_ROOT = Path(r"C:\Users\Ulric\.gemini\antigravity\scratch").resolve()

PROTECTED_DIRS: Tuple[Path, ...] = (
    SCRATCH_ROOT / "SIMALITAET_LUANTI",
    SCRATCH_ROOT / "SIMALITAET_GROSSGEMEINDE_WOELFERSHEIM",
    SCRATCH_ROOT / "SIMALITAET_BAUSTEIN_01_BIODIVERSITAET",
    SCRATCH_ROOT / "SIMALITAET_BAUSTEIN_02_BEVOELKERUNG_INFRASTRUKTUR",
    SCRATCH_ROOT / "SIMALITAET_BINDI_COMM_01",
    Path(r"C:\Users\Ulric\BinDinG_Core_V1"),
    Path(r"C:\Users\Ulric\binding_cortana"),
)

WOELFERSHEIM_DB_PATH = (
    SCRATCH_ROOT / "SIMALITAET_GROSSGEMEINDE_WOELFERSHEIM" / "data" / "grossgemeinde_woelfersheim.sqlite3"
)
BIODIV_DB_PATH = (
    SCRATCH_ROOT / "SIMALITAET_BAUSTEIN_01_BIODIVERSITAET" / "data" / "simalitaet_biodiversitaet.sqlite3"
)


class FlyLabWriteLockError(PermissionError):
    """Ausgelöst, wenn ein Schreibzugriff außerhalb der freigegebenen Fly-Lab-Sandbox versucht wird."""


class FlyLabReadOnlyViolationError(PermissionError):
    """Ausgelöst, wenn eine Read-Only-SQLite-Abfrage schreibende Operationen versucht."""


def set_below_normal_priority() -> bool:
    """Drosselt den Rechenprozess unter Windows auf BELOW_NORMAL_PRIORITY_CLASS (0x00004000)."""
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetCurrentProcess()
        res = kernel32.SetPriorityClass(handle, 0x00004000)
        return bool(res)
    except Exception:
        return False


def get_process_rss_mb() -> float:
    """Liest den aktuellen Working-Set-Speicher (MB) des Prozesses unter Windows präzise."""
    try:
        import psutil  # type: ignore
        return round(psutil.Process().memory_info().rss / (1024.0 * 1024.0), 2)
    except Exception:
        pass
    if os.name != "nt":
        return 0.0
    try:
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        k32 = ctypes.windll.kernel32
        handle = k32.GetCurrentProcess()
        if k32.K32GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            return round(pmc.WorkingSetSize / (1024.0 * 1024.0), 2)
    except Exception:
        pass
    return 0.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class FlyLabSecurityGuard:
    """SplitBrain-Schreibschutz & Read-Only-SQLite-Adapter für SIMALITAET_FLY_LAB."""

    _ALLOWED_SQLITE_ACTIONS = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_PRAGMA,
    }

    def __init__(
        self,
        writable_roots: Optional[Iterable[Path]] = None,
        protected_dirs: Optional[Iterable[Path]] = None,
    ) -> None:
        self.rot_locked: bool = False
        self.writable_roots: List[Path] = [
            Path(p).resolve() for p in (writable_roots if writable_roots is not None else [FLY_LAB_ROOT])
        ]
        self.protected_dirs: List[Path] = [
            Path(p).resolve() for p in (protected_dirs if protected_dirs is not None else PROTECTED_DIRS)
        ]
        self.audit_events: List[str] = []

    def activate_rot(self, reason: str) -> None:
        self.rot_locked = True
        self.audit_events.append(f"ROT_ACTIVATED:{reason}")

    def _is_within(self, child: Path, parent: Path) -> bool:
        try:
            child.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            return False

    def assert_write_allowed(self, target_path: Path) -> Path:
        resolved = Path(target_path).resolve()
        if self.rot_locked:
            raise FlyLabWriteLockError(f"ROT_LOCK_ACTIVE: Schreibzugriff verweigert für {resolved}")
        for pdir in self.protected_dirs:
            if pdir.exists() and self._is_within(resolved, pdir):
                raise FlyLabWriteLockError(f"PROTECTED_CORE_DENIED: {resolved} liegt in {pdir}")
        if not any(self._is_within(resolved, root) for root in self.writable_roots):
            raise FlyLabWriteLockError(f"OUTSIDE_FLY_LAB_SANDBOX: {resolved}")
        return resolved

    def safe_write_text(self, target_path: Path, text: str) -> Path:
        resolved = self.assert_write_allowed(target_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(text, encoding="utf-8")
        self.audit_events.append(f"WRITE_OK:{resolved.name}")
        return resolved

    def open_readonly_sqlite(self, db_path: Path) -> sqlite3.Connection:
        resolved = Path(db_path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"SQLite-Datei nicht gefunden: {resolved}")
        uri = f"{resolved.as_uri()}?mode=ro&immutable=0"
        con = sqlite3.connect(uri, uri=True, timeout=5.0)
        con.row_factory = sqlite3.Row

        def _authorizer(action, arg1, arg2, dbname, source):
            if action in self._ALLOWED_SQLITE_ACTIONS:
                # PRAGMA darf nicht schreiben (z.B. journal_mode/user_version)
                if action == sqlite3.SQLITE_PRAGMA and arg2 is not None:
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        con.set_authorizer(_authorizer)
        self.audit_events.append(f"SQLITE_RO_OPEN:{resolved.name}")
        return con

    @staticmethod
    def snapshot_protected_state(
        luanti_dir: Path = SCRATCH_ROOT / "SIMALITAET_LUANTI",
        woelfersheim_db: Path = WOELFERSHEIM_DB_PATH,
    ) -> Dict[str, object]:
        luanti_latest_mtime = 0.0
        luanti_latest_file = ""
        luanti_code_latest_mtime = 0.0
        luanti_code_latest_file = ""
        luanti_file_count = 0
        if luanti_dir.exists():
            for p in luanti_dir.rglob("*"):
                if p.is_file():
                    luanti_file_count += 1
                    mt = p.stat().st_mtime
                    if mt > luanti_latest_mtime:
                        luanti_latest_mtime = mt
                        luanti_latest_file = str(p)
                    if p.suffix.lower() in {".py", ".lua", ".gd", ".json", ".md"} and "logs" not in p.parts:
                        if mt > luanti_code_latest_mtime:
                            luanti_code_latest_mtime = mt
                            luanti_code_latest_file = str(p)
        db_sha = sha256_file(woelfersheim_db) if woelfersheim_db.exists() else ""
        return {
            "luanti_file_count": luanti_file_count,
            "luanti_latest_mtime": round(luanti_latest_mtime, 3),
            "luanti_latest_file": luanti_latest_file,
            "luanti_code_latest_mtime": round(luanti_code_latest_mtime, 3),
            "luanti_code_latest_file": luanti_code_latest_file,
            "woelfersheim_db_sha256": db_sha,
      }
