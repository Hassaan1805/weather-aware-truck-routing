"""Weather risk rules from the assessment brief.

Pure functions only, so the rules can be read and tested in isolation.

Thresholds (per checkpoint, using the forecast hour at the truck's ETA):

    Condition   Low       Moderate    High        Severe      No Travel
    Wind        <25 mph   25-34       35-44       45-54       >=55 mph
    Rain        <0.10     0.10-0.25   0.25-0.50   0.50-1.00   >1.00 in/hr
    Snow        <0.5      0.5-1.0     1.0-2.0     2.0-3.0     >3.0 in/hr

Range boundaries are read as [lower, upper): a value equal to a lower bound
belongs to the higher band (e.g. 0.25 in/hr rain is High). The top band is
strict where the brief says ">" (1.00 in/hr rain is still Severe).

Load rules raise the wind band for heavy trucks:
    >=55 mph                  -> No Travel for any load
    45-54 mph and >30,000 lb  -> No Travel
    35-44 mph and >40,000 lb  -> Severe
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def key(self) -> str:
        return self.name.lower()


# (upper bound, level) pairs, checked in order. Upper bounds are exclusive.
WIND_BANDS_MPH = [(25, Risk.LOW), (35, Risk.MODERATE), (45, Risk.HIGH), (55, Risk.SEVERE)]
RAIN_BANDS_IN_HR = [(0.10, Risk.LOW), (0.25, Risk.MODERATE), (0.50, Risk.HIGH)]
RAIN_SEVERE_MAX_IN_HR = 1.00  # inclusive: only "> 1.00" is No Travel
SNOW_BANDS_IN_HR = [(0.5, Risk.LOW), (1.0, Risk.MODERATE), (2.0, Risk.HIGH)]
SNOW_SEVERE_MAX_IN_HR = 3.0  # inclusive: only "> 3.0" is No Travel

LOAD_NO_TRAVEL_LB = 30_000  # with 45-54 mph wind
LOAD_SEVERE_LB = 40_000  # with 35-44 mph wind


def _band(value: float, bands: list[tuple[float, Risk]], severe_max: float | None, top: Risk) -> Risk:
    for upper, level in bands:
        if value < upper:
            return level
    if severe_max is not None:
        return Risk.SEVERE if value <= severe_max else Risk.NO_TRAVEL
    return top


def wind_risk(wind_mph: float) -> Risk:
    return _band(wind_mph, WIND_BANDS_MPH, None, Risk.NO_TRAVEL)


def rain_risk(rain_in_hr: float) -> Risk:
    return _band(rain_in_hr, RAIN_BANDS_IN_HR, RAIN_SEVERE_MAX_IN_HR, Risk.NO_TRAVEL)


def snow_risk(snow_in_hr: float) -> Risk:
    return _band(snow_in_hr, SNOW_BANDS_IN_HR, SNOW_SEVERE_MAX_IN_HR, Risk.NO_TRAVEL)


def load_adjusted_wind_risk(wind_mph: float, load_lb: float) -> Risk:
    """Wind band after applying the load rules."""
    base = wind_risk(wind_mph)
    if base == Risk.SEVERE and load_lb > LOAD_NO_TRAVEL_LB:
        return Risk.NO_TRAVEL
    if base == Risk.HIGH and load_lb > LOAD_SEVERE_LB:
        return Risk.SEVERE
    return base


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    load_applied: bool
    reasons: list[str] = field(default_factory=list)


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall risk at one point and time: the worst of wind (load-adjusted), rain and snow."""
    base_wind = wind_risk(wind_mph)
    wind = load_adjusted_wind_risk(wind_mph, load_lb)
    rain = rain_risk(rain_in_hr)
    snow = snow_risk(snow_in_hr)
    level = max(wind, rain, snow)

    reasons: list[str] = []
    if level > Risk.LOW:
        if wind == level:
            note = f"wind {wind_mph:.0f} mph"
            if wind != base_wind:
                note += f" with {load_lb:,.0f} lb load"
            reasons.append(note)
        if rain == level:
            reasons.append(f"rain {rain_in_hr:.2f} in/hr")
        if snow == level:
            reasons.append(f"snow {snow_in_hr:.2f} in/hr")

    return Assessment(
        level=level,
        wind=wind,
        rain=rain,
        snow=snow,
        load_applied=wind != base_wind,
        reasons=reasons,
    )
