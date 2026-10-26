from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

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
