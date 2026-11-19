# -*- coding: utf-8 -*-
r"""
Startskript für das interaktive SIMALITÄT Ökosystem-Observatorium.

Beispiel:
    .\.venv\Scripts\python.exe run_observatory.py --port 8765 --scenario REGENZYKLUS
"""

from __future__ import annotations

import argparse
import signal
import time

from fly_lab.ecosystem.observatory_engine import ObservatoryEngine
from fly_lab.ecosystem.observatory_server import ObservatoryServer
from fly_lab.security_guards import set_below_normal_priority


def main() -> int:
    parser = argparse.ArgumentParser(description="SIMALITÄT Sichtbares Ökosystem-Observatorium")
    parser.add_argument("--port", type=int, default=8765, help="Lokaler HTTP-Port (Standard: 8765)")
    parser.add_argument("--scenario", type=str, default="REGENZYKLUS", choices=["REGENZYKLUS", "TROCKEN_KONTROLLE", "STARKREGEN"])
    parser.add_argument("--season", type=str, default="SOMMER", choices=["FRUEHLING", "SOMMER", "HERBST", "WINTER"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--preload-s", type=float, default=0.0, help="Optional vorberechnete Sekunden beim Start")
    args = parser.parse_args()

    set_below_normal_priority()
    engine = ObservatoryEngine(scenario=args.scenario, season=args.season, seed=args.seed)
    if args.preload_s > 0.0:
        engine.run_for_seconds(args.preload_s)

    server = ObservatoryServer(engine=engine, host="127.0.0.1", port=args.port)
    bound_port = server.start()
    print(f"OBSERVATORY_READY http://127.0.0.1:{bound_port}", flush=True)

    stop_requested = False

    def _sig(_signum, _frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    try:
        while not stop_requested:
            time.sleep(0.5)
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
