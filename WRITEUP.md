**To:** assessment@enam.com
**Subject:** ENAM - IIT screening - 2027

Hello ENAM team,

Please find my submission for the FINN build challenge.

- **Prototype (open on a phone):** <DEPLOYED_URL>
- **Repository:** <GITHUB_URL>
- **AI build history:** <CLAUDE_CODE_TRANSCRIPT_LINK>

**What I built.** FINN is a mobile-first PWA built on one idea: *the product competes on how much it lets you not read.*

The **Brief** (push) is an inbox you clear, not a feed you scroll:
- It opens on a funnel (*"41 filings → 9 need you"*) for a window you pick, from "since your last visit" to 30 days.
- Material items get full cards: results with QoQ/YoY read straight from the exchange-filed PDF, management changes with who's coming and going and where their bio came from, and price/volume moves.
- The rest collapses to one line or a count.
- Cards swipe away to done, or teach the filter to mute that kind of filing for that company.
- The whole brief can be *played* as a 60-second audio summary.

**Alerts** let the investor set price, volume and a volatility-adjusted σ threshold. Each change instantly replays 90 sessions to show what the rule would cost in pings per week. Unusual moves are cross-checked against filings, and moves *no filing explains* are ranked highest.

**Research** (pull, any NSE ticker) leads with a **promise ledger**. Guidance from the last four concalls is turned into metric, band and period, checked against the quarters later reported, and given a verdict, a verbatim quote and a page link. Example from live data: TCS kept its 26–28% margin band in FY26 but is slightly behind in FY27. Alongside it sit a call-by-call *tone vs. numbers* view, rule-based flags on trajectory, balance sheet and cash conversion, a fact-cited bull/bear, and voice-enabled "ask the transcripts" with citations.

**Key decisions and trade-offs**
- **Deterministic first, models only where judgment is needed.** Classification, materiality, results numbers and every financial check are rules. That makes them free, instant and explainable. The cheap model only *labels* pre-filtered transcript sentences: a 50-page call becomes ~25 sentences, and quotes stay verbatim. The strong model writes one synthesis per company and must cite fact ids, or the point is dropped. Everything is cached by content hash, so each company costs model calls once. The app runs fully with no key at all.
- **Wrong is worse than empty.** Parsed results must reconcile with reported totals. Implausible margin "bands" are discarded. Rules never grade an unquantified statement. "Board meeting to consider results" is a calendar entry, not results.
- **Size things against the company.** An order is sized vs revenue, an equity raise vs market cap (dilution), and a ₹56-lakh penalty is labelled immaterial.
- **Legitimate sources only.** NSE/BSE APIs are bot-protected, so FINN polls NSE's public RSS and reads public PDF archives instead of evading the protection. For the same reason, LinkedIn is a search link rather than scraped. A seed snapshot and a nightly refresh keep the deployed demo working even if a source blocks the host.

**Deliberately left out:** annual-report deep reading (transcripts carry the guidance; ARs are next for Ask), accounts and server-side state, intraday data, and true background web-push.

**Where I'd take it next:** a desk-level shared inbox (cleared once per team), AR and investor-deck ingestion for segment, RPT and auditor flags, a multi-year credibility time series that becomes a screen, a filter that learns from swipes, and peer-relative results ("margin −310 bps vs peers −80 bps").

Thank you for the thoughtful brief.

Best regards,
<YOUR NAME>
