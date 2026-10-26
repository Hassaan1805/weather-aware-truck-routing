import { formatDateTime, formatDuration, formatMiles } from "../lib/format";
import { RISK_COLOR, RISK_LABEL, RISK_ORDER } from "../lib/risk";
import type { Plan, Route } from "../types";

interface Props {
  plan: Plan;
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function RiskBar({ route }: { route: Route }) {
  const total = route.distance_miles || 1;
  return (
    <div className="risk-bar" aria-hidden>
      {RISK_ORDER.map((k) => {
        const miles = route.miles_by_risk[k];
        return miles > 0 ? (
          <span key={k} style={{ width: `${(miles / total) * 100}%`, background: RISK_COLOR[k] }} />
        ) : null;
      })}
    </div>
  );
}

export default function RouteList({ plan, selectedId, onSelect }: Props) {
  const routes = [...plan.routes].sort((a, b) => a.rank - b.rank);
  return (
    <div className="route-list" role="listbox" aria-label="Route options">
      {routes.map((r) => {
        const recommended = r.id === plan.recommended_route_id;
        const m = r.miles_by_risk;
        return (
          <button
            key={r.id}
            role="option"
            aria-selected={r.id === selectedId}
            className={`route-card${r.id === selectedId ? " selected" : ""}${recommended ? " recommended" : ""}`}
            onClick={() => onSelect(r.id)}
          >
            <div className="route-head">
              <span className="route-name">{r.name}</span>
              {recommended && <span className="badge">Recommended</span>}
              <span className="risk-pill" style={{ background: RISK_COLOR[r.max_risk] }}>
                max {RISK_LABEL[r.max_risk]}
              </span>
            </div>
            {r.via.length > 0 && <div className="via">via {r.via.join(" · ")}</div>}
            <div className="route-stats">
              <span>
                <strong>{formatDuration(r.duration_hours)}</strong>
              </span>
              <span>{formatMiles(r.distance_miles)}</span>
              <span>arrive {formatDateTime(r.arrival)}</span>
            </div>
            <RiskBar route={r} />
            <dl className="risk-miles">
              <div>
                <dt>Severe+</dt>
                <dd className={r.severe_or_worse_miles > 0 ? "bad" : ""}>{Math.round(r.severe_or_worse_miles)} mi</dd>
              </div>
              <div>
                <dt>High</dt>
                <dd className={m.high > 0 ? "warn" : ""}>{Math.round(m.high)} mi</dd>
              </div>
              <div>
                <dt>Avg risk</dt>
                <dd>{r.avg_risk.toFixed(2)} / 4</dd>
              </div>
              <div>
                <dt>No Travel</dt>
                <dd className={m.no_travel > 0 ? "bad" : ""}>{Math.round(m.no_travel)} mi</dd>
              </div>
            </dl>
          </button>
        );
      })}
    </div>
  );
}
