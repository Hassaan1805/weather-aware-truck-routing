import { formatTime } from "../lib/format";
import { RISK_COLOR, RISK_LABEL } from "../lib/risk";
import type { Route } from "../types";

interface Props {
  route: Route;
  hovered: number | null;
  onHover: (i: number | null) => void;
  onPick: (i: number) => void;
}

export default function CheckpointTable({ route, hovered, onHover, onPick }: Props) {
  return (
    <div className="checkpoints">
      <h3>
        {route.name} checkpoints <span className="muted">({route.checkpoints.length})</span>
      </h3>
      <p className="hint">Hover to find one on the map. Click to see the weather at its ETA.</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th title="Sustained wind, mph">Wind</th>
              <th title="Rain, in/hr">Rain</th>
              <th title="Snow, in/hr">Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((c, i) => (
              <tr
                key={i}
                className={hovered === i ? "hovered" : ""}
                onMouseEnter={() => onHover(i)}
                onMouseLeave={() => onHover(null)}
                onClick={() => onPick(i)}
                title={c.reasons.join(", ") || "No weather concerns"}
              >
                <td>{Math.round(c.mile)}</td>
                <td>{formatTime(c.eta)}</td>
                <td className={c.factors.wind !== "low" ? "flag" : ""}>
                  {c.weather.wind_mph.toFixed(0)}
                  {c.load_applied && <sup title="Raised by load-weight rule">⚖</sup>}
                </td>
                <td className={c.factors.rain !== "low" ? "flag" : ""}>{c.weather.rain_in_hr.toFixed(2)}</td>
                <td className={c.factors.snow !== "low" ? "flag" : ""}>{c.weather.snow_in_hr.toFixed(2)}</td>
                <td>
                  <span className="dot" style={{ background: RISK_COLOR[c.risk] }} />
                  {RISK_LABEL[c.risk]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
