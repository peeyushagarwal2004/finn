"""Response cache for the read endpoints.

The free server has about a tenth of a CPU, so a page should never be recomputed when nothing
underneath it has changed. Every cached response is keyed by its parameters and by a data
version that the refresh loop bumps whenever it stores new filings or prices.
"""
import threading
import time

_lock = threading.Lock()
_cache: dict = {}
_version = {"n": 0}


def bump():
    with _lock:
        _version["n"] += 1
        _cache.clear()


def get(key, fn, ttl=600):
    k = (key, _version["n"])
    now = time.time()
    with _lock:
        hit = _cache.get(k)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    with _lock:
        _cache[k] = (now, val)
        if len(_cache) > 300:
            _cache.pop(next(iter(_cache)))
    return val
