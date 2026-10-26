import L from "leaflet";
import { memo, useEffect, useMemo } from "react";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Pane,
  Polyline,
  TileLayer,
  Tooltip,
  ZoomControl,
  useMap,
} from "react-leaflet";
import { formatDateTime } from "../lib/format";
import { RISK_COLOR, RISK_LABEL } from "../lib/risk";
import type { TruckState } from "../lib/truck";
import type { HeatMetric, Heatmap, Plan, Route } from "../types";
import HeatmapLayer from "./HeatmapLayer";

interface Props {
  plan: Plan | null;
  selectedId: number | null;
  onSelect: (id: number) => void;
  hoveredCheckpoint: number | null;
  onHoverCheckpoint: (i: number | null) => void;
  onPickCheckpoint: (i: number) => void;
  focus: [number, number] | null;
  heatmap: Heatmap | null;
  heatVisible: boolean;
  metric: HeatMetric;
  hour: number;
  truck: TruckState | null;
}

const US_CENTER: [number, number] = [39.5, -98.35];

const pin = (letter: string, cls: string) =>
  L.divIcon({ className: "", html: `<div class="pin ${cls}">${letter}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] });
const ORIGIN_ICON = pin("A", "pin-origin");
const DEST_ICON = pin("B", "pin-dest");
const TRUCK_ICON = L.divIcon({
  className: "",
  html: `<div class="truck-marker"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M2 15V6h11v9M13 9h4l3 3.5V15h-1" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><circle cx="6.5" cy="16.5" r="2" fill="#fff"/><circle cx="16.5" cy="16.5" r="2" fill="#fff"/></svg></div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

function FitToPlan({ plan }: { plan: Plan | null }) {
  const map = useMap();
  useEffect(() => {
    if (!plan) return;
    const bounds = L.latLngBounds(plan.routes.flatMap((r) => r.geometry));
    // Extra bottom padding keeps the routes clear of the time-slider overlay.
    map.fitBounds(bounds, { paddingTopLeft: [40, 40], paddingBottomRight: [40, 170] });
  }, [map, plan]);
  return null;
}

function FlyTo({ focus }: { focus: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.flyTo(focus, Math.max(map.getZoom(), 8), { duration: 0.6 });
  }, [map, focus]);
  return null;
}

/** Route lines and checkpoints. Memoised so scrubbing the hour slider doesn't re-render them. */
const RouteLayers = memo(function RouteLayers({
  plan,
  selectedId,
  onSelect,
  hoveredCheckpoint,
  onHoverCheckpoint,
  onPickCheckpoint,
}: Pick<Props, "selectedId" | "onSelect" | "hoveredCheckpoint" | "onHoverCheckpoint" | "onPickCheckpoint"> & {
  plan: Plan;
}) {
  const selected = plan.routes.find((r) => r.id === selectedId) ?? null;
  const others = plan.routes.filter((r) => r.id !== selectedId);

  return (
    <>
      {others.map((r) => (
        <Polyline
          key={`alt-${r.id}`}
          positions={r.geometry}
          pathOptions={{ color: "#5b6b80", weight: 5, opacity: 0.5 }}
          eventHandlers={{ click: () => onSelect(r.id) }}
        >
          <Tooltip sticky>
            {r.name} · click to inspect
          </Tooltip>
        </Polyline>
      ))}
      {selected && <SelectedRoute route={selected} />}
      {selected?.checkpoints.map((c, i) => (
        <CircleMarker
          key={`${selected.id}-${i}`}
          center={[c.lat, c.lon]}
          radius={hoveredCheckpoint === i ? 9 : 5.5}
          pathOptions={{ color: "#fff", weight: 2, fillColor: RISK_COLOR[c.risk], fillOpacity: 1 }}
          eventHandlers={{
            mouseover: () => onHoverCheckpoint(i),
            mouseout: () => onHoverCheckpoint(null),
            click: () => onPickCheckpoint(i),
          }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            <div className="cp-tip">
              <strong>
                Mile {Math.round(c.mile)} · <span style={{ color: RISK_COLOR[c.risk] }}>{RISK_LABEL[c.risk]}</span>
              </strong>
              <div>ETA {formatDateTime(c.eta)}</div>
              <div>
                Wind {c.weather.wind_mph.toFixed(0)} mph (gust {c.weather.gust_mph.toFixed(0)}) · Rain{" "}
                {c.weather.rain_in_hr.toFixed(2)} · Snow {c.weather.snow_in_hr.toFixed(2)} in/hr
              </div>
              {c.reasons.length > 0 && <div className="cp-tip-reason">{c.reasons.join(", ")}</div>}
            </div>
          </Tooltip>
        </CircleMarker>
      ))}
    </>
  );
});

function SelectedRoute({ route }: { route: Route }) {
  return (
    <>
      <Polyline positions={route.geometry} pathOptions={{ color: "#fff", weight: 10, opacity: 0.95 }} interactive={false} />
      {route.risk_segments.map((s, i) => (
        <Polyline
          key={i}
          positions={s.coords}
          pathOptions={{ color: RISK_COLOR[s.risk], weight: 6, opacity: 1, lineCap: "round" }}
          interactive={false}
        />
      ))}
    </>
  );
}

export default function MapView(props: Props) {
  const { plan, focus, heatmap, heatVisible, metric, hour, truck } = props;
  const endpoints = useMemo(
    () => (plan ? { o: [plan.origin.lat, plan.origin.lon], d: [plan.destination.lat, plan.destination.lon] } : null),
    [plan],
  ) as { o: [number, number]; d: [number, number] } | null;

  return (
    <MapContainer center={US_CENTER} zoom={4} minZoom={3} maxZoom={16} className="map" preferCanvas zoomControl={false}>
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        attribution='Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors · Routing: <a href="https://project-osrm.org/">OSRM</a> · Weather: <a href="https://open-meteo.com/">Open-Meteo</a>'
        maxZoom={16}
      />
      <HeatmapLayer heatmap={heatmap} metric={metric} hour={hour} visible={heatVisible} />
      {/* Place names sit above the heatmap so they stay readable. */}
      <Pane name="labels" style={{ zIndex: 450, pointerEvents: "none" }}>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          maxZoom={16}
        />
      </Pane>
      {plan && (
        <RouteLayers
          plan={plan}
          selectedId={props.selectedId}
          onSelect={props.onSelect}
          hoveredCheckpoint={props.hoveredCheckpoint}
          onHoverCheckpoint={props.onHoverCheckpoint}
          onPickCheckpoint={props.onPickCheckpoint}
        />
      )}
      {endpoints && (
        <>
          <Marker position={endpoints.o} icon={ORIGIN_ICON}>
            <Tooltip direction="top" offset={[0, -14]}>{plan!.origin.label}</Tooltip>
          </Marker>
          <Marker position={endpoints.d} icon={DEST_ICON}>
            <Tooltip direction="top" offset={[0, -14]}>{plan!.destination.label}</Tooltip>
          </Marker>
        </>
      )}
      {truck && truck.status === "driving" && <Marker position={truck.position} icon={TRUCK_ICON} zIndexOffset={1000} />}
      <ZoomControl position="topright" />
      <FitToPlan plan={plan} />
      <FlyTo focus={focus} />
    </MapContainer>
  );
}
