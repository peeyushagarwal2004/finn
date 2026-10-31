# FINN

Live demo: https://finn-6xsx.onrender.com (best on a phone)

FINN is my submission for the ENAM AI Engineer build challenge. It follows a portfolio of 18 NSE companies, reads every exchange filing and end-of-day price, and gives you a short note of what's worth reading. You can also research any NSE company, and it checks management's guidance on earnings calls against the results they reported later.

## What it does

**Note (push).** A daily note for the portfolio, with a window you can change (since your last visit, today, 3 days, a week, a month). Each item is written as a headline, for example "L&T profit up 27%, margins narrow 130 bps" or "Kaynes falls 6.3% on 3.3x volume, no filing behind it". Below the headline is the detail that matters for that kind of filing:

- Results: revenue, EBITDA, PBT and PAT against last quarter and the same quarter last year, read from the results PDF filed with the exchange.
- Management changes: who is joining and who is leaving, their roles, and a short background where one is available.
- Price moves: the close, how heavy the volume was against the 20-day average, and whether any filing explains the move.

Less important filings get one line, and routine ones (trading window notices, ESOP allotments and so on) are grouped and counted at the bottom. You can swipe an item away once you've read it, or mute that kind of filing for that company. The play button reads the note aloud.

**Alerts.** You set a daily move threshold, a volume multiple, and optionally a volatility-adjusted threshold (a 3% move means something different for a small-cap than for a large bank). You also choose which filing types should trigger an alert. When you change a setting, the page shows how many alerts those rules would have produced over the last 90 trading days, so you can tune it before saving.

**Research (pull).** Search any NSE company. FINN downloads its last four earnings call transcripts, finds the statements where management guided on revenue growth, margins or profit, and checks them against the quarters reported since. For example, it finds TCS guiding a 26-28% operating margin for FY27 when the first two quarters came in at 25.7%, and Astral guiding 20-25% growth for FY27 against 15.9% in the first quarter. Every statement links to the page of the transcript it came from.

The research page also covers the business description, multi-year growth, the balance sheet and working capital, cash conversion, a bull and bear case, and a question box that answers from the transcripts and annual report (typed or spoken).

From what I could find about how ENAM invests, the screens that matter are governance, capital allocation, return ratios, cash generation and promoter integrity, held over long periods. So I added three things aimed at those questions:

- Annual report checks. FINN reads the latest annual report (300 to 600 pages, about 20 seconds) and pulls out the auditor's opinion and firm, emphasis-of-matter or going-concern language, the number of key audit matters, the board's statement on related-party transactions, and the contingent liabilities note. Each finding is quoted with a page link rather than summarised.
- Capital allocation. Where five years of operating cash went: capex, acquisitions, dividends, interest and borrowing, from the filed cash-flow statements. For example, TCS paid out 72% as dividends, while Dixon put 75% into capex and 17% into acquisitions.
- Owner's checklist. On the portfolio screen, one table for all 18 holdings: guidance kept, five-year cash conversion, ROCE, audit opinion and the change in promoter stake.

Push and pull share the same record of guidance. When a company reports results, the results card checks the quarter against what management guided on its last call (for example, TCS's Q2 margin of 25.7% against the 26-28% it guided for FY27). The note also lists upcoming results dates, parsed from the board-meeting notices companies file. A "How FINN works" page in the app shows how many filings, PDF pages, calls and annual reports it has read, and what the model calls have cost.

## How it works

The backend is Python with FastAPI. The frontend is React, built as an installable web app and served by the same process. Everything is cached in one SQLite file.

Data sources:

- NSE's public announcements RSS feed, polled every 5 minutes. It only holds the last few hundred items and most of them are mutual fund NAV notices, so FINN stores what it sees to build its own history. NSE's and BSE's JSON APIs block automated requests and I didn't try to get around that.
- screener.in for standardised financial statements and for links to the primary documents: results filings, annual reports and concall transcripts hosted on BSE.
- Yahoo Finance (via yfinance) for end-of-day prices.

I tried to use rules wherever a rule is good enough, and a language model only where it clearly helps:

- Filing classification and importance scoring are rules. Exchange filing titles are formulaic, so a list of patterns covers nearly everything, and every score can be explained. The score also takes size into account: an order is compared with annual revenue, a share issue with market cap, and a penalty that's tiny relative to the company is marked immaterial.
- Results numbers come from the filing PDF. Indian results tables list this quarter, the previous quarter and the year-ago quarter as their first three columns, so a regex can pick all three up. Every number is then checked against screener's standardised table, and anything that doesn't match is replaced with the standardised figure.
- For transcripts, rules first cut a 50-page call down to about 25 forward-looking sentences from management. A small model then labels those sentences by id (metric, target range, period). Because the model only points at sentences, every quote shown in the app is exactly what was said.
- One call to a larger model per company writes the bull and bear case from a numbered list of facts. Any point that doesn't cite one of those facts is dropped.
- Model responses are cached by a hash of the prompt, so each company costs model calls only once.

Without an API key the whole app still works, using rules for everything. With a free Gemini or Groq key, guidance extraction and the written summaries get noticeably better. FINN will only use a paid OpenAI key if `FINN_LLM_PROVIDER=openai` is set. `FINN_LLM_BASE_URL` can point it at any OpenAI-compatible server, including a local Ollama.

## Things that went wrong along the way

- My first classifier treated "board meeting to consider results" as a results announcement and attached the previous quarter's numbers to it. Those are now treated as calendar entries, and a results card is only attached if its quarter matches the filing date.
- The same event often appears several times: once on NSE, once on BSE, and again as a results deck and a shareholder letter. I added a dedupe step that merges them into one item.
- About half the results PDFs didn't parse with regex: some were scanned, some put labels and numbers on different lines, some had formula references like "(3+4)" in the row labels. That is where the model fallback is used, and it goes through the same check against reported totals.
- The guidance parser read Pidilite's advertising spend ("3-5% of sales") as revenue growth, IndiGo's yield guidance as revenue growth, and a "16-17%" figure as a margin when it was something else. I added exclusions for cost ratios and unit metrics, and a check that throws out any margin target far from the company's actual margin level. A wrong verdict is worse than no verdict, so the rules leave out anything they can't place confidently.
- The annual report scanner first found the auditor's opinion for 20 of 22 companies and the audit firm for 15. Two reports open straight into "Opinion: We have audited..." with no heading, and my firm-name pattern was matching "the Institute of Chartered Accountants of India" instead of the signature. The signature sits just above the firm's ICAI registration number, sometimes with two joint auditors on one line, so I anchored on that. It now gets all 22.
- When I plugged in a Gemini key, the 2.5 models I had defaulted to turned out to be closed to new keys, and the 3.5 model used up its token limit thinking and returned truncated JSON. I moved to `gemini-3.5-flash` with low reasoning effort for bulk extraction and more headroom for the summary, retry on Google's frequent "high demand" responses, and fall back to rules when the JSON is malformed instead of failing the whole research page.
- HDFC Bank's CEO change filing didn't include the new CEO's profile; it referred to an earlier filing. Instead of guessing, the app says where the profile was filed and links a LinkedIn search.

## Running it

```bash
cd backend
pip install -r requirements.txt
cd ../web
npm ci
npm run build
cd ..
uvicorn finn.api:app --app-dir backend --port 8000
```

Then open http://localhost:8000. A compressed snapshot of the data is included in `seed/`, so the app has something to show even if a source is unreachable. A GitHub Action refreshes it each weekday after market close. To deploy, use `render.yaml` on Render or build the Dockerfile.

## What I left out

- Scraping LinkedIn, which its terms don't allow. Background on a new executive comes from the appointment filing, Wikipedia, or (clearly labelled) the language model.
- User accounts. Alert rules, mutes and read status live on the device; the device sends its rules to the server along with its push subscription.
- Intraday prices. The brief asked for end-of-day data.

## Running on a free server

Render's free plan sleeps after 15 idle minutes and wipes its disk on restart. Three things work around that:

- A GitHub Action (`tick.yml`) calls `/api/tick` every 10 minutes. That keeps the server awake (one service running all month fits in the 750 free hours), refreshes filings and prices, and sends background notifications.
- Notifications use Web Push, so they arrive even when FINN is closed. Each device re-sends its subscription whenever the app opens, so a restart that wipes the server's copy fixes itself on the next visit. On iPhone, FINN has to be added to the home screen first, which is an Apple requirement.
- A compressed snapshot in `seed/` means a fresh start still has data immediately; it's refreshed nightly by another Action.

## What I'd do next

- A shared view for a team, so that once one person has read an item it's marked for everyone.
- Annual reports and investor presentations in the question box, plus alerts for things like auditor remarks, related-party transactions and contingent liabilities.
- Keep the guidance record across years, so you can see which managements usually hit their numbers.
- Use what people swipe away and mute to adjust the scoring.
- Compare results with peers, e.g. a margin drop of 310 bps against a peer average of 80 bps.
