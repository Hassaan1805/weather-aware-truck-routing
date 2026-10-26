from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .services import weather

MAX_DAYS_AHEAD = 7  # forecasts get unreliable beyond this; Open-Meteo stops at 16 days
MAX_LOAD_LB = 120_000


class PlaceSerializer(serializers.Serializer):
    """A place as picked from autocomplete, or plain text to geocode on the server."""

    label = serializers.CharField(max_length=300)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = {"label": data}
        value = super().to_internal_value(data)
        if ("lat" in value) != ("lon" in value):
            raise serializers.ValidationError("Provide both lat and lon, or neither.")
        return value


def validate_departure(value):
    now = timezone.now()
    if value < now - timedelta(hours=1):
        raise serializers.ValidationError("Departure can't be in the past.")
    if value > now + timedelta(days=MAX_DAYS_AHEAD):
        raise serializers.ValidationError(f"Departure must be within {MAX_DAYS_AHEAD} days.")
    return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_weight_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=[10, 25, 50], default=25)


class WeatherNeedsRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField(validators=[validate_departure])


class WeatherUploadSerializer(serializers.Serializer):
    """Open-Meteo ``hourly`` blocks the browser fetched, one per lattice point."""

    MAX_POINTS = 100

    points = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        min_length=1,
        max_length=MAX_POINTS,
    )
    hourly = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=MAX_POINTS)

    def validate(self, data):
        points, hourly = data["points"], data["hourly"]
        if len(points) != len(hourly):
            raise serializers.ValidationError("points and hourly must be the same length.")
        max_hours = weather.WINDOW_DAYS * 24
        clean_points, clean_hourly = [], []
        for (lat, lon), block in zip(points, hourly):
            if weather.snap(lat, lon) != (lat, lon):
                raise serializers.ValidationError("Points must be weather lattice points from /api/weather/needs.")
            series = {}
            lengths = set()
            for var in weather.HOURLY_VARIABLES:
                values = block.get(var)
                if not isinstance(values, list) or len(values) > max_hours:
                    raise serializers.ValidationError(f"hourly.{var} must be a list of at most {max_hours} values.")
                if any(v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)) for v in values):
                    raise serializers.ValidationError(f"hourly.{var} must contain numbers.")
                lengths.add(len(values))
                series[var] = values
            if len(lengths) != 1:
                raise serializers.ValidationError("All hourly series must be the same length.")
            clean_points.append((lat, lon))
            clean_hourly.append(series)
        return {"points": clean_points, "hourly": clean_hourly}


class HeatmapRequestSerializer(serializers.Serializer):
    corridor = serializers.ListField(
        child=serializers.ListField(
            child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
            min_length=2,
            max_length=400,
        ),
        min_length=1,
        max_length=3,
    )
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_weight_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)

    def validate_corridor(self, lines):
        for line in lines:
            for lat, lon in line:
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise serializers.ValidationError("Corridor coordinates out of range.")
        return [[(lat, lon) for lat, lon in line] for line in lines]
