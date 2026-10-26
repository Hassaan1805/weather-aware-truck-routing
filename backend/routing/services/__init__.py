"""Clients for third-party routing, geocoding and weather APIs."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

import requests
import truststore
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Verify TLS against the OS certificate store rather than certifi's bundle, so
# corporate proxies and antivirus TLS inspection work the same as in a browser.
truststore.inject_into_ssl()

logger = logging.getLogger(__name__)


class UpstreamError(Exception):
    """A third-party service failed or returned something unusable. The message is safe to show users."""


def make_session() -> requests.Session:
    session = requests.Session()
    # 429s aren't retried: another attempt inside the same minute just burns quota.
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = settings.HTTP_USER_AGENT
    return session


def get_json(
    session: requests.Session,
    url: str,
    params: dict,
    timeout: float = 20,
    body_on_status: tuple[int, ...] = (),
) -> dict:
    """GET and decode JSON. Statuses in ``body_on_status`` return their body instead of raising."""
    host = urlsplit(url).hostname
    try:
        resp = session.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning("%s unreachable: %s", host, exc)
        raise UpstreamError(f"{host} is not responding. Please try again.") from exc

    if resp.status_code == 429:
        raise UpstreamError(f"{host} rate limit reached. Please wait a minute and try again.")
    if resp.status_code >= 400 and resp.status_code not in body_on_status:
        logger.warning("%s returned %s: %s", host, resp.status_code, resp.text[:300])
        raise UpstreamError(f"{host} returned an error ({resp.status_code}). Please try again.")
    try:
        return resp.json()
    except ValueError as exc:
        raise UpstreamError(f"{host} returned an invalid response.") from exc
