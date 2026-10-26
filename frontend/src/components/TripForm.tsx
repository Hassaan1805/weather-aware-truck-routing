import { toLocalInput } from "../lib/format";
import type { Place } from "../types";
import PlaceInput from "./PlaceInput";

export interface TripFormValues {
  origin: Place;
  destination: Place;
  departureLocal: string; // datetime-local value in the browser's zone
  loadLb: string;
  interval: number;
}

interface Props {
  values: TripFormValues;
  onChange: (values: TripFormValues) => void;
  onSubmit: () => void;
  onIntervalChange: (interval: number) => void;
  loading: boolean;
}

const INTERVALS = [10, 25, 50];

export default function TripForm({ values, onChange, onSubmit, onIntervalChange, loading }: Props) {
  const set = <K extends keyof TripFormValues>(key: K, v: TripFormValues[K]) => onChange({ ...values, [key]: v });
  const now = new Date();
  const max = new Date(now.getTime() + 7 * 24 * 3600 * 1000);

  return (
    <form
      className="trip-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <PlaceInput label="Origin" value={values.origin} onChange={(p) => set("origin", p)} placeholder="City or address" />
      <button
        type="button"
        className="swap"
        title="Swap origin and destination"
        aria-label="Swap origin and destination"
        onClick={() => onChange({ ...values, origin: values.destination, destination: values.origin })}
      >
        ⇅
      </button>
      <PlaceInput
        label="Destination"
        value={values.destination}
        onChange={(p) => set("destination", p)}
        placeholder="City or address"
      />

      <div className="field-row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            required
            value={values.departureLocal}
            min={toLocalInput(new Date(now.getTime() - 3600 * 1000))}
            max={toLocalInput(max)}
            onChange={(e) => set("departureLocal", e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight</label>
          <div className="suffix-input">
            <input
              id="load"
              type="number"
              inputMode="numeric"
              required
              min={0}
              max={120000}
              step={500}
              value={values.loadLb}
              onChange={(e) => set("loadLb", e.target.value)}
            />
            <span>lb</span>
          </div>
        </div>
      </div>

      <div className="field">
        <span className="label" id="interval-label">
          Weather checkpoint every
        </span>
        <div className="segmented" role="radiogroup" aria-labelledby="interval-label">
          {INTERVALS.map((mi) => (
            <button
              key={mi}
              type="button"
              role="radio"
              aria-checked={values.interval === mi}
              className={values.interval === mi ? "on" : ""}
              onClick={() => onIntervalChange(mi)}
            >
              {mi} mi
            </button>
          ))}
        </div>
      </div>

      <button className="primary" type="submit" disabled={loading}>
        {loading ? "Planning routes…" : "Find safest route"}
      </button>
    </form>
  );
}
