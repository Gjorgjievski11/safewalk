import csv
import io
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DB_PATH = Path(os.getenv("SAFEWALK_DB", "data/safewalk.db"))
SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed.json"


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                confidence REAL,
                brightness REAL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                street TEXT,
                draft TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        has_demo_data = connection.execute(
            "SELECT 1 FROM reports WHERE street LIKE 'Demo Street %' LIMIT 1"
        ).fetchone()
        if has_demo_data is None:
            seed = json.loads(SEED_PATH.read_text(encoding="utf-8")) if SEED_PATH.exists() else []
            connection.executemany(
                """
                INSERT INTO reports
                    (label, confidence, brightness, latitude, longitude, street, draft, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        report["label"],
                        report.get("confidence"),
                        report.get("brightness"),
                        report["lat"],
                        report["lon"],
                        report.get("street"),
                        report.get("report_text", ""),
                        report.get("created_at", datetime.now(UTC).isoformat()),
                    )
                    for report in seed
                ],
            )


def create_report(
    *,
    label: str,
    confidence: float | None,
    brightness: float | None,
    latitude: float,
    longitude: float,
    street: str | None,
    draft: str,
) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO reports
                (label, confidence, brightness, latitude, longitude, street, draft, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (label, confidence, brightness, latitude, longitude, street, draft, created_at),
        )
        report_id = cursor.lastrowid
    return get_report(report_id)  # type: ignore[arg-type]


def get_report(report_id: int) -> dict[str, Any]:
    with _connection() as connection:
        row = connection.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise LookupError(f"report {report_id} was not created")
    return dict(row)


def list_reports() -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute("SELECT * FROM reports ORDER BY created_at DESC, id DESC").fetchall()
    return [dict(row) for row in rows]


def reports_csv() -> str:
    fields = ["id", "label", "street", "lat", "lon", "report_text", "confidence", "brightness", "created_at"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for report in list_reports():
        values = {
            "id": report["id"],
            "label": report["label"],
            "street": report["street"],
            "lat": report["latitude"],
            "lon": report["longitude"],
            "report_text": report["draft"],
            "confidence": report["confidence"],
            "brightness": report["brightness"],
            "created_at": report["created_at"],
        }
        for field in ("label", "street", "report_text"):
            if isinstance(values[field], str) and values[field][:1] in "=+-@\t\r":
                values[field] = "'" + values[field]
        writer.writerow(values)
    return output.getvalue()


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False)