# -*- coding: utf-8 -*-
"""
Lokaler HTTP-Server für das interaktive SIMALITÄT Ökosystem-Observatorium.

Verwendet ausschließlich Python-Standardbibliothek (`http.server`) ohne externe Web-Abhängigkeiten.
Bindet sich an 127.0.0.1 (Standardport 8765) und bedient HTML/CSS/JS + JSON-Endpunkte.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .observatory_engine import ObservatoryEngine


STATIC_DIR = Path(__file__).resolve().parent


class _ObservatoryHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    engine: ObservatoryEngine  # vom Server auf die Klasse gebunden

    def log_message(self, format: str, *args: Any) -> None:
        # Kompaktes Konsolenlogging unterdrücken, um Hintergrund-Task-Logs sauber zu halten
        return

    def _send_json(self, data: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_file(self, file_path: Path, mime: str) -> None:
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, f"Missing {file_path.name}")
            return
        raw = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "observatory_ui.html", "text/html; charset=utf-8")
        elif parsed.path == "/observatory_style.css":
            self._send_file(STATIC_DIR / "observatory_style.css", "text/css; charset=utf-8")
        elif parsed.path == "/observatory_app.js":
            self._send_file(STATIC_DIR / "observatory_app.js", "application/javascript; charset=utf-8")
        elif parsed.path == "/api/meta":
            self._send_json(self.engine.get_meta())
        elif parsed.path == "/api/state":
            t_val = float(qs["t"][0]) if "t" in qs and qs["t"][0] != "" else None
            self._send_json(self.engine.get_state_payload(t_s=t_val))
        elif parsed.path == "/api/object":
            eid = qs.get("id", [""])[0]
            t_val = float(qs["t"][0]) if "t" in qs and qs["t"][0] != "" else None
            self._send_json(self.engine.get_object_detail(eid, t_s=t_val))
        elif parsed.path == "/api/diff":
            t1 = float(qs.get("t1", ["0"])[0])
            t2 = float(qs.get("t2", ["0"])[0])
            eid = qs.get("entity_id", [None])[0]
            if eid == "":
                eid = None
            self._send_json(self.engine.get_diff(t1, t2, entity_id=eid))
        elif parsed.path == "/api/causal_chain":
            ev_id = qs.get("event_id", [""])[0]
            self._send_json(self.engine.get_causal_chain(ev_id))
        else:
            self._send_json({"error": f"Unknown path {parsed.path}"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {}

        if parsed.path == "/api/control":
            action = str(payload.get("action", "")).lower()
            if action == "play":
                self.engine.start_background()
            elif action == "pause":
                self.engine.pause_background()
            elif action == "step":
                sec = float(payload.get("seconds", 5.0))
                self.engine.pause_background()
                self.engine.run_for_seconds(sec)
            elif action == "run_rain_cycle":
                target = float(payload.get("target_s", 90.0))
                self.engine.start_cycle_async(target)
            elif action == "reset":
                self.engine.reset(
                    scenario=payload.get("scenario"),
                    season=payload.get("season"),
                    seed=payload.get("seed"),
                )
            self._send_json(self.engine.get_state_payload())
        elif parsed.path == "/api/compare_control":
            dur = float(payload.get("duration_s", 90.0))
            if payload.get("async", True):
                self.engine.pause_background()
                self.engine.start_compare_dry_async(duration_s=dur)
                self._send_json({"status": "started", "compare_running": True})
            else:
                self.engine.pause_background()
                res = self.engine.compare_against_dry_control(duration_s=dur)
                self._send_json(res)
        else:
            self._send_json({"error": f"Unknown POST {parsed.path}"}, status=HTTPStatus.NOT_FOUND)


class ObservatoryServer:
    """Verwaltet ThreadingHTTPServer + Hintergrund-Simulationsschleife sauber."""

    def __init__(self, engine: ObservatoryEngine, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.engine = engine
        self.host = host
        self.requested_port = int(port)
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._serve_thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        if self._httpd is not None:
            return int(self._httpd.server_address[1])
        return self.requested_port

    def start(self) -> int:
        eng = self.engine

        class _BoundHandler(_ObservatoryHandler):
            engine = eng

        ThreadingHTTPServer.allow_reuse_address = True
        self._httpd = ThreadingHTTPServer((self.host, self.requested_port), _BoundHandler)
        self._serve_thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="ObservatoryHTTPThread",
            daemon=True,
        )
        self._serve_thread.start()
        return self.port

    def stop(self) -> None:
        self.engine.stop_background()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
