import type { LatLon, Route } from "../types";

export type TruckState =
  | { status: "waiting"; position: LatLon }
  | { status: "driving"; position: LatLon; mile: number }
  | { status: "arrived"; position: LatLon };

/** Where the truck is on ``route`` a given number of hours after departure. */
export function truckAt(route: Route, hoursFromDeparture: number): TruckState {
  const { geometry: pts, geometry_hours: hrs } = route;
  if (hoursFromDeparture <= 0) return { status: "waiting", position: pts[0] };
  if (hoursFromDeparture >= hrs[hrs.length - 1]) return { status: "arrived", position: pts[pts.length - 1] };

  // Binary search for the segment containing this time.
  let lo = 0;
  let hi = hrs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (hrs[mid] <= hoursFromDeparture) lo = mid;
    else hi = mid;
  }
  const t = hrs[hi] === hrs[lo] ? 0 : (hoursFromDeparture - hrs[lo]) / (hrs[hi] - hrs[lo]);
  const [la0, lo0] = pts[lo];
  const [la1, lo1] = pts[hi];
  return {
    status: "driving",
    position: [la0 + (la1 - la0) * t, lo0 + (lo1 - lo0) * t],
    mile: mileAt(route, hoursFromDeparture),
  };
}

/** Route mile at a time, interpolated between checkpoints (which carry exact mile/time pairs). */
function mileAt(route: Route, hours: number): number {
  const cps = route.checkpoints;
  for (let i = 1; i < cps.length; i++) {
    const a = cps[i - 1];
    const b = cps[i];
    if (hours <= b.hours_from_departure) {
      const span = b.hours_from_departure - a.hours_from_departure;
      const t = span ? (hours - a.hours_from_departure) / span : 0;
      return a.mile + (b.mile - a.mile) * t;
    }
  }
  return route.distance_miles;
}
