"""Deterministic analysis of the standardised statements: snapshot, trajectory, balance sheet,
cash quality, and a set of 'flags' — observations a rule can make without a model.

Every number here comes from the company's own filed statements (via screener's tables),
so these sections cost zero model calls and never hallucinate.
"""
import re

from ..sources import screener


def _row(tbl, *names):
    if not tbl:
        return None
    for n in names:
        for k, v in tbl["rows"].items():
            if k.lower() == n.lower():
                return v
    return None


def _cagr(series, years):
    vals = [v for v in series if v is not None]
    if len(vals) <= years:
        return None
    a, b = vals[-1 - years], vals[-1]
    if not a or a <= 0 or b is None or b <= 0:
        return None
    return round(100 * ((b / a) ** (1 / years) - 1), 1)


def _annual(tbl):
    """Drop the trailing 'TTM' column for year-on-year work; keep it separately."""
    if not tbl:
        return [], {}, None
    h = tbl["headers"]
    n = len(h) - (1 if h and h[-1] == "TTM" else 0)
    rows = {k: v[:n] for k, v in tbl["rows"].items()}
    ttm = {k: v[-1] for k, v in tbl["rows"].items()} if n < len(h) else None
    return h[:n], rows, ttm


def _pick(rows, *names):
    for n in names:
        if n in rows:
            return rows[n]
    return None


def analyse(symbol):
    co = screener.company(symbol)
    T = co["tables"]
    lender = any("Financing Profit" in (T.get(t) or {}).get("rows", {}) for t in ("quarters", "profit-loss"))
    years, pl, ttm = _annual(T.get("profit-loss"))
    sales = _pick(pl, "Sales", "Revenue") or []
    op = _pick(pl, "Operating Profit", "Financing Profit") or []
    opm = _pick(pl, "OPM %", "Financing Margin %") or []
    pat = _pick(pl, "Net Profit") or []
    eps = _pick(pl, "EPS in Rs") or []
    oi = _pick(pl, "Other Income") or []
    pbt = _pick(pl, "Profit before tax") or []

    q = T.get("quarters") or {"headers": [], "rows": {}}
    qs = _pick(q["rows"], "Sales", "Revenue") or []
    qopm = _pick(q["rows"], "OPM %", "Financing Margin %") or []
    qpat = _pick(q["rows"], "Net Profit") or []
    q_yoy = [round(100 * (qs[i] / qs[i - 4] - 1), 1) if i >= 4 and qs[i] and qs[i - 4] else None for i in range(len(qs))]
    qpat_yoy = [round(100 * (qpat[i] / qpat[i - 4] - 1), 1) if i >= 4 and qpat[i] and qpat[i - 4] and qpat[i - 4] > 0 else None for i in range(len(qpat))]

    bs_h, bs, _ = _annual(T.get("balance-sheet"))
    borrow = _pick(bs, "Borrowings") or []
    eq = [(a or 0) + (b or 0) for a, b in zip(_pick(bs, "Equity Capital") or [], _pick(bs, "Reserves") or [])]
    cash_sched = screener.schedule(co["company_id"], "Other Assets", "balance-sheet", co.get("basis") == "consolidated") if co.get("company_id") and not lender else {}
    cash = cash_sched.get("Cash Equivalents") or {}
    cash_series = [cash.get(h) for h in bs_h]

    cf_h, cf, _ = _annual(T.get("cash-flow"))
    cfo = _pick(cf, "Cash from Operating Activity") or []
    cfi = _pick(cf, "Cash from Investing Activity") or []
    fcf = _pick(cf, "Free Cash Flow") or []
    pat_by_year = dict(zip(years, pat))
    cfo_pat = [round(c / pat_by_year[y], 2) if c is not None and pat_by_year.get(y) and pat_by_year[y] > 0 else None for y, c in zip(cf_h, cfo)]

    r_h, rt, _ = _annual(T.get("ratios"))
    ratio = lambda n: _pick(rt, n) or []

    sh = T.get("shareholding") or {"headers": [], "rows": {}}
    prom = _pick(sh["rows"], "Promoters") or []

    R = co["ratios"]
    hi_lo = R.get("High / Low") if isinstance(R.get("High / Low"), list) else [None, None]
    snapshot = {
        "name": co["name"], "symbol": symbol, "sector": co["sector"], "about": co["about"], "key_points": co["key_points"],
        "basis": co.get("basis"), "website": co.get("website"), "lender": lender,
        "mcap": R.get("Market Cap"), "price": R.get("Current Price"), "pe": R.get("Stock P/E"),
        "roce": R.get("ROCE"), "roe": R.get("ROE"), "div_yield": R.get("Dividend Yield"), "book_value": R.get("Book Value"),
        "hi52": hi_lo[0] if hi_lo else None, "lo52": hi_lo[1] if len(hi_lo) > 1 else None,
        "ttm_sales": (ttm or {}).get("Sales") or (ttm or {}).get("Revenue"), "ttm_pat": (ttm or {}).get("Net Profit"),
        "opm_last": qopm[-1] if qopm else None,
        "documents": {"annual_reports": co["documents"]["annual_reports"][:3], "concalls": co["documents"]["concalls"][:6]},
    }
    trajectory = {
        "years": years[-10:], "sales": sales[-10:], "op": op[-10:], "opm": opm[-10:], "pat": pat[-10:], "eps": eps[-10:],
        "cagr": {"sales_3y": _cagr(sales, 3), "sales_5y": _cagr(sales, 5), "pat_3y": _cagr(pat, 3), "pat_5y": _cagr(pat, 5),
                 "eps_3y": _cagr(eps, 3), "eps_5y": _cagr(eps, 5)},
        "quarters": {"labels": q["headers"][-8:], "sales": qs[-8:], "sales_yoy": q_yoy[-8:], "opm": qopm[-8:],
                     "pat": qpat[-8:], "pat_yoy": qpat_yoy[-8:]},
    }
    balance = {
        "years": bs_h[-6:], "borrowings": borrow[-6:], "equity": eq[-6:], "cash": cash_series[-6:],
        "de": [round(b / e, 2) if b is not None and e else None for b, e in zip(borrow[-6:], eq[-6:])],
        "net_debt": [round(b - (c or 0)) if b is not None and c is not None else None for b, c in zip(borrow[-6:], cash_series[-6:])],
        "wc_years": r_h[-6:], "debtor_days": ratio("Debtor Days")[-6:], "inventory_days": ratio("Inventory Days")[-6:],
        "payable_days": ratio("Days Payable")[-6:], "ccc": ratio("Cash Conversion Cycle")[-6:],
        "roce": ratio("ROCE %")[-6:], "roe": ratio("ROE %")[-6:],
        "promoter": {"labels": sh["headers"][-6:], "values": prom[-6:]},
    }
    cash_q = {"years": cf_h[-8:], "cfo": cfo[-8:], "cfi": cfi[-8:], "fcf": fcf[-8:], "pat": [pat_by_year.get(y) for y in cf_h[-8:]],
              "cfo_pat": cfo_pat[-8:]}
    c5 = [(c, pat_by_year.get(y)) for y, c in zip(cf_h[-5:], cfo[-5:]) if c is not None and pat_by_year.get(y)]
    cash_q["cfo_pat_5y"] = round(sum(c for c, _ in c5) / sum(p for _, p in c5), 2) if c5 and sum(p for _, p in c5) > 0 else None

    out = {"snapshot": snapshot, "trajectory": trajectory, "balance": balance, "cash": cash_q}
    out["flags"] = flags(out, oi=oi, pbt=pbt, lender=lender)
    return out


def _f(fid, tone, title, detail, section):
    return {"id": fid, "tone": tone, "title": title, "detail": detail, "section": section}


def flags(a, oi, pbt, lender):
    """Rule-based observations. tone: pos / neg / watch."""
    F = []
    tr, bal, cq = a["trajectory"], a["balance"], a["cash"]
    c3, c5 = tr["cagr"]["sales_3y"], tr["cagr"]["sales_5y"]
    yoy = [v for v in tr["quarters"]["sales_yoy"] if v is not None]
    if c3 is not None and len(yoy) >= 2:
        recent = sum(yoy[-2:]) / 2
        if recent > c3 + 5:
            F.append(_f("growth_accel", "pos", "Growth is accelerating",
                        f"Revenue grew {recent:.0f}% YoY over the last two quarters vs a {c3:.0f}% 3-year CAGR.", "trajectory"))
        elif recent < c3 - 5:
            F.append(_f("growth_decel", "neg", "Growth is slowing",
                        f"Revenue grew {recent:.0f}% YoY over the last two quarters vs a {c3:.0f}% 3-year CAGR.", "trajectory"))
    opm = [v for v in tr["opm"] if v is not None]
    if len(opm) >= 4 and not lender:
        d = opm[-1] - opm[-4]
        if abs(d) >= 2:
            F.append(_f("margin_trend", "pos" if d > 0 else "neg", f"Margins {'expanded' if d > 0 else 'compressed'} {abs(d):.0f} pts in 3 years",
                        f"Operating margin moved from {opm[-4]:.0f}% to {opm[-1]:.0f}%.", "trajectory"))
    p3, e3 = tr["cagr"]["pat_3y"], tr["cagr"]["eps_3y"]
    if p3 is not None and e3 is not None and p3 - e3 > 3:
        F.append(_f("dilution", "watch", "Shareholders are being diluted",
                    f"Profit compounded {p3:.0f}% a year over 3 years but EPS only {e3:.0f}% — the share count grew.", "trajectory"))
    if not lender:
        cp = cq.get("cfo_pat_5y")
        if cp is not None:
            if cp < 0.7:
                F.append(_f("cash_weak", "neg", "Profits aren't turning into cash",
                            f"Over 5 years operating cash flow was only {cp:.2f}× reported profit.", "cash"))
            elif cp >= 1.0:
                F.append(_f("cash_strong", "pos", "Profits are backed by cash",
                            f"Over 5 years operating cash flow was {cp:.2f}× reported profit.", "cash"))
        fcf = [v for v in cq["fcf"][-3:] if v is not None]
        if len(fcf) == 3 and all(v < 0 for v in fcf):
            F.append(_f("fcf_neg", "watch", "Three years of negative free cash flow",
                        "Capex is outrunning operating cash — growth is being funded externally.", "cash"))
        de = [v for v in bal["de"] if v is not None]
        nd = [v for v in bal["net_debt"] if v is not None]
        if nd and nd[-1] < 0:
            F.append(_f("net_cash", "pos", "Net cash balance sheet", f"Cash exceeds borrowings by ₹{-nd[-1]:,.0f} cr.", "balance"))
        elif de and de[-1] > 1:
            F.append(_f("leverage_high", "neg", "Leverage is high", f"Debt-to-equity is {de[-1]:.1f}×.", "balance"))
        if len(de) >= 3 and de[-1] - de[-3] > 0.3:
            F.append(_f("leverage_up", "watch", "Borrowing is rising", f"Debt-to-equity went from {de[-3]:.2f}× to {de[-1]:.2f}× in two years.", "balance"))
        ccc = [v for v in bal["ccc"] if v is not None]
        if len(ccc) >= 4 and ccc[-1] - ccc[-4] >= 20:
            F.append(_f("wc_stretch", "neg", "Working capital is stretching",
                        f"Cash conversion cycle lengthened from {ccc[-4]:.0f} to {ccc[-1]:.0f} days over 3 years.", "balance"))
        elif len(ccc) >= 4 and ccc[-4] - ccc[-1] >= 20:
            F.append(_f("wc_better", "pos", "Working capital is tightening",
                        f"Cash conversion cycle shortened from {ccc[-4]:.0f} to {ccc[-1]:.0f} days over 3 years.", "balance"))
        dd = [v for v in bal["debtor_days"] if v is not None]
        if len(dd) >= 3 and dd[-1] - dd[-3] >= 15:
            F.append(_f("debtors_up", "watch", "Customers are paying slower", f"Debtor days rose from {dd[-3]:.0f} to {dd[-1]:.0f}.", "balance"))
    roce = [v for v in bal["roce"] if v is not None]
    if len(roce) >= 3 and not lender:
        if roce[-1] >= 20:
            F.append(_f("roce_high", "pos", f"High returns on capital ({roce[-1]:.0f}% ROCE)", f"ROCE was {roce[-3]:.0f}% two years ago.", "balance"))
        elif roce[-1] - roce[-3] <= -5:
            F.append(_f("roce_down", "neg", "Returns on capital are falling", f"ROCE fell from {roce[-3]:.0f}% to {roce[-1]:.0f}%.", "balance"))
    oi_l = [v for v in oi if v is not None][-1:] or [None]
    pbt_l = [v for v in pbt if v is not None][-1:] or [None]
    if oi_l[0] and pbt_l[0] and pbt_l[0] > 0 and oi_l[0] / pbt_l[0] > 0.25:
        F.append(_f("other_income", "watch", "Profit leans on other income",
                    f"Other income was {100 * oi_l[0] / pbt_l[0]:.0f}% of pre-tax profit last year.", "trajectory"))
    pr = [v for v in bal["promoter"]["values"] if v is not None]
    if len(pr) >= 2 and abs(pr[-1] - pr[0]) >= 1.5:
        F.append(_f("promoter", "pos" if pr[-1] > pr[0] else "watch", f"Promoter stake {'up' if pr[-1] > pr[0] else 'down'} {abs(pr[-1] - pr[0]):.1f} pts",
                    f"From {pr[0]:.1f}% to {pr[-1]:.1f}% over the last {len(pr)} quarters.", "balance"))
    return F
