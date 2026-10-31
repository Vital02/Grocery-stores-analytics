"""HTTP-health сервер генератора.

Нужен, чтобы docker-compose мог проверить, что сервис не просто запущен,
а действительно пишет данные (healthcheck по /healthz). Ничего не знает о
ClickHouse: читает счётчики из репозитория и сервиса генерации.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

logger = logging.getLogger(__name__)

STARTED_AT = time.time()
STALE_AFTER_SEC = 120.0
STARTUP_GRACE_SEC = 90.0


class HealthState:
    """Снимок состояния генератора для health-эндпоинтов."""

    def __init__(self, repository: Any, service: Any) -> None:
        self.repository = repository
        self.service = service

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        last_insert = getattr(self.service, "last_insert_at", None)
        if last_insert is None:
            age = None
            fresh = (now - STARTED_AT) < STARTUP_GRACE_SEC
        else:
            age = round(now - last_insert, 1)
            fresh = age <= STALE_AFTER_SEC
        return {
            "status": "ok" if fresh else "stale",
            "last_insert_age_sec": age,
            "lines_written": getattr(self.service, "lines_written", 0),
            "lines_generated": getattr(self.service, "lines_generated", 0),
            "anomalies_generated": getattr(self.service, "anomalies_generated", 0),
            "sales_in_db": self._sales_count(),
        }

    def _sales_count(self) -> int:
        try:
            return int(getattr(self.repository, "sales_count", lambda: 0)())
        except Exception:  # noqa: BLE001 - health не должен падать на запросе счётчика
            return -1


class _Handler(BaseHTTPRequestHandler):
    state: HealthState

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D102 - тише в логах
        logger.debug("health: " + fmt, *args)

    def _send(self, code: int, payload: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - имя метода задано http.server
        path = self.path.split("?")[0]
        if path in ("/healthz", "/readyz", "/health"):
            snapshot = self.state.snapshot()
            code = 200 if snapshot["status"] == "ok" else 503
            self._send(code, json.dumps(snapshot).encode(), "application/json")
        elif path == "/metrics":
            snapshot = self.state.snapshot()
            lines = [f"generator_{key} {value}" for key, value in snapshot.items()
                     if isinstance(value, (int, float))]
            self._send(200, ("\n".join(lines) + "\n").encode(), "text/plain; version=0.0.4")
        else:
            self._send(404, b'{"detail":"not found"}', "application/json")


class HealthServer:
    """Фоновый HTTP-сервер (daemon-поток)."""

    def __init__(self, port: int, state: HealthState, host: str = "0.0.0.0") -> None:
        handler = type("_BoundHandler", (_Handler,), {"state": state})
        self._server = ThreadingHTTPServer((host, port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="health", daemon=True)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def start(self) -> None:
        self._thread.start()
        logger.info("Health-сервер слушает порт %s", self.port)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
