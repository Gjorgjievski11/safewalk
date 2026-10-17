from math import atan2, cos, radians, sin, sqrt
from typing import Iterable


def parse_point(value: str) -> tuple[float, float]:
    try:
        latitude, longitude = (float(part.strip()) for part in value.split(",", 1))
    except (ValueError, TypeError):
        raise ValueError("coordinates must be formatted as lat,lon") from None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("coordinates are outside valid latitude/longitude ranges")
    return latitude, longitude


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    x = (lon2 - lon1) * cos((lat1 + lat2) / 2)
    y = lat2 - lat1
    return 6371000 * sqrt(x * x + y * y)


def make_routes(
    start: tuple[float, float],
    end: tuple[float, float],
    reports: Iterable[dict],
) -> dict:
    direct = [list(start), list(end)]
    midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
    nearby = [
        report for report in reports
        if _distance((report["latitude"], report["longitude"]), (midpoint[0], midpoint[1]))
        < max(75, _distance(start, end) / 3)
    ]
    # A small perpendicular detour is a useful dependency-free fallback until
    # the optional OSM graph is present.
    safer = direct
    if nearby:
        dx, dy = end[1] - start[1], end[0] - start[0]
        length = max(sqrt(dx * dx + dy * dy), 1e-9)
        offset = 0.001
        safer = [list(start), [midpoint[0] + offset * dx / length, midpoint[1] - offset * dy / length], list(end)]
    direct_distance = round(_distance(start, end), 1)
    safer_distance = round(sum(_distance(tuple(a), tuple(b)) for a, b in zip(safer, safer[1:])), 1)
    return {
        "direct": {"coords": direct, "length": direct_distance},
        "safer": {"coords": safer, "length": safer_distance},
        "direct_distance_m": round(_distance(start, end), 1),
        "safer_distance_m": safer_distance,
        "avoided_reports": len(nearby),
    }