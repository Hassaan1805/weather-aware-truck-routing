export type RiskKey = "low" | "moderate" | "high" | "severe" | "no_travel";

export type LatLon = [number, number];

export interface Place {
  label: string;
  lat?: number;
  lon?: number;
}

export interface Checkpoint {
  mile: number;
  lat: number;
  lon: number;
  eta: string;
  hours_from_departure: number;
  covers_miles: number;
  weather: { wind_mph: number; gust_mph: number; rain_in_hr: number; snow_in_hr: number };
  risk: RiskKey;
  risk_score: number;
  factors: { wind: RiskKey; rain: RiskKey; snow: RiskKey };
  load_applied: boolean;
  reasons: string[];
}

export interface Route {
  id: number;
  name: string;
  rank: number;
  via: string[];
  distance_miles: number;
  duration_hours: number;
  arrival: string;
  max_risk: RiskKey;
  avg_risk: number;
  miles_by_risk: Record<RiskKey, number>;
  severe_or_worse_miles: number;
  geometry: LatLon[];
  geometry_hours: number[];
  risk_segments: { risk: RiskKey; coords: LatLon[] }[];
  checkpoints: Checkpoint[];
}

export interface Plan {
  origin: Required<Place>;
  destination: Required<Place>;
  departure: string;
  load_weight_lb: number;
  interval_miles: number;
  recommended_route_id: number;
  recommendation: string;
  warnings: string[];
  routes: Route[];
  corridor: LatLon[][];
}

export type HeatMetric = "risk" | "wind_mph" | "rain_in_hr" | "snow_in_hr";

export interface Heatmap {
  start: string;
  hours: string[];
  cell_size: [number, number];
  cells: LatLon[];
  frames: Record<HeatMetric, number[][]>;
}

export interface TripRequest {
  origin: Place;
  destination: Place;
  departure: string;
  load_weight_lb: number;
  interval_miles: number;
}
