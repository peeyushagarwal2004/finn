"""Background notifications via Web Push.

Each device that turns on notifications sends its push subscription together with its own
alert rules and mutes. A scheduled ping (/api/tick, every 10 minutes from GitHub Actions)
refreshes the data, builds each device's digest, and pushes any alert it hasn't sent yet.
The same ping keeps the free server awake, so it never cold-starts.

Render's free disk is wiped on restart, so devices also re-send their subscription every
time the app opens; a lost subscription heals itself on the next visit.
"""
import hashlib
import json
import logging
import os
import time

from .. import store
from . import digest

log = logging.getLogger("finn.push")


def public_key():
    return os.environ.get("VAPID_PUBLIC_KEY")


def subscribe(sub, rules, muted):
    endpoint = (sub or {}).get("endpoint")
    if not endpoint:
        return False
    key = hashlib.sha1(endpoint.encode()).hexdigest()
    old = store.kv_get("push", key) or {}
    store.kv_set("push", key, {"sub": sub, "rules": rules or {}, "muted": muted or [], "sent": old.get("sent", [])})
    return True


def unsubscribe(sub):
    endpoint = (sub or {}).get("endpoint", "")
    with store._lock:
        store._conn.execute("DELETE FROM kv WHERE ns='push' AND k=?", (hashlib.sha1(endpoint.encode()).hexdigest(),))
        store._conn.commit()


def _send(sub, payload):
    from py_vapid import Vapid01
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info=sub, data=json.dumps(payload),
                vapid_private_key=Vapid01.from_raw(os.environ["VAPID_PRIVATE_KEY"].encode()),
                vapid_claims={"sub": os.environ.get("VAPID_CONTACT", "mailto:finn@example.com")}, ttl=6 * 3600)
        return "ok"
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        return "gone" if code in (404, 410) else f"error {code}"


def _payload(it):
    if it["kind"] == "move":
        body = it["title"] + (". No filing explains it." if it.get("unexplained") else "")
    elif it.get("results"):
        body = f"{it['results']['period']}: {it['results']['headline']}"
    else:
        body = it.get("oneliner") or it["title"]
    return {"title": f"{it['symbol']} · {it['category_label']}", "body": body[:180], "tag": it["id"], "url": "/#brief"}


def tick():
    """Send each subscribed device the alerts it hasn't seen. Returns a small report."""
    if not os.environ.get("VAPID_PRIVATE_KEY"):
        return {"devices": 0, "sent": 0, "note": "push not configured"}
    subs = store.kv_all("push")
    sent = gone = 0
    cutoff = time.time() - 36 * 3600  # only recent alerts; never replay old news to a new device
    for key, rec in subs.items():
        d = digest.build(hours=24, rules=rec["rules"], muted=rec["muted"])
        seen = set(rec.get("sent", []))
        fresh = [i for i in d["needs_you"] if i.get("alert") and i["id"] not in seen and i["ts"] >= cutoff]
        for it in fresh[:3]:  # a burst cap: three pings at most per check
            res = _send(rec["sub"], _payload(it))
            if res == "gone":
                unsubscribe(rec["sub"])
                gone += 1
                break
            if res == "ok":
                sent += 1
            seen.add(it["id"])
        else:
            rec["sent"] = list(seen)[-500:]
            store.kv_set("push", key, rec)
    return {"devices": len(subs) - gone, "sent": sent, "removed": gone}
