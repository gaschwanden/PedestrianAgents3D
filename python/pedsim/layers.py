"""Named landscape layers with user-adjustable weights.

What a pedestrian feels underfoot is the sum of several independent influences:
slope, a river crossing, marsh, thick scrub, a built-up wall line. Rather than
baking those into one opaque friction array, each influence is kept as its own
named :class:`Layer` with its own weight, so it can be inspected, drawn, and
re-weighted interactively (the viewer exposes one button per layer and adjusts
the selected layer's weight with the mouse wheel).

Combination rule -- additive, matching the flood fill's "increment the cell by
more than one" semantics::

    friction = 1 + sum(weight_i * data_i)        # for kind == "friction"
    blocked  = any(data_i > 0)                   # for kind == "block"

``data`` is normally normalised to 0..1, so a layer at weight 2.0 makes its
worst cells cost 3x a plain cell. Layers of kind ``info`` are display-only and
never affect routing, which is useful for showing elevation or a source map.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

FRICTION = "friction"
BLOCK = "block"
INFO = "info"

#: Lower bound on combined friction. Layers may be *negative* -- a river bank
#: attracts traffic by making the going easier than open country -- but the
#: cost solvers need strictly positive edge weights, so the sum is clamped here.
MIN_FRICTION = 0.1


@dataclass
class Layer:
    """One named influence on movement (or a purely visual overlay).

    Parameters
    ----------
    name:
        Short identifier, also shown on the viewer's layer button.
    data:
        ``[nx, ny]`` array aligned with the navigation grid. For ``friction``
        layers this should be normalised to roughly 0..1 (use
        :meth:`normalise`); ``inf`` marks impassable cells.
    weight:
        User-adjustable multiplier. 0 disables the layer without removing it.
    kind:
        ``friction`` (adds cost), ``block`` (makes cells impassable) or
        ``info`` (display only).
    """

    name: str
    data: np.ndarray
    weight: float = 1.0
    kind: str = FRICTION
    color: Tuple[int, int, int] = (120, 180, 255)
    visible: bool = False
    weight_step: float = 0.25
    max_weight: float = 8.0
    description: str = ""

    def __post_init__(self) -> None:
        self.data = np.asarray(self.data, dtype=float)
        if self.data.ndim != 2:
            raise ValueError(f"layer {self.name!r} data must be 2D")

    @property
    def shape(self) -> Tuple[int, int]:
        return self.data.shape  # type: ignore[return-value]

    @property
    def enabled(self) -> bool:
        return self.kind != INFO and self.weight > 0.0

    def normalise(self) -> "Layer":
        """Scale finite values into 0..1 in place (``inf`` is preserved)."""
        finite = np.isfinite(self.data)
        if finite.any():
            lo = float(self.data[finite].min())
            hi = float(self.data[finite].max())
            if hi > lo:
                self.data[finite] = (self.data[finite] - lo) / (hi - lo)
            else:
                self.data[finite] = 0.0
        return self

    def adjust_weight(self, steps: int) -> float:
        """Nudge the weight by ``steps`` increments, clamped to 0..max_weight."""
        w = self.weight + steps * self.weight_step
        self.weight = float(min(max(w, 0.0), self.max_weight))
        return self.weight

    def display_norm(self) -> np.ndarray:
        """0..1 array for drawing (``inf`` shown as the maximum)."""
        d = np.where(np.isfinite(self.data), self.data, np.nan)
        if not np.isfinite(d).any():
            return np.ones_like(self.data, dtype=float)
        lo = float(np.nanmin(d))
        hi = float(np.nanmax(d))
        out = np.zeros_like(self.data, dtype=float) if hi <= lo else (d - lo) / (hi - lo)
        return np.nan_to_num(np.asarray(out, dtype=float), nan=1.0)

    def label(self) -> str:
        if self.kind == INFO:
            return self.name
        return f"{self.name} x{self.weight:g}"


class LayerStack:
    """An ordered collection of :class:`Layer` sharing the grid's shape.

    ``version`` increments whenever anything that affects routing changes, so
    the grid can tell when its cached cost fields are stale.
    """

    def __init__(self, shape: Tuple[int, int], layers: Optional[List[Layer]] = None):
        self.shape = (int(shape[0]), int(shape[1]))
        self._layers: List[Layer] = []
        self.version = 0
        for layer in layers or []:
            self.add(layer)

    # ------------------------------------------------------------- collection
    def add(self, layer: Layer) -> Layer:
        if layer.shape != self.shape:
            raise ValueError(
                f"layer {layer.name!r} has shape {layer.shape}, expected {self.shape}"
            )
        existing = self.get(layer.name)
        if existing is not None:
            self._layers[self._layers.index(existing)] = layer
        else:
            self._layers.append(layer)
        self.touch()
        return layer

    def remove(self, name: str) -> None:
        layer = self.get(name)
        if layer is not None:
            self._layers.remove(layer)
            self.touch()

    def get(self, name: str) -> Optional[Layer]:
        for layer in self._layers:
            if layer.name == name:
                return layer
        return None

    def names(self) -> List[str]:
        return [layer.name for layer in self._layers]

    def touch(self) -> None:
        self.version += 1

    def set_weight(self, name: str, weight: float) -> None:
        layer = self.get(name)
        if layer is not None:
            layer.weight = float(max(0.0, weight))
            self.touch()

    def __iter__(self) -> Iterator[Layer]:
        return iter(self._layers)

    def __len__(self) -> int:
        return len(self._layers)

    def __getitem__(self, i: int) -> Layer:
        return self._layers[i]

    # ------------------------------------------------------------- combination
    def friction(self) -> Optional[np.ndarray]:
        """Combined friction array, or ``None`` if no friction layer is active."""
        active = [lyr for lyr in self._layers if lyr.kind == FRICTION and lyr.enabled]
        if not active:
            return None
        out = np.ones(self.shape, dtype=float)
        for lyr in active:
            out = out + lyr.weight * lyr.data
        # negative layers (bank attraction) must not drive the sum to zero
        return np.where(np.isfinite(out), np.maximum(out, MIN_FRICTION), out)

    def blocked(self) -> Optional[np.ndarray]:
        """Combined impassability mask, or ``None`` if nothing blocks."""
        active = [lyr for lyr in self._layers if lyr.kind == BLOCK and lyr.enabled]
        infinite = [lyr for lyr in self._layers if lyr.kind == FRICTION and lyr.enabled]
        mask: Optional[np.ndarray] = None
        for lyr in active:
            m = lyr.data > 0.0
            mask = m if mask is None else (mask | m)
        for lyr in infinite:  # inf friction is impassable too
            m = ~np.isfinite(lyr.data)
            if m.any():
                mask = m if mask is None else (mask | m)
        return mask

    def summary(self) -> str:
        if not self._layers:
            return "no layers"
        return ", ".join(lyr.label() for lyr in self._layers)


def constant_layer(name: str, shape: Tuple[int, int], value: float = 0.0, **kw) -> Layer:
    """Convenience for an empty layer you fill in later."""
    return Layer(name=name, data=np.full(shape, float(value)), **kw)
