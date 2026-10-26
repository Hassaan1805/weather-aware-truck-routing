import { useEffect, useState } from "react";
import { METRIC_LABEL, RISK_COLOR, RISK_LABEL, RISK_ORDER, heatColor, metricRamp } from "../lib/risk";
import type { TruckState } from "../lib/truck";
import type { HeatMetric, Heatmap } from "../types";

interface Props {
  heatmap: Heatmap | null;
  loading: boolean;
  hour: number;
  onHour: (h: number) => void;
  metric: HeatMetric;
  onMetric: (m: HeatMetric) => void;
  visible: boolean;
  onVisible: (v: boolean) => void;
  departureOffsetHours: number;
  truck: TruckState | null;
  routeName: string | null;
}

const METRICS: HeatMetric[] = ["risk", "wind_mph", "rain_in_hr", "snow_in_hr"];
const PLAY_MS = 450;

function Legend({ metric }: { metric: HeatMetric }) {
  if (metric === "risk") {
    return (
      <div className="legend">
        {RISK_ORDER.map((k) => (
          <span key={k}>
            <i style={{ background: RISK_COLOR[k] }} />
            {RISK_LABEL[k]}
          </span>
        ))}
      </div>
    );
  }
  const ramp = metricRamp(metric);
  const stops = ramp.stops.map(([v]) => v);
  const gradient = stops
    .map((v, i) => {
      const c = heatColor(metric, v + 1e-9)!;
      return `rgb(${c[0]},${c[1]},${c[2]}) ${(i / (stops.length - 1)) * 100}%`;
    })
    .join(", ");
  return (
    <div className="legend ramp">
      <div className="ramp-bar" style={{ background: `linear-gradient(90deg, ${gradient})` }} />
      <div className="ramp-labels">
        {stops.map((v) => (
          <span key={v}>{v}</span>
        ))}
        <span className="unit">{ramp.unit}</span>
      </div>
    </div>
  );
}

function truckText(truck: TruckState | null, routeName: string | null): string {
  if (!truck || !routeName) return "";
  if (truck.status === "waiting") return `${routeName}: not departed yet`;
  if (truck.status === "arrived") return `${routeName}: arrived`;
  return `${routeName}: truck near mile ${Math.round(truck.mile).toLocaleString()}`;
}

export default function TimeControl(props: Props) {
  const { heatmap, hour, onHour, metric, onMetric, visible, onVisible, departureOffsetHours } = props;
  const [playing, setPlaying] = useState(false);
  const maxHour = heatmap ? heatmap.hours.length - 1 : 48;

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => onHour(hour >= maxHour ? 0 : hour + 1), PLAY_MS);
    return () => clearInterval(t);
  }, [playing, hour, maxHour, onHour]);

  const when = heatmap
    ? new Date(heatmap.hours[hour]).toLocaleString([], {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "";
  const rel = hour - departureOffsetHours;
  const relText = Math.abs(rel) < 0.05 ? "at departure" : `${rel > 0 ? "+" : "−"}${Math.abs(rel).toFixed(rel % 1 ? 1 : 0)}h from departure`;

  return (
    <div className="time-control">
      <div className="tc-top">
        <div className="metric-chips" role="radiogroup" aria-label="Heatmap layer">
          {METRICS.map((m) => (
            <button
              key={m}
              role="radio"
              aria-checked={metric === m}
              className={metric === m ? "on" : ""}
              onClick={() => {
                onMetric(m);
                onVisible(true);
              }}
            >
              {METRIC_LABEL[m]}
            </button>
          ))}
        </div>
        <label className="toggle">
          <input type="checkbox" checked={visible} onChange={(e) => onVisible(e.target.checked)} />
          Heatmap
        </label>
      </div>

      <div className="tc-slider">
        <button
          className="play"
          onClick={() => setPlaying((p) => !p)}
          disabled={!heatmap}
          aria-label={playing ? "Pause" : "Play forecast"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          min={0}
          max={maxHour}
          step={1}
          value={hour}
          disabled={!heatmap}
          onChange={(e) => {
            setPlaying(false);
            onHour(Number(e.target.value));
          }}
          aria-label="Forecast hour"
          aria-valuetext={`${when}, ${relText}`}
        />
        <div className="tc-when">
          {props.loading ? (
            <span className="muted">Loading forecast grid…</span>
          ) : heatmap ? (
            <>
              <strong>{when}</strong>
              <span className="muted">
                {" "}
                · {relText} · +{hour}h
              </span>
            </>
          ) : (
            <span className="muted">0–48 h forecast</span>
          )}
        </div>
      </div>

      <div className="tc-bottom">
        <Legend metric={metric} />
        <span className="truck-status">{truckText(props.truck, props.routeName)}</span>
      </div>
    </div>
  );
}
