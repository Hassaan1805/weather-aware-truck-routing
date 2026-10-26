import { useCallback, useMemo, useRef, useState } from "react";
import { ApiError, fetchHeatmap, planTrip } from "./api";
import CheckpointTable from "./components/CheckpointTable";
import RouteList from "./components/RouteList";
import TimeControl from "./components/TimeControl";
import TripForm, { type TripFormValues } from "./components/TripForm";
import { nextWholeHour, toLocalInput } from "./lib/format";
import { truckAt } from "./lib/truck";
import MapView from "./map/MapView";
import type { HeatMetric, Heatmap, Plan } from "./types";

const INITIAL: TripFormValues = {
  origin: { label: "Chicago, IL" },
  destination: { label: "Denver, CO" },
  departureLocal: toLocalInput(nextWholeHour()),
  loadLb: "42000",
  interval: 25,
};

/** Hours between the heatmap's first frame (departure, floored to the UTC hour) and departure itself. */
function departureOffsetHours(departureIso: string): number {
  const d = new Date(departureIso);
  return d.getUTCMinutes() / 60 + d.getUTCSeconds() / 3600;
}

export default function App() {
  const [values, setValues] = useState(INITIAL);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [heatmap, setHeatmap] = useState<Heatmap | null>(null);
  const [planning, setPlanning] = useState(false);
  const [heatLoading, setHeatLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [heatError, setHeatError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [focus, setFocus] = useState<[number, number] | null>(null);
  const [hour, setHour] = useState(0);
  const [metric, setMetric] = useState<HeatMetric>("risk");
  const [heatVisible, setHeatVisible] = useState(true);

  const planCtrl = useRef<AbortController | null>(null);
  const heatCtrl = useRef<AbortController | null>(null);
  const heatKey = useRef("");

  const loadHeatmap = useCallback((p: Plan) => {
    // The corridor grid doesn't depend on checkpoint spacing, so keep it if only that changed.
    const key = JSON.stringify([p.corridor.map((l) => [l[0], l[l.length - 1], l.length]), p.departure, p.load_weight_lb]);
    if (key === heatKey.current) return;
    heatCtrl.current?.abort();
    const ctrl = new AbortController();
    heatCtrl.current = ctrl;
    setHeatLoading(true);
    setHeatError(null);
    setHeatmap(null);
    fetchHeatmap(p.corridor, p.departure, p.load_weight_lb, ctrl.signal)
      .then((h) => {
        heatKey.current = key;
        setHeatmap(h);
      })
      .catch((err) => {
        if (err.name !== "AbortError") setHeatError(err instanceof ApiError ? err.message : "Couldn't load the heatmap.");
      })
      .finally(() => {
        if (heatCtrl.current === ctrl) setHeatLoading(false);
      });
  }, []);

  const runPlan = useCallback(
    (v: TripFormValues) => {
      const departure = new Date(v.departureLocal);
      if (Number.isNaN(departure.getTime())) {
        setError("Enter a valid departure time.");
        return;
      }
      planCtrl.current?.abort();
      const ctrl = new AbortController();
      planCtrl.current = ctrl;
      setPlanning(true);
      setError(null);
      planTrip(
        {
          origin: v.origin,
          destination: v.destination,
          departure: departure.toISOString(),
          load_weight_lb: Number(v.loadLb),
          interval_miles: v.interval,
        },
        ctrl.signal,
      )
        .then((p) => {
          setPlan(p);
          setSelectedId(p.recommended_route_id);
          setHovered(null);
          setHour(0);
          // Keep the resolved places so the same coordinates are reused next time.
          setValues((cur) => ({ ...cur, origin: p.origin, destination: p.destination }));
          loadHeatmap(p);
        })
        .catch((err) => {
          if (err.name !== "AbortError") setError(err instanceof ApiError ? err.message : "Something went wrong.");
        })
        .finally(() => {
          if (planCtrl.current === ctrl) setPlanning(false);
        });
    },
    [loadHeatmap],
  );

  const onIntervalChange = (interval: number) => {
    const next = { ...values, interval };
    setValues(next);
    if (plan) runPlan(next);
  };

  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null;
  const offset = plan ? departureOffsetHours(plan.departure) : 0;
  const truck = useMemo(() => (selected ? truckAt(selected, hour - offset) : null), [selected, hour, offset]);

  const pickCheckpoint = useCallback(
    (i: number) => {
      if (!selected) return;
      const cp = selected.checkpoints[i];
      setHour(Math.max(0, Math.min(48, Math.round(offset + cp.hours_from_departure))));
      setFocus([cp.lat, cp.lon]);
      setHeatVisible(true);
    },
    [selected, offset],
  );

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <div className="logo" aria-hidden>
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path d="M2 15V6h11v9M13 9h4l3 3.5V15h-1" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
              <circle cx="6.5" cy="16.5" r="2" fill="currentColor" />
              <circle cx="16.5" cy="16.5" r="2" fill="currentColor" />
            </svg>
          </div>
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p>Pick the safest route by weather, load and travel time.</p>
          </div>
        </header>

        <TripForm
          values={values}
          onChange={setValues}
          onSubmit={() => runPlan(values)}
          onIntervalChange={onIntervalChange}
          loading={planning}
        />

        {error && (
          <div className="alert error" role="alert">
            {error}
          </div>
        )}

        {plan && (
          <section className="results" aria-live="polite">
            <div className="recommendation">
              <div className="rec-label">Recommendation</div>
              <p>{plan.recommendation}</p>
              {plan.warnings.map((w) => (
                <div key={w} className="alert warn">
                  {w}
                </div>
              ))}
            </div>
            <RouteList plan={plan} selectedId={selectedId} onSelect={setSelectedId} />
            {selected && (
              <CheckpointTable route={selected} hovered={hovered} onHover={setHovered} onPick={pickCheckpoint} />
            )}
            <p className="footnote">
              Risk uses the forecast at each checkpoint's ETA: the worst of wind (adjusted for load), rain and snow.
              Truck speed is capped at 65 mph. Times are shown in your time zone.
            </p>
          </section>
        )}
      </aside>

      <main className="map-wrap">
        <MapView
          plan={plan}
          selectedId={selectedId}
          onSelect={setSelectedId}
          hoveredCheckpoint={hovered}
          onHoverCheckpoint={setHovered}
          onPickCheckpoint={pickCheckpoint}
          focus={focus}
          heatmap={heatmap}
          heatVisible={heatVisible}
          metric={metric}
          hour={hour}
          truck={truck}
        />
        {!plan && !planning && (
          <div className="map-empty">
            <strong>Plan a trip to compare routes</strong>
            <span>We'll check the forecast at every checkpoint for the time your truck will be there.</span>
          </div>
        )}
        {planning && (
          <div className="map-loading" role="status">
            <span className="spinner" /> Finding routes and checking forecasts…
          </div>
        )}
        {plan && (
          <TimeControl
            heatmap={heatmap}
            loading={heatLoading}
            hour={hour}
            onHour={setHour}
            metric={metric}
            onMetric={setMetric}
            visible={heatVisible}
            onVisible={setHeatVisible}
            departureOffsetHours={offset}
            truck={truck}
            routeName={selected?.name ?? null}
          />
        )}
        {heatError && <div className="alert error map-alert">{heatError}</div>}
      </main>
    </div>
  );
}
