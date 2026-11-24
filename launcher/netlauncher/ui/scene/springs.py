"""Damped springs integrated in small fixed steps, so motion does not depend on the frame rate."""

from __future__ import annotations

import math

MAX_DT = 0.25
SUBSTEP = 0.016


class Spring:
    def __init__(self, value: float, k: float = 16.0, damping: float = 1.0):
        self.value = float(value)
        self.target = float(value)
        self.velocity = 0.0
        self.k = k
        self.damping = damping

    def step(self, dt: float) -> float:
        dt = min(max(dt, 0.0), MAX_DT)
        if dt <= 0:
            return self.value
        n = max(1, math.ceil(dt / SUBSTEP))
        h = dt / n
        c = 2 * math.sqrt(self.k) * self.damping
        for _ in range(n):
            a = self.k * (self.target - self.value) - c * self.velocity
            self.velocity += a * h
            self.value += self.velocity * h
        return self.value

    def snap(self, value: float) -> None:
        self.value = self.target = float(value)
        self.velocity = 0.0


class Springs:
    """A named group of springs: pose channels, camera values."""

    def __init__(self, values: dict[str, float], k: dict[str, float] | None = None,
                 damping: dict[str, float] | None = None, default_k: float = 16.0):
        k, damping = k or {}, damping or {}
        self._s = {name: Spring(v, k.get(name, default_k), damping.get(name, 1.0)) for name, v in values.items()}

    def set_targets(self, d: dict[str, float]) -> None:
        for name, v in d.items():
            if name in self._s:
                self._s[name].target = float(v)

    def step(self, dt: float) -> None:
        for s in self._s.values():
            s.step(dt)

    def snap(self, d: dict[str, float]) -> None:
        for name, v in d.items():
            if name in self._s:
                self._s[name].snap(v)

    def moving(self, eps: float = 1e-3) -> bool:
        """True while any spring is still travelling towards its target."""
        return any(abs(s.target - s.value) > eps or abs(s.velocity) > eps for s in self._s.values())

    def __getitem__(self, name: str) -> float:
        return self._s[name].value

    def target(self, name: str) -> float:
        return self._s[name].target
