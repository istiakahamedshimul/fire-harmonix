"""Vercel serverless API router for FIRE-HARMONIX.

The bundled SQLite database is opened read-only. No runtime writes are made,
which keeps the function compatible with Vercel's immutable deployment image.
"""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATABASE = Path(__file__).resolve().parents[1] / "data" / "fire_harmonix.db"


def query(sql: str, params: tuple = ()) -> list[dict]:
    connection = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]
    finally:
        connection.close()


class handler(BaseHTTPRequestHandler):
    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=0, s-maxage=300")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_csv(self) -> None:
        body = (DATABASE.parent / "fire_samples.csv").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", "attachment; filename=fire_samples.csv")
        self.send_header("Cache-Control", "public, max-age=0, s-maxage=3600")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parameters = parse_qs(urlparse(self.path).query)
        route = parameters.get("route", [""])[0]

        if route == "download":
            self.send_csv()
            return

        if route == "summary":
            totals = query(
                "SELECT COUNT(*) detections, ROUND(SUM(frp),1) total_frp, "
                "COUNT(DISTINCT grid_id) grids, SUM(status='Unusual') unusual "
                "FROM observations"
            )[0]
            self.send_json({
                "totals": totals,
                "sensors": query("SELECT * FROM sensor_summary"),
                "daily": query("SELECT * FROM grid_daily ORDER BY acq_date"),
            })
            return

        if route == "observations":
            sensor = parameters.get("sensor", ["ALL"])[0].upper()
            where = "" if sensor == "ALL" else " WHERE sensor = ?"
            values = () if sensor == "ALL" else (sensor,)
            self.send_json(query(f"SELECT * FROM observations{where} ORDER BY hfai DESC", values))
            return

        if route == "observation":
            try:
                observation_id = int(parameters.get("id", [""])[0])
            except ValueError:
                self.send_json({"error": "Invalid observation id"}, 400)
                return
            rows = query("SELECT * FROM observations WHERE id = ?", (observation_id,))
            self.send_json(rows[0] if rows else {"error": "Not found"}, 200 if rows else 404)
            return

        self.send_json({"error": "Unknown API route"}, 404)

    def log_message(self, format: str, *args: object) -> None:
        return
