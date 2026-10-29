"""NSE's public announcements RSS. It is a rolling window of ~300 items, most of them
mutual-fund NAV notices, so FINN polls it and keeps its own history in SQLite."""
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from .. import store
from ..net import FetchError, fetch

FEEDS = ["https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"]
IST = timezone(timedelta(hours=5, minutes=30))


def _norm(name):
    name = re.sub(r"\b(limited|ltd|the|india|of)\b\.?", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", name)


def poll(symbols, names):
    """Fetch the feed, keep portfolio items, return market-wide stats for the 'noise' counter."""
    by_name = {_norm(n): s for s, n in names.items() if n}
    kept, total, nav = [], 0, 0
    for feed in FEEDS:
        try:
            xml = fetch(feed, ttl=240)
        except FetchError:
            continue
        for it in ET.fromstring(xml.encode("utf-8")).iter("item"):
            total += 1
            desc = (it.findtext("description") or "").strip()
            body, _, subject = desc.rpartition("|SUBJECT:")
            subject = subject.strip()
            if "Declaration of NAV" in subject:
                nav += 1
                continue
            link = (it.findtext("link") or "").strip()
            title = (it.findtext("title") or "").strip()
            m = re.search(r"/corporate/([A-Z0-9&\-]+)_\d{14}", link)
            sym = m.group(1) if m else by_name.get(_norm(title))
            if sym not in symbols:
                continue
            try:
                ts = datetime.strptime(it.findtext("pubDate").strip(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST).timestamp()
            except (ValueError, AttributeError):
                continue
            q = re.search(r'"([^"]{6,})"', body)
            headline = (q.group(1) if q else re.sub(r"^.*?informed the Exchange (?:about|regarding)\s*", "", body)).strip(" .")
            kept.append({
                "id": hashlib.sha1(link.encode()).hexdigest()[:16], "symbol": sym, "company": title,
                "ts": ts, "title": headline[:300], "subject": subject, "summary": body.strip()[:600],
                "url": link, "source": "NSE",
            })
    store.upsert_filings(kept)
    if total:
        store.kv_set("nse", "feed_stats", {"total": total, "nav": nav, "kept": len(kept)})
        # unique market-wide filings per IST day, for the "firehose vs. what needs you" stat
        day = datetime.now(IST).date().isoformat()
        seen = set(store.kv_get("nse", f"seen:{day}") or [])
        seen.update(hashlib.sha1(((it.findtext("link") or "") + (it.findtext("pubDate") or "")).encode()).hexdigest()[:10]
                    for it in ET.fromstring(xml.encode("utf-8")).iter("item")
                    if (it.findtext("pubDate") or "").startswith(datetime.now(IST).strftime("%d-%b-%Y")))
        store.kv_set("nse", f"seen:{day}", sorted(seen))
        counts = store.kv_get("nse", "day_counts") or {}
        counts[day] = len(seen)
        store.kv_set("nse", "day_counts", dict(sorted(counts.items())[-14:]))
    return kept
