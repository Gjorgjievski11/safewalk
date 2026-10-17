from pathlib import Path
from math import cos, radians
from typing import Iterable

import networkx as nx
import osmnx as ox


GRAPH_PATH = Path(__file__).resolve().parents[1] / "data" / "area.graphml"
DARK_PENALTY = 100
SAFE_RADIUS_M = 75
MAX_SNAP_M = 300

G = ox.load_graphml(GRAPH_PATH)


def parse_point(value: str) -> tuple[float, float]:
    try:
        latitude, longitude = (float(part.strip()) for part in value.split(",", 1))
    except (ValueError, TypeError):
        raise ValueError("coordinates must be formatted as lat,lon") from None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("coordinates are outside valid latitude/longitude ranges")
    return latitude, longitude


def _pin_coordinates(pin: dict) -> tuple[float, float]:
    try:
        latitude = pin["lat"] if pin.get("lat") is not None else pin["latitude"]
        longitude = pin["lon"] if pin.get("lon") is not None else pin["longitude"]
        return (
            float(latitude),
            float(longitude),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("reports must contain valid lat/lon coordinates") from exc


def _segment_distance(
    point: tuple[float, float],
    start: list[float],
    end: list[float],
) -> float:
    """Approximate distance in metres from a point to a lat/lon segment."""
    lat_scale = 110540
    lon_scale = 111320 * cos(radians(point[0]))
    px = (point[1] - start[1]) * lon_scale
    py = (point[0] - start[0]) * lat_scale
    bx = (end[1] - start[1]) * lon_scale
    by = (end[0] - start[0]) * lat_scale
    length_squared = bx * bx + by * by
    fraction = 0 if not length_squared else max(
        0, min(1, (px * bx + py * by) / length_squared)
    )
    return ((px - bx * fraction) ** 2 + (py - by * fraction) ** 2) ** 0.5


def _edge_distance_to_pin(u: int, v: int, data: dict, pin: tuple[float, float]) -> float:
    geometry = data.get("geometry")
    if geometry is None:
        points = [
            [float(G.nodes[u]["y"]), float(G.nodes[u]["x"])],
            [float(G.nodes[v]["y"]), float(G.nodes[v]["x"])],
        ]
    else:
        points = [[lat, lon] for lon, lat in geometry.coords]
    return min(
        _segment_distance(pin, start, end)
        for start, end in zip(points, points[1:])
    )


def _apply_costs(graph: nx.MultiDiGraph) -> None:
    for _u, _v, _key, data in graph.edges(keys=True, data=True):
        cost = float(data["length"])
        if str(data.get("lit", "")).lower() == "no":
            cost += DARK_PENALTY
        data["cost"] = cost


def _edge_data(u: int, v: int) -> dict:
    return min(G[u][v].values(), key=lambda edge: float(edge["length"]))


def _describe(path: list[int]) -> dict:
    coords: list[list[float]] = []
    for u, v in zip(path, path[1:]):
        edge = _edge_data(u, v)
        geometry = edge.get("geometry")
        if geometry is None:
            points = [
                [float(G.nodes[u]["y"]), float(G.nodes[u]["x"])],
                [float(G.nodes[v]["y"]), float(G.nodes[v]["x"])],
            ]
        else:
            points = [[lat, lon] for lon, lat in geometry.coords]
        if coords:
            points = points[1:]
        coords.extend(points)

    length = sum(float(_edge_data(u, v)["length"]) for u, v in zip(path, path[1:]))
    return {"coords": coords, "length": round(length, 1)}


def make_routes(
    start: tuple[float, float],
    end: tuple[float, float],
    reports: Iterable[dict],
) -> dict:
    pins = list(reports)
    start_node, start_distance = ox.distance.nearest_nodes(
        G, start[1], start[0], return_dist=True
    )
    end_node, end_distance = ox.distance.nearest_nodes(
        G, end[1], end[0], return_dist=True
    )
    if start_distance > MAX_SNAP_M or end_distance > MAX_SNAP_M:
        raise ValueError("point is outside the demo area")

    direct_path = nx.shortest_path(G, start_node, end_node, weight="length")
    safe_graph = G.copy()
    pin_points = [_pin_coordinates(pin) for pin in pins]
    blocked_edges = [
        (u, v, key)
        for u, v, key, data in safe_graph.edges(keys=True, data=True)
        if any(_edge_distance_to_pin(u, v, data, pin) <= SAFE_RADIUS_M for pin in pin_points)
    ]
    safe_graph.remove_edges_from(blocked_edges)
    _apply_costs(safe_graph)
    safer_path = nx.shortest_path(safe_graph, start_node, end_node, weight="cost")
    direct = _describe(direct_path)
    safer = _describe(safer_path)
    direct_reports = _reports_on_route(direct_path, pins)
    safer_reports = _reports_on_route(safer_path, pins)
    return {
        "direct": direct,
        "safer": safer,
        "direct_distance_m": direct["length"],
        "safer_distance_m": safer["length"],
        "avoided_reports": max(0, len(direct_reports) - len(safer_reports)),
    }


def _reports_on_route(path: list[int], reports: list[dict]) -> list[dict]:
    route_edges = {frozenset(edge) for edge in zip(path, path[1:])}
    matched = []
    for report in reports:
        lat, lon = _pin_coordinates(report)
        u, v, _key = ox.distance.nearest_edges(G, X=lon, Y=lat)
        if frozenset((int(u), int(v))) in route_edges:
            matched.append(report)
    return matched
