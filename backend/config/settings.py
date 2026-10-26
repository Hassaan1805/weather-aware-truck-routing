"""Django settings. Everything deploy-specific comes from environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes"}


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# No models: the app is a stateless API over third-party services.
DATABASES = {}

TEMPLATES = []

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "routing",
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
}

# Browser-fetched forecast batches (100 points x up to 12 days) can exceed Django's 2.5 MB default.
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

# The built React app is served from the site root by WhiteNoise, so the
# frontend and API share one origin and one deployment.
STATIC_URL = "static/"
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None
WHITENOISE_INDEX_FILE = True

USE_TZ = True
TIME_ZONE = "UTC"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Third-party services (all free, no API key). Override to point at a
# self-hosted OSRM or a commercial Open-Meteo endpoint.
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
GEOCODER_URL = os.environ.get("GEOCODER_URL", "https://photon.komoot.io/api/")
OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0")
WEATHER_CACHE_SECONDS = int(os.environ.get("WEATHER_CACHE_SECONDS", "1800"))
# Weather lookups snap to this lattice (degrees). 0 = exact points, which costs
# far more API calls; only sensible with a paid Open-Meteo key.
WEATHER_GRID_DEG = float(os.environ.get("WEATHER_GRID_DEG", "0.25"))
# Let browsers upload forecasts they fetched from Open-Meteo (see routing/prefetch.py).
WEATHER_ACCEPT_CLIENT_FORECASTS = env_bool("WEATHER_ACCEPT_CLIENT_FORECASTS", True)
