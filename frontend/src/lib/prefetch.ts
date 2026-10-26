import { uploadWeather, weatherNeeds } from "../api";
import type { LatLon, Place, TripRequest } from "../types";

const OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast";
const BATCH = 100;
const CONCURRENCY = 3;

/**
 * Fetch the trip's forecasts from Open-Meteo in the browser and hand them to the server.
 *
 * Open-Meteo's free quota is per IP. Cloud hosts share outbound IPs with many other
 * apps, so the server's own weather requests can be rate-limited before it has made
 * any. The viewer's browser has its own quota. Risk scoring still happens on the server.
 *
 * Returns the resolved places so the plan request reuses the exact same coordinates.
 */
export async function prefetchWeather(
  trip: Pick<TripRequest, "origin" | "destination" | "departure">,
  signal: AbortSignal,
): Promise<{ origin: Required<Place>; destination: Required<Place> }> {
  const needs = await weatherNeeds(trip, signal);
  const batches: LatLon[][] = [];
  for (let i = 0; i < needs.points.length; i += BATCH) batches.push(needs.points.slice(i, i + BATCH));

  const run = async (batch: LatLon[]) => {
    const params = new URLSearchParams({
      ...needs.open_meteo_params,
      latitude: batch.map((p) => p[0]).join(","),
      longitude: batch.map((p) => p[1]).join(","),
      start_date: needs.start_date,
      end_date: needs.end_date,
    });
    const resp = await fetch(`${OPEN_METEO_URL}?${params}`, { signal });
    if (!resp.ok) throw new Error(`Open-Meteo returned ${resp.status}`);
    const data = await resp.json();
    const items: { hourly: unknown }[] = Array.isArray(data) ? data : [data];
    await uploadWeather(
      batch,
      items.map((it) => it.hourly),
      signal,
    );
  };

  // A small worker pool keeps a long trip quick without flooding Open-Meteo.
  const queue = [...batches];
  await Promise.all(
    Array.from({ length: Math.min(CONCURRENCY, queue.length) }, async () => {
      for (let b = queue.shift(); b; b = queue.shift()) await run(b);
    }),
  );
  return { origin: needs.origin, destination: needs.destination };
}
