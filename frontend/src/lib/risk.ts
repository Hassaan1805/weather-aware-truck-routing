import type { HeatMetric, RiskKey } from "../types";

export const RISK_ORDER: RiskKey[] = ["low", "moderate", "high", "severe", "no_travel"];

export const RISK_LABEL: Record<RiskKey, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
  no_travel: "No Travel",
};

export const RISK_COLOR: Record<RiskKey, string> = {
  low: "#2f9e63",
  moderate: "#e2b100",
  high: "#ef7d1a",
  severe: "#d62839",
  no_travel: "#6b1e8f",
};

type RGB = [number, number, number];

function hexToRgb(hex: string): RGB {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const RISK_RGB = RISK_ORDER.map((k) => hexToRgb(RISK_COLOR[k]));

/** Colour ramps for the weather heatmap: [value, rgb] stops; values below the first stop are transparent. */
const RAMPS: Record<Exclude<HeatMetric, "risk">, { stops: [number, RGB][]; unit: string; max: number }> = {
  wind_mph: {
    unit: "mph",
    max: 60,
    stops: [
      [10, [120, 190, 230]],
      [25, [226, 177, 0]],
      [35, [239, 125, 26]],
      [45, [214, 40, 57]],
      [55, [107, 30, 143]],
    ],
  },
  rain_in_hr: {
    unit: "in/hr",
    max: 1.2,
    stops: [
      [0.01, [140, 200, 240]],
      [0.1, [40, 120, 220]],
      [0.25, [239, 125, 26]],
      [0.5, [214, 40, 57]],
      [1.0, [107, 30, 143]],
    ],
  },
  snow_in_hr: {
    unit: "in/hr",
    max: 3.5,
    stops: [
      [0.05, [200, 220, 255]],
      [0.5, [120, 150, 240]],
      [1.0, [239, 125, 26]],
      [2.0, [214, 40, 57]],
      [3.0, [107, 30, 143]],
    ],
  },
};

export const METRIC_LABEL: Record<HeatMetric, string> = {
  risk: "Risk",
  wind_mph: "Wind",
  rain_in_hr: "Rain",
  snow_in_hr: "Snow",
};

export function metricRamp(metric: Exclude<HeatMetric, "risk">) {
  return RAMPS[metric];
}

/** RGBA fill for one heatmap cell, or null for "nothing to draw". */
export function heatColor(metric: HeatMetric, value: number): [number, number, number, number] | null {
  if (metric === "risk") {
    const rgb = RISK_RGB[Math.max(0, Math.min(4, value))];
    return [...rgb, value === 0 ? 0.16 : 0.42 + value * 0.09];
  }
  const { stops } = RAMPS[metric];
  if (value < stops[0][0]) return null;
  for (let i = 1; i < stops.length; i++) {
    const [v1, c1] = stops[i];
    if (value < v1) {
      const [v0, c0] = stops[i - 1];
      const t = (value - v0) / (v1 - v0);
      const rgb = c0.map((c, j) => Math.round(c + (c1[j] - c) * t)) as RGB;
      return [...rgb, 0.3 + 0.35 * ((i - 1 + t) / (stops.length - 1))];
    }
  }
  return [...stops[stops.length - 1][1], 0.7];
}
