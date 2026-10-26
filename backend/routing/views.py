import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import planner
from .heatmap import corridor_heatmap
from .serializers import HeatmapRequestSerializer, PlanRequestSerializer
from .services import UpstreamError, geocoding

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
            origin = self._place(data["origin"])
            destination = self._place(data["destination"])
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

    @staticmethod
    def _place(place: dict) -> dict:
        if "lat" in place:
            return {"label": place["label"], "lat": place["lat"], "lon": place["lon"]}
        return geocoding.resolve(place["label"])


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
