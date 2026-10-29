"""Polite, cached HTTP. One request per host every ~0.6s; responses cached in SQLite."""
import threading
import time
from urllib.parse import urlparse

import requests

from . import store
from .config import UA

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
_last_hit: dict[str, float] = {}
_host_lock = threading.Lock()


class FetchError(Exception):
    pass


def _throttle(host, gap=0.6):
    with _host_lock:
        wait = _last_hit.get(host, 0) + gap - time.time()
        _last_hit[host] = time.time() + max(wait, 0)
    if wait > 0:
        time.sleep(wait)


def fetch(url, ttl=3600, binary=False, timeout=30):
    """Return text (or bytes) for url, served from cache when younger than ttl seconds."""
    hit = store.blob_get(url, max_age=ttl)
    if hit is not None:
        body = hit[0]
        return body if binary else body.decode("utf-8", "replace")
    _throttle(urlparse(url).netloc)
    try:
        r = _session.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        stale = store.blob_get(url)
        if stale is not None:  # network down: serve stale rather than fail the demo
            return stale[0] if binary else stale[0].decode("utf-8", "replace")
        raise FetchError(f"{url}: {e}") from e
    if r.status_code != 200:
        stale = store.blob_get(url)
        if stale is not None:
            return stale[0] if binary else stale[0].decode("utf-8", "replace")
        raise FetchError(f"{url}: HTTP {r.status_code}")
    store.blob_set(url, r.content, r.headers.get("content-type", ""))
    return r.content if binary else r.content.decode(r.encoding or "utf-8", "replace")


def fetch_json(url, ttl=3600):
    import json
    return json.loads(fetch(url, ttl=ttl))
