"""Route ranking.

The brief's preference order is fewest Severe miles, then fewest High miles,
then lowest average risk, then shortest travel time. No Travel is worse than
Severe, so routes are first compared on No Travel miles, and No Travel miles
also count toward the Severe total ("Severe or worse").
"""

from __future__ import annotations

from dataclasses import dataclass

from .risk import Risk


@dataclass(frozen=True)
class RouteScore:
    no_travel_miles: float
    severe_miles: float  # Severe or worse
    high_miles: float
    avg_risk: float  # distance-weighted mean of the 0-4 risk scale
    duration_s: float

    def sort_key(self) -> tuple:
        # Rounded so tiny floating-point noise can't decide the ranking.
        return (
            round(self.no_travel_miles, 1),
            round(self.severe_miles, 1),
            round(self.high_miles, 1),
            round(self.avg_risk, 3),
            round(self.duration_s),
        )


def score(levels_and_miles: list[tuple[Risk, float]], duration_s: float) -> RouteScore:
    total = sum(m for _, m in levels_and_miles) or 1.0
    return RouteScore(
        no_travel_miles=sum(m for lvl, m in levels_and_miles if lvl == Risk.NO_TRAVEL),
        severe_miles=sum(m for lvl, m in levels_and_miles if lvl >= Risk.SEVERE),
        high_miles=sum(m for lvl, m in levels_and_miles if lvl == Risk.HIGH),
        avg_risk=sum(int(lvl) * m for lvl, m in levels_and_miles) / total,
        duration_s=duration_s,
    )


def rank(scores: list[RouteScore]) -> list[int]:
    """Indices of ``scores`` from best to worst."""
    return sorted(range(len(scores)), key=lambda i: scores[i].sort_key())


def _hours(seconds: float) -> str:
    h, m = divmod(round(seconds / 60), 60)
    return f"{h}h {m:02d}m"


def explain(best: RouteScore, runner_up: RouteScore | None, best_name: str, other_name: str) -> str:
    """One sentence on why ``best`` beat ``runner_up``, naming the deciding criterion."""
    if runner_up is None:
        return "Only one route was available."
    criteria = [
        ("no_travel_miles", "fewest No Travel miles", "mi"),
        ("severe_miles", "fewest Severe-or-worse miles", "mi"),
        ("high_miles", "fewest High-risk miles", "mi"),
        ("avg_risk", "lowest average risk", ""),
    ]
    for attr, label, unit in criteria:
        a, b = getattr(best, attr), getattr(runner_up, attr)
        precision = 3 if attr == "avg_risk" else 1
        if round(a, precision) != round(b, precision):
            if unit:
                return f"{best_name} has the {label}: {a:.0f} mi vs {b:.0f} mi on {other_name}."
            return f"{best_name} has the {label}: {a:.2f} vs {b:.2f} on {other_name}."
    if round(best.duration_s) == round(runner_up.duration_s):
        return f"{best_name} and {other_name} are tied on weather risk and travel time."
    return (
        f"Weather risk is equal, so the faster route wins: {best_name} takes "
        f"{_hours(best.duration_s)} vs {_hours(runner_up.duration_s)} on {other_name}."
    )
