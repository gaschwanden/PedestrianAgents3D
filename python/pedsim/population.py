"""Population classes: shares, speed and how much a person can carry.

The default table is an ``ASSUMPTION``. It is loaded from
``python/data/config/population.yaml`` and every entry carries ``source`` and
``confidence`` so an unsourced class can be badged in the viewers (X-06).
Shares must sum to 1. Infants are not walkers and are not in the table.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class PopClass:
    id: str
    label: str
    share: float
    speed_factor: float
    max_range_m: float
    max_load_kg: float
    source: str = ""
    confidence: str = "assumption"
    notes: str = ""

    @property
    def assumption(self) -> bool:
        return (not self.source) or self.confidence == "assumption"


@dataclass
class Population:
    classes: List[PopClass]
    load_k: float = 0.2
    source: str = ""
    confidence: str = "assumption"

    def get(self, class_id: str) -> Optional[PopClass]:
        for c in self.classes:
            if c.id == class_id:
                return c
        return None

    def ids(self) -> List[str]:
        return [c.id for c in self.classes]

    def badges(self) -> List[str]:
        """Labels that the UI should mark as assumptions."""
        out = []
        if self.assumption_header:
            out.append("population table")
        out.extend(c.label for c in self.classes if c.assumption)
        return out

    @property
    def assumption_header(self) -> bool:
        return (not self.source) or self.confidence == "assumption"

    def assign(self, agents: Sequence, rng) -> Dict[str, int]:
        """Give every agent a class by the largest-remainder method.

        The counts match the configured shares to the nearest agent, which is
        inside ±1 % for any table whose shares sum to 1 once there are more
        than a handful of agents.
        """
        n = len(agents)
        if n == 0 or not self.classes:
            return {}
        raw = [c.share * n for c in self.classes]
        counts = [int(v) for v in raw]
        leftover = n - sum(counts)
        order = sorted(range(len(self.classes)), key=lambda i: -(raw[i] - counts[i]))
        for k in range(leftover):
            counts[order[k % len(order)]] += 1
        labels: List[str] = []
        for c, k in zip(self.classes, counts):
            labels.extend([c.id] * k)
        rng.shuffle(labels)
        for agent, label in zip(agents, labels):
            agent.pclass = label
            spec = self.get(label)
            agent.speed_factor = spec.speed_factor if spec else 1.0
        return {c.id: counts[i] for i, c in enumerate(self.classes)}


def load_factor(load_kg: float, max_load_kg: float, k: float = 0.2) -> float:
    """``1 - k * load / max_load``, floored at 0.2 so a full load still moves.

    ``k`` defaults to 0.2 (``ASSUMPTION``, to be replaced by a field fit).
    """
    if max_load_kg <= 0 or load_kg <= 0:
        return 1.0
    return max(0.2, 1.0 - float(k) * float(load_kg) / float(max_load_kg))


def _class_from(entry: dict) -> PopClass:
    return PopClass(
        id=str(entry["id"]),
        label=str(entry.get("label", entry["id"])),
        share=float(entry["share"]),
        speed_factor=float(entry.get("speed_factor", 1.0)),
        max_range_m=float(entry.get("max_range_m", 30000)),
        max_load_kg=float(entry.get("max_load_kg", 20)),
        source=str(entry.get("source", "")),
        confidence=str(entry.get("confidence", "assumption")),
        notes=str(entry.get("notes", "")),
    )


def validate_shares(classes: Sequence[PopClass], tol: float = 1e-6) -> None:
    total = sum(c.share for c in classes)
    if abs(total - 1.0) > tol:
        raise ValueError(f"population shares sum to {total:.4f}, not 1")
    ids = [c.id for c in classes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate population class id in {ids}")


def from_mapping(data: dict) -> Population:
    classes = [_class_from(e) for e in data.get("classes", [])]
    if not classes:
        raise ValueError("population config has no classes")
    validate_shares(classes)
    return Population(
        classes=classes,
        load_k=float(data.get("load_k", 0.2)),
        source=str(data.get("source", "")),
        confidence=str(data.get("confidence", "assumption")),
    )


def load_population(path: Optional[str] = None) -> Population:
    from .scenario import config_path, load_yaml

    path = path or config_path("population.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return from_mapping(load_yaml(path))
