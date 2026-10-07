"""Create the FIRE-HARMONIX demo CSV and SQLite database.

The script samples evenly across the three CSV files in the public Kaggle
NASA FIRMS dataset. It keeps the source fields intact and adds transparent,
non-ML prototype features used by the dashboard.
"""

from __future__ import annotations

import csv
import io
import math
import random
import sqlite3
import statistics
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CSV_PATH = DATA_DIR / "fire_samples.csv"
DB_PATH = DATA_DIR / "fire_harmonix.db"
PUBLIC_CSV_PATH = ROOT / "public" / "data" / "fire_samples.csv"

FILES = (
    ("fire_nrt_M-C61_565334.csv", 67),
    ("fire_nrt_J1V-C2_565335.csv", 67),
    ("fire_nrt_SV-C2_565336.csv", 66),
)

RAW_FIELDS = [
    "latitude", "longitude", "brightness", "scan", "track", "acq_date",
    "acq_time", "satellite", "instrument", "confidence", "version",
    "bright_t31", "frp", "daynight",
]


def reservoir(reader: csv.DictReader, size: int, seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed)
    result: list[dict[str, str]] = []
    for index, row in enumerate(reader):
        if index < size:
            result.append(row)
        else:
            choice = rng.randint(0, index)
            if choice < size:
                result[choice] = row
    return result


def confidence_number(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return {"l": 35.0, "n": 65.0, "h": 90.0}.get(value.lower(), 50.0)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def load_sample(zip_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with zipfile.ZipFile(zip_path) as archive:
        for seed, (name, count) in enumerate(FILES, start=41):
            with archive.open(name) as binary:
                text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                rows.extend(reservoir(csv.DictReader(text), count, seed))
    return rows


def enrich(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    by_sensor: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_sensor[row["instrument"].upper()].append(row)

    stats: dict[str, dict[str, tuple[float, float]]] = {}
    for sensor, group in by_sensor.items():
        stats[sensor] = {}
        for field in ("brightness", "frp"):
            values = [float(item[field]) for item in group]
            stats[sensor][field] = (statistics.mean(values), statistics.pstdev(values) or 1.0)

    enriched: list[dict[str, object]] = []
    for index, raw in enumerate(rows, start=1):
        row: dict[str, object] = {field: raw[field] for field in RAW_FIELDS}
        for field in ("latitude", "longitude", "brightness", "scan", "track", "bright_t31", "frp"):
            row[field] = float(raw[field])
        row["acq_time"] = str(raw["acq_time"]).zfill(4)
        sensor = raw["instrument"].upper()
        bright_mean, bright_std = stats[sensor]["brightness"]
        frp_mean, frp_std = stats[sensor]["frp"]
        norm_brightness = (float(raw["brightness"]) - bright_mean) / bright_std
        norm_frp = (float(raw["frp"]) - frp_mean) / frp_std
        quality = confidence_number(raw["confidence"]) / 100
        # Engineering index only: bounded, interpretable, and deliberately not called a prediction.
        activity = clamp(0.30 + 0.17 * norm_brightness + 0.22 * norm_frp + 0.16 * quality + (0.05 if raw["daynight"] == "N" else 0))
        agreement = clamp(0.72 - abs(norm_brightness - norm_frp) * 0.12)
        hfai = clamp(0.25 * activity + 0.25 * clamp((norm_frp + 2) / 4) + 0.20 * clamp((norm_brightness + 2) / 4) + 0.15 * agreement + 0.15 * quality)
        parsed = datetime.strptime(f"{raw['acq_date']} {row['acq_time']}", "%Y-%m-%d %H%M")
        resolution = 0.05
        grid_lat = math.floor(float(raw["latitude"]) / resolution)
        grid_lon = math.floor(float(raw["longitude"]) / resolution)
        row.update({
            "id": index,
            "datetime_utc": parsed.strftime("%Y-%m-%dT%H:%M:00Z"),
            "sensor": sensor,
            "grid_id": f"{grid_lat}_{grid_lon}",
            "normalized_brightness": round(norm_brightness, 4),
            "normalized_frp": round(norm_frp, 4),
            "quality_score": round(quality, 4),
            "sensor_agreement": round(agreement, 4),
            "hfai": round(hfai, 4),
            "status": "Unusual" if hfai >= 0.68 else "Elevated" if hfai >= 0.48 else "Normal",
        })
        enriched.append(row)
    return enriched


def write_outputs(rows: list[dict[str, object]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["id", *RAW_FIELDS, "datetime_utc", "sensor", "grid_id", "normalized_brightness", "normalized_frp", "quality_score", "sensor_agreement", "hfai", "status"]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    PUBLIC_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_CSV_PATH.write_bytes(CSV_PATH.read_bytes())

    if DB_PATH.exists():
        DB_PATH.unlink()
    connection = sqlite3.connect(DB_PATH)
    connection.executescript("""
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL,
            brightness REAL NOT NULL, scan REAL, track REAL, acq_date TEXT NOT NULL,
            acq_time TEXT NOT NULL, satellite TEXT NOT NULL, instrument TEXT NOT NULL,
            confidence TEXT, version TEXT, bright_t31 REAL, frp REAL NOT NULL,
            daynight TEXT, datetime_utc TEXT NOT NULL, sensor TEXT NOT NULL,
            grid_id TEXT NOT NULL, normalized_brightness REAL,
            normalized_frp REAL, quality_score REAL, sensor_agreement REAL,
            hfai REAL, status TEXT
        );
        CREATE INDEX idx_observations_sensor ON observations(sensor);
        CREATE INDEX idx_observations_date ON observations(acq_date);
        CREATE INDEX idx_observations_grid ON observations(grid_id);
    """)
    columns = fields
    placeholders = ",".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO observations ({','.join(columns)}) VALUES ({placeholders})",
        [[row[column] for column in columns] for row in rows],
    )
    connection.executescript("""
        CREATE VIEW sensor_summary AS
        SELECT sensor, COUNT(*) AS detections, ROUND(AVG(frp), 2) AS mean_frp,
               ROUND(AVG(brightness), 2) AS mean_brightness,
               ROUND(AVG(sensor_agreement), 3) AS mean_agreement,
               ROUND(AVG(hfai), 3) AS mean_hfai
        FROM observations GROUP BY sensor;

        CREATE VIEW grid_daily AS
        SELECT grid_id, acq_date, COUNT(*) AS detection_count,
               ROUND(AVG(frp), 2) AS mean_frp, ROUND(MAX(frp), 2) AS max_frp,
               ROUND(AVG(brightness), 2) AS mean_brightness,
               ROUND(AVG(hfai), 3) AS hfai,
               SUM(CASE WHEN daynight = 'D' THEN 1 ELSE 0 END) AS day_count,
               SUM(CASE WHEN daynight = 'N' THEN 1 ELSE 0 END) AS night_count
        FROM observations GROUP BY grid_id, acq_date;
    """)
    connection.commit()
    connection.close()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/seed_data.py <kaggle-dataset.zip>")
    rows = enrich(load_sample(Path(sys.argv[1])))
    write_outputs(rows)
    print(f"Created {CSV_PATH.name} and {DB_PATH.name} with {len(rows)} genuine sampled observations.")
    print("Run python scripts/export_static_api.py to refresh Vercel's static JSON files.")


if __name__ == "__main__":
    main()
