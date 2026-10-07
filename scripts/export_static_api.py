"""Export SQLite-backed dashboard responses as Vercel-ready static JSON."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "fire_harmonix.db"
PUBLIC = ROOT / "public"


def query(connection: sqlite3.Connection, sql: str) -> list[dict]:
    return [dict(row) for row in connection.execute(sql).fetchall()]


def main() -> None:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    try:
        observations = query(connection, "SELECT * FROM observations ORDER BY hfai DESC")
        totals = query(connection, "SELECT COUNT(*) detections, ROUND(SUM(frp),1) total_frp, COUNT(DISTINCT grid_id) grids, SUM(status='Unusual') unusual FROM observations")[0]
        summary = {
            "totals": totals,
            "sensors": query(connection, "SELECT * FROM sensor_summary"),
            "daily": query(connection, "SELECT * FROM grid_daily ORDER BY acq_date"),
        }
    finally:
        connection.close()

    api_dir = PUBLIC / "api"
    data_dir = PUBLIC / "data"
    api_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "observations.json").write_text(json.dumps(observations, separators=(",", ":")), encoding="utf-8")
    (api_dir / "summary.json").write_text(json.dumps(summary, separators=(",", ":")), encoding="utf-8")
    shutil.copyfile(ROOT / "data" / "fire_samples.csv", data_dir / "fire_samples.csv")
    print(f"Exported {len(observations)} observations for static deployment.")


if __name__ == "__main__":
    main()
