# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route for a trip, based on the
forecast weather along each route at the time the truck will actually be there, the load
weight, and travel time.

Enter an origin, destination, departure time and load weight. The app:

1. Gets **3 route options** (OSRM).
2. Places **checkpoints every 10 / 25 / 50 miles** and works out the truck's ETA at each one.
3. Looks up the **hourly forecast at each checkpoint's ETA** (Open-Meteo).
4. Scores every checkpoint with the **risk and load rules**.
5. **Recommends a route**: fewest Severe miles → fewest High miles → lowest average risk → shortest time.
6. Shows the routes, colour-coded checkpoints, ETAs and summaries on a map, with a **weather heatmap of
   the trip corridor** and a **0–48 h forecast slider**. A truck marker shows where you'd be at that hour.

All third-party services are free and need no API keys.

## Running locally

Requires Python 3.11+ and Node 18+.

```bash
# backend (http://127.0.0.1:8000)
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver

# frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Tests (risk rules, checkpoint sampling, ranking and the API with services stubbed):

```bash
cd backend
python manage.py test routing
```

## How it works

```
origin/destination ──► Photon geocoder
                      │
                      ▼
            OSRM: fastest + alternatives ──(fewer than 3?)──► detours through offset waypoints
                      │
                      ▼
  build_track: cumulative miles + truck time per vertex (speed capped at 65 mph)
                      │
                      ▼
  sample_checkpoints every N miles ──► ETA = departure + time to that mile
                      │
                      ▼
  Open-Meteo hourly forecast at each checkpoint, at the hour of its ETA
                      │
                      ▼
  risk.assess (wind+load, rain, snow) ──► miles per risk level ──► recommend.rank
```

| Module | What it does |
| --- | --- |
| `backend/routing/risk.py` | The brief's threshold table and load rules, as pure functions |
| `backend/routing/geo.py` | Distance and time along a polyline, checkpoint sampling, simplification |
| `backend/routing/recommend.py` | Route scoring, ranking and the one-line explanation |
| `backend/routing/planner.py` | Ties it together: routes → checkpoints → weather → risk → recommendation |
| `backend/routing/heatmap.py` | Weather grid along the corridor for 49 hourly frames |
| `backend/routing/services/` | OSRM, Photon and Open-Meteo clients (retries, batching, caching) |
| `frontend/src/map/HeatmapLayer.tsx` | Canvas layer that repaints one forecast hour per slider step |

### API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/geocode?q=` | Place autocomplete |
| `POST /api/plan` | `{origin, destination, departure, load_weight_lb, interval_miles}` → routes, checkpoints, risk, recommendation |
| `POST /api/heatmap` | `{corridor, departure, load_weight_lb}` → corridor grid with 49 hourly frames (risk, wind, rain, snow) |
| `GET /api/health` | Health check |

`/api/plan` returns the thinned route lines (`corridor`), which the client posts to `/api/heatmap`.
That keeps the backend stateless and lets the routes appear before the heatmap finishes loading.

## Risk rules

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind | <25 mph | 25–34 | 35–44 | 45–54 | ≥55 mph |
| Rain | <0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow | <0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

Load rules: ≥55 mph is No Travel for any load. 45–54 mph with more than 30,000 lb is No Travel.
35–44 mph with more than 40,000 lb is Severe.

How I read the brief:

- **Checkpoint risk** is the worst of wind (after the load rules), rain and snow.
- **Band edges** are `[lower, upper)`: 0.25 in/hr of rain is High and 35 mph is High. Where the brief says
  ">" for the top band, the edge belongs to Severe, so 1.00 in/hr of rain and 3.0 in/hr of snow are
  Severe and anything above is No Travel.
- **Inputs:** wind is the sustained 10 m wind speed (gusts are shown but not scored). Rain is Open-Meteo
  `rain + showers` and snow is `snowfall`, each the total for that hour, so they are in/hr directly.
  Rain is converted from mm and snow from cm.
- **Miles per risk level:** each checkpoint represents the road closer to it than to its neighbours
  (half the gap on each side). The miles add up exactly to the route length, whatever the interval.

## Recommendation

Routes are compared in this order:

1. **No Travel miles.** The brief doesn't list them, but they are worse than Severe, so they come first.
2. **Severe-or-worse miles.**
3. **High miles.**
4. **Average risk:** a distance-weighted mean on a 0–4 scale.
5. **Travel time.**

Values are rounded before comparing, so floating-point noise can't decide the ranking. The UI shows the
criterion that decided it, e.g. *"Route B has the fewest Severe-or-worse miles: 0 mi vs 34 mi on
Route A."* If every route has Severe or No Travel weather, it suggests a later departure.

## Assumptions and trade-offs

- **Truck speed:** OSRM's public server only has a car profile, so segment speeds are capped at 65 mph.
  Truck-only restrictions such as low bridges and hazmat bans aren't modelled, and neither are
  Hours-of-Service rest breaks. The ETA is continuous driving.
- **Three routes:** OSRM often returns only one or two alternatives. The rest come from routing through
  waypoints offset to either side of the fastest route. A detour is kept only if it is at most 1.6× the
  fastest distance and shares less than 85% of its road with the routes already chosen.
- **Weather quota:** Open-Meteo's free tier counts every location as one API call. Lookups snap to a
  0.25° lattice (about 17 mi, close to the GFS model grid), so nearby checkpoints, all three spacings and
  the heatmap cells share forecasts. Each checkpoint still uses its own ETA hour. Forecasts are cached
  per lattice point for a fixed window starting today. Set `WEATHER_GRID_DEG=0` (and ideally
  `OPEN_METEO_API_KEY`) to sample exact points.
- **Forecast range:** departures are limited to the next 7 days.
- **Times** are shown in the browser's time zone.

## Performance

- Route lines are simplified with Douglas–Peucker (about 40 m tolerance). Checkpoints and ETAs still use
  the full-resolution geometry. A cross-country plan is about 35 KB gzipped.
- The heatmap downloads all 49 frames once. Moving the slider just repaints a few hundred cells on a
  canvas (one `requestAnimationFrame`), and a CSS blur smooths the grid into a heat surface. Route layers
  are memoised so they don't re-render while you scrub.
- Weather requests are batched (100 locations each) and run in parallel. Routes are cached, so changing
  the checkpoint spacing doesn't call OSRM again and the heatmap is reused.

## Deploying

The `Dockerfile` builds the React app and serves it from Django with WhiteNoise, so the app is a single
service on one URL. On [Render](https://render.com), create a Blueprint from this repo and it will pick
up `render.yaml`. Any Docker host works:

```bash
docker build -t truck-routing .
docker run -p 8000:8000 -e DJANGO_SECRET_KEY=change-me truck-routing
```

Gunicorn runs one worker with 8 threads, so all requests share the in-memory cache.

Environment variables (all optional): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
`OSRM_URL`, `GEOCODER_URL`, `OPEN_METEO_URL`, `OPEN_METEO_API_KEY`, `WEATHER_GRID_DEG`,
`WEATHER_CACHE_SECONDS`.

## Data sources

Routing © [OSRM](https://project-osrm.org/) / OpenStreetMap contributors · Geocoding
[Photon](https://photon.komoot.io/) · Weather [Open-Meteo](https://open-meteo.com/) · Basemap © Esri.
