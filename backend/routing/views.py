import logging

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import planner
from .heatmap import corridor_heatmap
from .prefetch import weather_needs
from .serializers import (
    HeatmapRequestSerializer,
    PlanRequestSerializer,
    WeatherNeedsRequestSerializer,
    WeatherUploadSerializer,
)
from .services import UpstreamError, geocoding, weather

logger = logging.getLogger(__name__)


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class GeocodeView(APIView):
    def get(self, request):
        query = request.query_params.get("q", "")
        if len(query.strip()) < 2:
            return Response({"results": []})
        try:
            return Response({"results": geocoding.search(query)})
        except UpstreamError as exc:
            logger.warning("geocode failed: %s", exc)
            return _error("Place search is unavailable right now.", status.HTTP_502_BAD_GATEWAY)


class PlanView(APIView):
    def post(self, request):
        ser = PlanRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            origin = resolve_place(data["origin"])
            destination = resolve_place(data["destination"])
            plan = planner.plan_trip(
                origin,
                destination,
                data["departure"],
                data["load_weight_lb"],
                int(data["interval_miles"]),
            )
        except (geocoding.PlaceNotFound, planner.NoRouteError) as exc:
            return _error(str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
        except UpstreamError as exc:
            logger.warning("plan failed: %s", exc)
            return _error(str(exc), status.HTTP_502_BAD_GATEWAY)
        return Response(plan)


def resolve_place(place: dict) -> dict:
    if "lat" in place:
        return {"label": place["label"], "lat": place["lat"], "lon": place["lon"]}
    return geocoding.resolve(place["label"])


class WeatherNeedsView(APIView):
    """Forecast points a trip needs, for the browser to fetch from Open-Meteo itself."""

    def post(self, request):
        ser = WeatherNeedsRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            needs = weather_needs(
                resolve_place(data["origin"]), resolve_place(data["destination"]), data["departure"]
            )
        except (geocoding.PlaceNotFound, planner.NoRouteError) as exc:
            return _error(str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
        except UpstreamError as exc:
            logger.warning("weather needs failed: %s", exc)
            return _error(str(exc), status.HTTP_502_BAD_GATEWAY)
        return Response(needs)


class WeatherUploadView(APIView):
    """Accept browser-fetched Open-Meteo forecasts into the server's forecast cache."""

    def post(self, request):
        if not settings.WEATHER_ACCEPT_CLIENT_FORECASTS:
            return _error("Forecast uploads are disabled on this server.", status.HTTP_403_FORBIDDEN)
        ser = WeatherUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        stored = weather.store_client_forecasts(ser.validated_data["points"], ser.validated_data["hourly"])
        return Response({"stored": stored})


class HeatmapView(APIView):
    def post(self, request):
        ser = HeatmapRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            return Response(corridor_heatmap(data["corridor"], data["departure"], data["load_weight_lb"]))
        except UpstreamError as exc:
            logger.warning("heatmap failed: %s", exc)
            return _error(str(exc), status.HTTP_502_BAD_GATEWAY)
