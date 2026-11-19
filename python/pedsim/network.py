"""Travel times, graph metrics and a gravity model for the Taş Tepeler sites.

Least-cost time comes from the directional Dijkstra field. It is not the same
number as the time an agent actually takes, because agents follow a vision cone
rather than the geodesic. Both are reported.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .timing import TOBLER_FLAT_KMH, cost_to_minutes, metres_to_minutes

DAY_TRIP_MIN = 6.0 * 60.0     # ASSUMPTION: 6 h one way


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def straight_minutes(lat1, lon1, lat2, lon2, kmh: float = 4.5) -> float:
    """Sanity-check time on the flat. Not a model result."""
    return haversine_m(lat1, lon1, lat2, lon2) / 1000.0 / kmh * 60.0


def pair_minutes(sim, origin_idx: int, dest_idx: int) -> float:
    """Least-cost minutes from one OD to another, using that destination's field."""
    from .tasks import trip_minutes
    return trip_minutes(sim, origin_idx, dest_idx, speed_factor=1.0)


def travel_time_rows(sim, month: Optional[int] = None,
                     window_label: str = "") -> List[dict]:
    """Long-format travel times for every ordered pair of named ODs."""
    named = [(i, od) for i, od in enumerate(sim.ods)
             if od is not None and (od.site or od.name)]
    # empirical minutes logged by the simulation, if any
    buckets: Dict[Tuple[str, str], List[float]] = {}
    for rec in getattr(sim, "trip_log", []):
        key = (rec.get("origin", ""), rec.get("dest", ""))
        if "minutes" in rec:
            buckets.setdefault(key, []).append(float(rec["minutes"]))
    rows = []
    for i, a in named:
        for j, b in named:
            if i == j:
                continue
            minutes = pair_minutes(sim, i, j)
            samples = buckets.get((a.name, b.name), [])
            median = float(np.median(samples)) if samples else ""
            iqr = ""
            if len(samples) >= 2:
                q1, q3 = np.percentile(samples, [25, 75])
                iqr = float(q3 - q1)
            rows.append({
                "from": a.site or a.name,
                "to": b.site or b.name,
                "t_lcp_min": "" if not math.isfinite(minutes) else round(minutes, 2),
                "t_agent_median_min": median if median == "" else round(float(median), 2),
                "t_agent_iqr_min": iqr if iqr == "" else round(float(iqr), 2),
                "n_trips": len(samples),
                "month": month if month is not None else "",
                "window": window_label,
            })
    return rows


TRAVEL_UNITS = {
    "from": "", "to": "", "t_lcp_min": "min", "t_agent_median_min": "min",
    "t_agent_iqr_min": "min", "n_trips": "count", "month": "", "window": "",
}


def interaction_matrix(population: Sequence[float], minutes: np.ndarray,
                       beta: float = 1.0, kind: str = "power") -> np.ndarray:
    """``I_ij = P_i P_j / f(t_ij)``. Diagonal is zero. ``t`` is minutes."""
    pop = np.asarray(population, dtype=float)
    t = np.asarray(minutes, dtype=float)
    t = np.where(t <= 0, np.nan, t)
    if kind == "exponential":
        f = np.exp(beta * t)
    else:
        f = np.power(t, beta)
    I = (pop[:, None] * pop[None, :]) / f
    np.fill_diagonal(I, 0.0)
    I[~np.isfinite(I)] = 0.0
    return I


def sample_pair_counts(interaction: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """Draw ``n`` directed trips with probability proportional to ``I_ij``."""
    flat = np.asarray(interaction, dtype=float).ravel()
    total = flat.sum()
    if total <= 0:
        raise ValueError("interaction matrix is empty")
    picks = rng.choice(flat.size, size=n, p=flat / total)
    counts = np.zeros(flat.size, dtype=float)
    for p in picks:
        counts[p] += 1
    return counts.reshape(interaction.shape)


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    x = np.asarray(a, dtype=float).ravel()
    y = np.asarray(b, dtype=float).ravel()
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if x.size < 3 or x.std() == 0 or y.std() == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _upper(matrix: np.ndarray) -> np.ndarray:
    idx = np.triu_indices(matrix.shape[0], k=1)
    return np.asarray(matrix, dtype=float)[idx]


def mantel(distance_a: np.ndarray, distance_b: np.ndarray,
           permutations: int = 9999, rng: Optional[np.random.Generator] = None,
           partial: Optional[np.ndarray] = None) -> dict:
    """Mantel correlation between two symmetric matrices, upper triangle.

    ``partial``, when given, is a third matrix (straight-line distance) that
    is controlled for with a partial Mantel test.
    """
    rng = rng or np.random.default_rng(0)
    a = _upper(distance_a)
    b = _upper(distance_b)
    if partial is None:
        r = pearson(a, b)
        n = distance_a.shape[0]
        count = 0
        for _ in range(permutations):
            order = rng.permutation(n)
            bp = _upper(distance_b[np.ix_(order, order)])
            if abs(pearson(a, bp)) >= abs(r):
                count += 1
        return {"r": r, "p": (count + 1) / (permutations + 1), "permutations": permutations,
                "kind": "mantel"}
    c = _upper(partial)
    r = _partial_corr(a, b, c)
    n = distance_a.shape[0]
    count = 0
    for _ in range(permutations):
        order = rng.permutation(n)
        bp = _upper(distance_b[np.ix_(order, order)])
        if abs(_partial_corr(a, bp, c)) >= abs(r):
            count += 1
    return {"r": r, "p": (count + 1) / (permutations + 1), "permutations": permutations,
            "kind": "partial"}


def _partial_corr(a, b, c) -> float:
    def resid(y, x):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if np.std(x) == 0:
            return y - y.mean()
        slope = np.cov(x, y, ddof=0)[0, 1] / np.var(x)
        return y - (slope * (x - x.mean()) + y.mean())
    return pearson(resid(a, c), resid(b, c))


def graph_metrics(names: Sequence[str], minutes: np.ndarray,
                  day_trip_min: float = DAY_TRIP_MIN) -> Tuple[List[dict], List[dict]]:
    """Weighted degree, closeness, betweenness, eigenvector; edges under a day.

    Uses networkx when it is installed. A small fallback covers degree and
    components so the table still exists without it.
    """
    names = list(names)
    n = len(names)
    minutes = np.asarray(minutes, dtype=float)
    try:
        import networkx as nx
        graph = nx.DiGraph()
        graph.add_nodes_from(names)
        for i, a in enumerate(names):
            for j, b in enumerate(names):
                if i == j:
                    continue
                t = float(minutes[i, j])
                if math.isfinite(t):
                    graph.add_edge(a, b, weight=t, t_lcp_min=t)
        degree = dict(graph.degree(weight="weight"))
        try:
            close = nx.closeness_centrality(graph, distance="weight")
        except Exception:
            close = {name: 0.0 for name in names}
        try:
            between = nx.betweenness_centrality(graph, weight="weight", normalized=True)
        except Exception:
            between = {name: 0.0 for name in names}
        try:
            # Eigenvector wants a positive similarity. Use inverse time.
            similar = nx.DiGraph()
            similar.add_nodes_from(names)
            for u, v, data in graph.edges(data=True):
                w = data.get("weight") or 0
                if w > 0:
                    similar.add_edge(u, v, weight=1.0 / w)
            eigen = nx.eigenvector_centrality_numpy(similar, weight="weight")
        except Exception:
            eigen = {name: 0.0 for name in names}
        undirected = nx.Graph()
        undirected.add_nodes_from(names)
        for i, a in enumerate(names):
            for j in range(i + 1, n):
                t = min(float(minutes[i, j]), float(minutes[j, i]))
                if math.isfinite(t) and t <= day_trip_min:
                    undirected.add_edge(a, names[j], weight=t)
        components = list(nx.connected_components(undirected))
        comp_of = {}
        for cid, nodes in enumerate(components):
            for node in nodes:
                comp_of[node] = cid
    except ImportError:
        degree = {}
        close = {}
        between = {}
        eigen = {}
        comp_of = {}
        for i, name in enumerate(names):
            degree[name] = float(np.nansum(minutes[i]))
            close[name] = 0.0
            between[name] = 0.0
            eigen[name] = 0.0
            comp_of[name] = 0
        graph = None
    rows = []
    for i, name in enumerate(names):
        order = np.argsort(np.where(np.isfinite(minutes[i]), minutes[i], np.inf))
        neighbours = [names[k] for k in order if k != i and math.isfinite(minutes[i, k])][:5]
        rows.append({
            "site": name,
            "weighted_degree_min": round(float(degree.get(name, 0.0)), 2),
            "closeness": round(float(close.get(name, 0.0)), 6),
            "betweenness": round(float(between.get(name, 0.0)), 6),
            "eigenvector": round(float(eigen.get(name, 0.0)), 6),
            "component": int(comp_of.get(name, -1)),
            "nearest": ";".join(neighbours),
        })
    edges = []
    for i, a in enumerate(names):
        for j in range(i + 1, n):
            t = float(minutes[i, j])
            if not math.isfinite(t):
                continue
            edges.append({
                "from": a, "to": names[j], "t_lcp_min": round(t, 2),
                "within_day": int(t <= day_trip_min),
            })
    return rows, edges


def knn(names: Sequence[str], minutes: np.ndarray, k: int = 3) -> Dict[str, List[str]]:
    out = {}
    minutes = np.asarray(minutes, dtype=float)
    for i, name in enumerate(names):
        order = np.argsort(np.where(np.isfinite(minutes[i]), minutes[i], np.inf))
        out[name] = [names[j] for j in order if j != i and math.isfinite(float(minutes[i, j]))][:k]
    return out


def minutes_between_points(sim) -> np.ndarray:
    """Square matrix of least-cost minutes for named ODs, in OD order."""
    named = [(i, od) for i, od in enumerate(sim.ods) if od is not None and (od.name or od.site)]
    n = len(named)
    matrix = np.full((n, n), np.inf)
    for a, (i, _) in enumerate(named):
        matrix[a, a] = 0.0
        for b, (j, _) in enumerate(named):
            if a == b:
                continue
            matrix[a, b] = pair_minutes(sim, i, j)
    return matrix


def flat_minutes_for_distance(metres: float, base_speed: float = 1.0) -> float:
    """Minutes for a flat Dijkstra whose cost equals ``metres / base_speed``."""
    return cost_to_minutes(metres / max(base_speed, 1e-6), base_speed)
