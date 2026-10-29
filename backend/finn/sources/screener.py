"""screener.in: standardised multi-year financials plus links to the primary documents
(results filings, annual reports, concall transcripts) and the latest announcements."""
import re
from datetime import datetime
from urllib.parse import quote

from bs4 import BeautifulSoup

from .. import store
from ..net import FetchError, fetch, fetch_json

BASE = "https://www.screener.in"


def num(s):
    """'8,77,260' -> 877260.0 ; '26%' -> 26.0 ; '(19)' -> -19.0 ; '' -> None"""
    if s is None:
        return None
    s = s.replace("₹", "").replace("Cr.", "").replace("%", "").replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def search(q, limit=8):
    if not q.strip():
        return []
    try:
        res = fetch_json(f"{BASE}/api/company/search/?q={quote(q)}", ttl=86400)
    except FetchError:
        return []
    out = []
    for r in res[:limit]:
        m = re.match(r"/company/([^/]+)/", r.get("url", ""))
        if m and r.get("id"):
            out.append({"symbol": m.group(1), "name": r["name"]})
    return out


def _label(td):
    txt = td.get_text(" ", strip=True)
    for tip in td.select("span, .tooltip, small"):  # drop inline glossary tooltips
        t = tip.get_text(" ", strip=True)
        if t and t != txt:
            txt = txt.replace(t, "")
    return re.sub(r"\s*\+\s*$", "", txt.replace("\xa0", " ")).strip()


def _table(soup, sec):
    tb = soup.select_one(f"#{sec} table.data-table") or soup.select_one(f"#{sec} table")
    if not tb:
        return None
    headers = [th.get_text(strip=True) for th in tb.select("thead th")][1:]
    rows = {}
    for tr in tb.select("tbody tr"):
        tds = tr.select("td")
        if not tds:
            continue
        lab = _label(tds[0])
        if lab:
            rows[lab] = [num(td.get_text(strip=True)) for td in tds[1:]]
    if not headers or not rows:
        return None
    return {"headers": headers, "rows": rows}


def _date(t):
    try:
        return datetime.fromisoformat(t).timestamp()
    except (TypeError, ValueError):
        return None


def _documents(soup):
    docs = {"announcements": [], "annual_reports": [], "concalls": [], "ratings": []}
    for blk in soup.select("#documents .documents"):
        head = (blk.find(["h3", "h4"]) or blk).get_text(" ", strip=True).lower()
        if head.startswith("announcements"):
            for li in blk.select("ul.list-links li"):
                a = li.find("a")
                if not a:
                    continue
                meta = a.find("div")
                summary, ts = "", None
                if meta:
                    t = meta.find("time")
                    ts = _date(t.get("datetime")) if t else None
                    mtxt = meta.get_text(" ", strip=True)
                    summary = mtxt.split(" - ", 1)[1].strip() if " - " in mtxt else ""
                    meta.extract()
                docs["announcements"].append({"title": a.get_text(" ", strip=True), "url": a.get("href"),
                                              "ts": ts, "summary": summary})
        elif head.startswith("annual"):
            for li in blk.select("li"):
                a = li.find("a")
                y = re.search(r"(20\d\d)", li.get_text(" ", strip=True))
                if a and y:
                    docs["annual_reports"].append({"year": int(y.group(1)), "url": a.get("href")})
        elif head.startswith("concalls"):
            for li in blk.select("li"):
                txt = li.get_text(" ", strip=True)
                m = re.match(r"([A-Z][a-z]{2}) (20\d\d)", txt)
                if not m:
                    continue
                links = {a.get_text(strip=True).lower(): a.get("href") for a in li.select("a[href]")}
                docs["concalls"].append({
                    "month": m.group(1), "year": int(m.group(2)),
                    "transcript": links.get("transcript"), "ppt": links.get("ppt"), "rec": links.get("rec"),
                })
        elif head.startswith("credit"):
            for li in blk.select("li"):
                a = li.find("a")
                if a:
                    docs["ratings"].append({"text": li.get_text(" ", strip=True), "url": a.get("href")})
    return docs


def _parse(html, symbol):
    soup = BeautifulSoup(html, "html.parser")
    top = soup.select_one("#top")
    if not top or not top.select_one("h1"):
        return None
    ratios = {}
    for li in soup.select("#top-ratios li"):
        name = li.select_one(".name")
        val = li.select_one(".value")
        if name and val:
            nums = [num(x) for x in re.findall(r"[\d,]+\.?\d*", val.get_text(" ", strip=True))]
            ratios[name.get_text(strip=True)] = nums[0] if len(nums) == 1 else nums
    cid = soup.select_one("[data-company-id]")
    about = soup.select_one(".company-profile .about")
    commentary = soup.select_one(".company-profile .commentary")
    sector = [a.get_text(strip=True) for a in soup.select("#peers a[title]") if a.get_text(strip=True)]
    if not sector:
        sector = [a.get_text(strip=True) for a in soup.select("#peers p a")]
    links = [a.get("href") for a in top.select("a[href]")]
    bse = next((re.search(r"/(\d{6})/", h).group(1) for h in links if h and "bseindia" in h and re.search(r"/(\d{6})/", h)), None)
    website = next((h for h in links if h and h.startswith("http") and "bseindia" not in h and "nseindia" not in h), None)
    return {
        "symbol": symbol,
        "name": top.select_one("h1").get_text(strip=True),
        "company_id": cid.get("data-company-id") if cid else None,
        "bse_code": bse,
        "website": website,
        "about": about.get_text(" ", strip=True) if about else "",
        "key_points": commentary.get_text("\n", strip=True) if commentary else "",
        "sector": sector[:4],
        "ratios": ratios,
        "tables": {s: _table(soup, s) for s in
                   ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios", "shareholding"]},
        "documents": _documents(soup),
    }


def company(symbol, ttl=6 * 3600):
    """Consolidated view when the company reports one, standalone otherwise."""
    symbol = symbol.upper().strip()
    cached = store.kv_get("company", symbol, max_age=ttl)
    if cached:
        return cached
    data = None
    for path in (f"/company/{quote(symbol)}/consolidated/", f"/company/{quote(symbol)}/"):
        try:
            data = _parse(fetch(BASE + path, ttl=ttl), symbol)
        except FetchError:
            continue
        q = data and data["tables"].get("quarters")
        if q and any(v is not None for v in q["rows"].get(next(iter(q["rows"])), [])):
            data["basis"] = "consolidated" if "consolidated" in path else "standalone"
            break
    if not data:
        stale = store.kv_get("company", symbol)
        if stale:
            return stale
        raise FetchError(f"No screener data for {symbol}")
    store.kv_set("company", symbol, data)
    return data


def schedule(company_id, parent, section, consolidated=True):
    """Line-item breakdown behind a '+' row, e.g. capex inside Cash from Investing Activity."""
    url = (f"{BASE}/api/company/{company_id}/schedules/?parent={quote(parent)}"
           f"&section={section}&consolidated={'true' if consolidated else ''}")
    try:
        raw = fetch_json(url, ttl=24 * 3600)
    except (FetchError, ValueError):
        return {}
    return {k: {p: num(v) for p, v in series.items()} for k, series in raw.items() if isinstance(series, dict)}


def results_source_url(company_id, header):
    """'Sep 2026' -> screener redirect to the exchange-filed results PDF for that quarter."""
    mon, yr = header.split()
    m = datetime.strptime(mon, "%b").month
    return f"{BASE}/company/source/quarter/{company_id}/{m}/{yr}/"
