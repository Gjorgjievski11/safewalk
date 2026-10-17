from contextlib import asynccontextmanager

from networkx import NetworkXNoPath
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .classify import classify_image
from .db import create_report, init_db, list_reports, reports_csv
from .drafting import draft_report
from .routing import make_routes, parse_point


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="SafeWalk API", lifespan=lifespan)


def _public_report(report: dict) -> dict:
    return {
        **report,
        "lat": report["latitude"],
        "lon": report["longitude"],
        "report_text": report["draft"],
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/classify")
async def classify(file: UploadFile = File(...)):
    try:
        return classify_image(await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/reports")
async def save_report(request: Request):
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)
    try:
        latitude = float(payload.get("latitude") if payload.get("latitude") is not None else payload["lat"])
        longitude = float(payload.get("longitude") if payload.get("longitude") is not None else payload["lon"])
        label = str(payload["label"])
        confidence = float(payload["confidence"]) if payload.get("confidence") is not None else None
        brightness = float(payload["brightness"]) if payload.get("brightness") is not None else None
        street = str(payload["street"]) if payload.get("street") else None
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="label and coordinates (lat/lon) are required",
        ) from exc
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise HTTPException(status_code=422, detail="coordinates are outside valid ranges")
    draft = draft_report(label, latitude, longitude, brightness)
    report = create_report(
        label=label,
        confidence=confidence,
        brightness=brightness,
        latitude=latitude,
        longitude=longitude,
        street=street,
        draft=draft,
    )
    return _public_report(report)


@app.get("/reports")
def reports():
    return [_public_report(report) for report in list_reports()]


@app.get("/route")
def route(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
):
    try:
        start, end = parse_point(from_), parse_point(to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return make_routes(start, end, list_reports())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NetworkXNoPath as exc:
        raise HTTPException(
            status_code=404,
            detail="no walkable path",
        ) from exc


@app.get("/hotspots")
def hotspots():
    grouped: dict[str, dict] = {}
    for report in list_reports():
        street = (report["street"] or "").strip()
        if not street:
            continue
        item = grouped.setdefault(street, {"street": street, "count": 0, "labels": {}})
        item["count"] += 1
        item["labels"][report["label"]] = item["labels"].get(report["label"], 0) + 1
    return sorted(grouped.values(), key=lambda item: item["count"], reverse=True)


@app.get("/export.csv", response_class=PlainTextResponse)
def export_csv():
    return PlainTextResponse(
        reports_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=safewalk-reports.csv"},
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")
