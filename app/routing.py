from pathlib import Path
from typing import Iterable

import networkx as nx
import osmnx as ox


GRAPH_PATH = Path(__file__).resolve().parents[1] / "data" / "area.graphml"
PIN_PENALTY = 200
DARK_PENALTY = 100
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


def _apply_costs(pins: list[dict]) -> None:
    bad: dict[frozenset[int], int] = {}
    if pins:
        xs, ys = zip(*((lon, lat) for lat, lon in map(_pin_coordinates, pins)))
        for u, v, _key in ox.distance.nearest_edges(G, X=xs, Y=ys):
            edge = frozenset((int(u), int(v)))
            bad[edge] = bad.get(edge, 0) + 1

    for u, v, _key, data in G.edges(keys=True, data=True):
        cost = float(data["length"]) + PIN_PENALTY * bad.get(frozenset((u, v)), 0)
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

    _apply_costs(pins)
    direct_path = nx.shortest_path(G, start_node, end_node, weight="length")
    safer_path = nx.shortest_path(G, start_node, end_node, weight="cost")
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
