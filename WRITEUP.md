**To:** assessment@enam.com
**Subject:** ENAM - IIT screening - 2027

Hello ENAM team,

Here is my submission for the FINN build challenge.

- Prototype: https://finn-6xsx.onrender.com (open it on a phone)
- Repository: https://github.com/peeyushagarwal2004/finn
- AI build history: the full Claude Code session export is attached

What I built: FINN follows a portfolio of 18 NSE companies. The main screen is a daily note: every filing and unusual price move in the window you choose, ranked and written as a headline. Results show revenue, EBITDA, PBT and PAT against last quarter and last year, read from the filed results PDF. Management changes show who is coming and going. Price moves show whether any filing explains them. Routine filings are grouped at the bottom. The alerts screen lets you set thresholds and shows how many alerts those settings would have produced over the last 90 trading days. The research screen works for any NSE company: it pulls guidance from the last four earnings calls and checks it against reported results, with a link to the transcript page for each statement. It also reads the latest annual report for the auditor's opinion, related-party disclosures and contingent liabilities, and shows where five years of operating cash went. When results come in, the results card is checked against the guidance management gave on its last call, and the portfolio screen has one table with these checks for every holding. I built those last parts around the criteria ENAM is known to look at: governance, capital allocation, returns and cash generation.

Main decisions:
- I used rules wherever they were reliable enough (classification, scoring, parsing results tables, all the financial checks) and a language model only for labelling guidance sentences and writing the summary. That keeps the cost close to zero, makes the scoring explainable, and the app runs fully without an API key.
- I'd rather show nothing than show something wrong. Parsed results are checked against reported totals, and guidance the rules can't interpret confidently is left out.
- NSE's and BSE's APIs block automated access, so I used the public NSE RSS feed and the public filing PDFs instead.

What I left out: user accounts and intraday data. Background alerts use Web Push, and a scheduled job keeps the free server awake so it doesn't take 50 seconds to load. The README has more detail, including a list of things that went wrong while building.

Next, I'd add a shared view for a team, compare results with peers, and track guidance accuracy across years.

Thank you,
<YOUR NAME>
