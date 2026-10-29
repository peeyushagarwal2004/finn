# FINN — Financial Investment Agent

**A filter, not a feed.** FINN reads every exchange filing and end-of-day print across a portfolio and shows an investor only the few things that need them. When they want to go deeper, it *audits* management against their own words instead of summarising them.

Mobile-first web app (installable PWA) · Python/FastAPI backend · React frontend · runs fully without an LLM key, gets sharper with a free one.

---

## The point of view

Most investor tools compete on how much they show. FINN competes on how much it lets you **not read**.

| Interaction | Why |
|---|---|
| **The Brief is an inbox you clear, not a feed you scroll.** It opens on a funnel — *"41 filings → 9 need you"* — and every card can be swiped away (→ done) or used to train the filter (← *mute this kind of filing for this company*). | The goal state is *inbox zero*, and the product tells you what it set aside so you trust it. |
| **Three tiers, three treatments.** *Needs you* gets a full card, *worth a glance* gets one line, *routine* collapses into a count per category. | Presentation cost should match materiality. A trading-window notice should never look like a CEO change. |
| **Thresholds show their price before you set them.** Moving the volume slider instantly replays 90 sessions: *"these rules would have pinged you 7.5× a week."* | "Unusual" is the investor's call, so the app should show the trade-off between coverage and interruptions. |
| **Moves are cross-examined against filings.** A 4% move with no disclosure behind it is flagged *unexplained* and ranked above one with an obvious driver. | The move nobody has explained yet is the one worth a call to IR. |
| **Pull leads with a promise ledger, not a ratio wall.** Every number management committed to on the last four calls, checked against what the filed results later showed. | The brief's own example: the difference between summarising management and analysing them. |
| **Push → Pull is one tap.** Every pushed item has *Dig in →* into research on that company. Research takes voice (*"KPIT"*), and the Brief can be **played as a 60-second audio briefing** for the commute. | An investor's day moves from "what changed?" to "what does it mean?" The two modes should feel like one product. |

## What's built

### Push
- **Windowed digest**: *since your last visit* / 24h / 3d / 7d / 30d, across 18 NSE companies (mega-cap to small-cap, 14 sectors).
- **Classification + materiality** of every filing into the brief's 17 categories, with the judgment written down as rules. Examples:
  - A CFO or MD leaving scores 92; a company-secretary change scores 22.
  - An order or capex is sized against annual revenue (*"₹1,200 cr ≈ 4.5% of revenue"*). An equity raise is sized against market cap (dilution). A penalty is too: *"Immaterial size (₹56 lakh)"* drops a DMart regulatory fine to *worth a glance*.
  - "Board meeting to consider results" is a *calendar entry*, not results.
  - NSE and BSE copies of the same filing, plus the result, deck and shareholder letter of one event, are merged into one card.
- **Results cards**: Revenue, EBITDA, PBT, PAT with QoQ and YoY, **read from the exchange-filed results PDF**. SEBI's format puts this quarter, last quarter and the year-ago quarter in the first three columns, so a regex pass gets all three without a model. Every parsed row is reconciled against screener's standardised table. Rows that don't reconcile fall back individually, and the card says so. A model is used only when the regex can't place the numbers (scanned or columnar PDFs), and its output goes through the same gate. For lenders, EBITDA is replaced by NII, with a note explaining why.
- **Management-change cards**: incoming and outgoing people with roles, extracted from the filing. The bio comes, in order of trust, from:
  1. The SEBI-mandated profile inside the filing.
  2. An earlier filing FINN has stored.
  3. Wikipedia, accepted only if the article mentions the company or a business role, so a namesake never becomes your new CFO.
  
  When the filing only references an earlier intimation (as HDFC Bank's Oct 27 CEO handover does), the card says so honestly. LinkedIn is a one-tap search link rather than scraped, because its terms forbid scraping.
- **Triggered alerts**: price ±X%, volume ×N vs the 20-day average, and a **volatility-adjusted σ lens** (a 3% day is noise for a small-cap and news for a bank), plus material filings in the categories you pick. A 90-session backtest prices each rule in pings per week. Notifications fire through the service worker while the app is open.

### Pull — works on any NSE ticker
- **Promise ledger.** Guidance from the last four concall transcripts is checked against reported quarters:
  - Each promise is a metric, a band and a period (*FY27*, *H2*, *Q3*).
  - Verdicts: *Delivered / On track / Slightly behind / Missed / Not checkable*.
  - Each promise carries a verbatim quote, the speaker and a page-linked source, and a credibility score sums them up.
  
  Examples from live data: TCS kept its 26–28% margin band in FY26 (27.1%) but is *slightly behind* in FY27 (25.7%). Astral guided 20% growth for FY26 and delivered 12.6%.
- **Say vs do, call by call**: a deterministic *tone index* of management's own words next to that quarter's revenue and PAT growth. Divergence is called out (*"Tone brightened while revenue growth slowed"*).
- **Business, trajectory, balance sheet, cash quality**: computed from filed statements, plus a rules engine of *flags*. Examples: "profits aren't turning into cash (CFO/PAT 0.6× over 5y)", "working capital stretched 25 days", "shareholders diluted (PAT CAGR ≫ EPS CAGR)", "promoter stake down 2.1 pts".
- **Bull vs bear + verdict**, written by the strong model from a numbered fact sheet. Any point that doesn't cite a real fact id is dropped. Without a model, these come from the flags and the ledger.
- **Ask the transcripts** (text or voice): BM25 retrieval picks ~6 passages, and the cheap model answers with `[n]` citations. Without a model, FINN quotes the passages verbatim rather than paraphrasing.
- **Primary sources only**: filed statements, exchange filings and the company's own transcripts. No news, no broker notes, and prompts forbid outside knowledge.

## Architecture

```
            ┌──────────── sources (polite, cached) ───────────┐
NSE RSS ───►│ nse.py      poll every 5 min, keep history      │
Yahoo  ────►│ prices.py   EOD, drops unfinished session       │──► SQLite (one file):
screener ──►│ screener.py statements, filings, doc links      │    http/pdf/LLM caches,
BSE PDFs ──►│ pdf.py      text per page, cached forever       │    filings, dossiers
            └─────────────────────────────────────────────────┘
                    │                              │
        push/                                pull/
        classify.py  rules → category+score  fundamentals.py  statements → flags
        results.py   filing → QoQ/YoY        guidance.py      transcript → promises
        people.py    filing → who/bio        ledger.py        promises × quarters
        alerts.py    rules + backtest        research.py      staged job + synthesis
        digest.py    rank, dedupe, enrich    ask.py           BM25 + cited answer
                    │                              │
                    └──────── api.py (FastAPI) ────┘──► React PWA (web/)
```

### Model routing and cost

| Step | Default | Model? |
|---|---|---|
| Classify & score ~all filings | rules | never |
| Results headline numbers | regex on the filed PDF + reconciliation | cheap model only if regex fails, sees **one page** |
| Management bio | filing text → structured | cheap |
| Guidance extraction | rules pre-filter a 50-page call to ~25 sentences | cheap model *labels sentence ids*; quotes stay verbatim |
| Narrative vs numbers, bull/bear | rules | **strong** model, one call per company, citations enforced |
| Ask | BM25 → 6 passages | cheap |

- Every model answer is cached by `sha256(model + prompt)`, and filings are immutable, so a company costs model calls **once**.
- The pre-filter means the model reads ~3k tokens per call instead of ~60k.
- A full dossier is ≈5 cheap calls + 1 strong call. On Gemini's free tier that's ₹0. At list price it's well under ₹1.
- Free providers (Gemini, Groq, OpenRouter) are picked up automatically. A paid OpenAI key is used **only** with `FINN_LLM_PROVIDER=openai`, so a stray key in the environment never spends money.
- `FINN_LLM_BASE_URL` points FINN at any OpenAI-compatible server, including a local Ollama.

### Robustness ("a demo that doesn't run is the worst outcome")
- **No key**: the whole app still works on rules.
- **Source down or IP-blocked**: stale cache is served. A gzipped seed snapshot (`seed/`) boots a fresh deploy with data. A nightly GitHub Action refreshes it after market close.
- **Wrong is worse than empty**: unreconciled results numbers, implausible margin bands, uncited model claims and unquantified "promises" are all dropped rather than shown.
- NSE/BSE APIs sit behind bot protection. FINN uses only their public RSS feed and public PDF archives, and doesn't try to get around the protection.

## Run it

```bash
cd backend
pip install -r requirements.txt
cd ../web
npm ci
npm run build
cd ..
uvicorn finn.api:app --app-dir backend --port 8000
```

Open http://localhost:8000 on a phone-sized window, or add it to your home screen. For better extraction quality, optionally set a free key first:

```bash
export GEMINI_API_KEY=...   # https://aistudio.google.com — free tier
```

**Deploy**: `render.yaml` (Render free tier, Docker), or any container host: `docker build -t finn . && docker run -p 8000:8000 finn`.

## Deliberately left out
- **Annual-report deep reading.** Statements come from filed numbers. Narrative grounding uses transcripts, which are where guidance lives. A 300-page AR is the next corpus for Ask (see below).
- **LinkedIn scraping** (against its terms). Real background push uses the filing's mandated profile, Wikipedia, or a search link.
- **Accounts and server-side state.** Rules, mutes and triage live on the device. That's right for a single-investor prototype and wrong for a team, which is next.
- **Intraday data.** The brief specifies EOD, and pretending otherwise would be noise.
- **True background web-push** (needs VAPID keys and a subscription store). Notifications work while the app is open or installed.

## Where it goes next
1. **Team layer**: shared mutes and "who's on it" per card, so the inbox is cleared once per desk, not once per analyst.
2. **Annual report and investor presentation** into the Ask index: segment tables, contingent liabilities, RPTs and auditor remarks as push flags.
3. **Guidance memory across years**: a running ledger per company, so credibility becomes a time series and a screen ("show me managements that under-promise").
4. **Learn the filter**: use swipe and mute history to re-weight materiality per investor.
5. **Peer context on results**: *"margin −310 bps vs peers −80 bps"* turns a number into a judgment.
