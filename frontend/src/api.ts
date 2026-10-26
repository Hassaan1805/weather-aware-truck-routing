import type { Heatmap, LatLon, Place, Plan, TripRequest } from "./types";

export class ApiError extends Error {}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...init.headers } });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Can't reach the server. Check your connection and try again.");
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok) throw new ApiError(errorMessage(body) ?? `Request failed (${resp.status}).`);
  return body as T;
}

/** Flatten DRF validation errors ({field: [msg]}) or {error: msg} into one line. */
function errorMessage(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  if (typeof b.error === "string") return b.error;
  const parts: string[] = [];
  const walk = (value: unknown, field: string) => {
    if (typeof value === "string") parts.push(field ? `${field.replace(/_/g, " ")}: ${value}` : value);
    else if (Array.isArray(value)) value.forEach((v) => walk(v, field));
    else if (value && typeof value === "object")
      Object.entries(value).forEach(([k, v]) => walk(v, k === "non_field_errors" ? field : k));
  };
  walk(b, "");
  return parts.length ? parts.join(" · ") : null;
}

export function searchPlaces(q: string, signal: AbortSignal): Promise<{ results: Required<Place>[] }> {
  return request(`/api/geocode?q=${encodeURIComponent(q)}`, { signal });
}

export function planTrip(trip: TripRequest, signal: AbortSignal): Promise<Plan> {
  return request("/api/plan", { method: "POST", body: JSON.stringify(trip), signal });
}

export interface WeatherNeeds {
  origin: Required<Place>;
  destination: Required<Place>;
  start_date: string;
  end_date: string;
  open_meteo_params: Record<string, string>;
  points: LatLon[];
}

export function weatherNeeds(
  trip: Pick<TripRequest, "origin" | "destination" | "departure">,
  signal: AbortSignal,
): Promise<WeatherNeeds> {
  return request("/api/weather/needs", { method: "POST", body: JSON.stringify(trip), signal });
}

export function uploadWeather(points: LatLon[], hourly: unknown[], signal: AbortSignal): Promise<{ stored: number }> {
  return request("/api/weather", { method: "POST", body: JSON.stringify({ points, hourly }), signal });
}

export function fetchHeatmap(
  corridor: LatLon[][],
  departure: string,
  loadLb: number,
  signal: AbortSignal,
): Promise<Heatmap> {
  return request("/api/heatmap", {
    method: "POST",
    body: JSON.stringify({ corridor, departure, load_weight_lb: loadLb }),
    signal,
  });
}
