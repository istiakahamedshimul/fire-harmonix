"""Zero-dependency local server for the FIRE-HARMONIX prototype."""

from __future__ import annotations

import json
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATABASE = ROOT / "data" / "fire_harmonix.db"


def query(sql: str, params: tuple = ()) -> list[dict]:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]
    finally:
        connection.close()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/data/fire_samples.csv":
            body = (ROOT / "data" / "fire_samples.csv").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=fire_samples.csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/observations":
            sensor = parse_qs(parsed.query).get("sensor", ["ALL"])[0].upper()
            where = "" if sensor == "ALL" else " WHERE sensor = ?"
            params = () if sensor == "ALL" else (sensor,)
            self.send_json(query(f"SELECT * FROM observations{where} ORDER BY hfai DESC", params))
            return
        if parsed.path == "/api/summary":
            totals = query("SELECT COUNT(*) detections, ROUND(SUM(frp),1) total_frp, COUNT(DISTINCT grid_id) grids, SUM(status='Unusual') unusual FROM observations")[0]
            self.send_json({"totals": totals, "sensors": query("SELECT * FROM sensor_summary"), "daily": query("SELECT * FROM grid_daily ORDER BY acq_date")})
            return
        if parsed.path.startswith("/api/observations/"):
            try:
                observation_id = int(parsed.path.rsplit("/", 1)[1])
            except ValueError:
                self.send_json({"error": "Invalid observation id"}, 400)
                return
            rows = query("SELECT * FROM observations WHERE id = ?", (observation_id,))
            self.send_json(rows[0] if rows else {"error": "Not found"}, 200 if rows else 404)
            return

        relative = parsed.path.lstrip("/") or "index.html"
        target = (PUBLIC / relative).resolve()
        if PUBLIC.resolve() not in target.parents and target != PUBLIC.resolve():
            self.send_error(403)
            return
        if not target.is_file():
            target = PUBLIC / "index.html"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    print("FIRE-HARMONIX running at http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
