"""Download a filing PDF once, keep its per-page text forever (filings never change)."""
import io
import logging

from .. import store
from ..net import FetchError, fetch

logging.getLogger("pypdf").setLevel(logging.ERROR)


def pages(url, max_pages=60):
    """List of page texts ([] if unreachable or scanned). Cached by url+cap."""
    key = f"{url}#{max_pages}"
    cached = store.kv_get("pdftext", key)
    if cached is not None:
        return cached
    from pypdf import PdfReader
    try:
        body = fetch(url, ttl=10 ** 9, binary=True, timeout=60)
    except FetchError:
        return []
    if not body[:5].startswith(b"%PDF"):
        store.kv_set("pdftext", key, [])
        return []
    try:
        reader = PdfReader(io.BytesIO(body))
        out = []
        for p in reader.pages[:max_pages]:
            try:
                out.append(p.extract_text() or "")
            except Exception:
                out.append("")
    except Exception:
        out = []
    store.kv_set("pdftext", key, out)
    store.blob_del(url)  # text is what we keep; the binary would only bloat the cache
    return out
