"""Management change -> who is coming, who is going, and where the newcomer came from.

Bio sources, in order of trust:
  1. The filing itself: SEBI's Reg 30 requires a brief profile on appointments.
  2. An earlier filing FINN has stored that mentions the person (companies often say
     "details were provided in our intimation dated ...").
  3. Wikipedia's public API, accepted only if the article mentions the company or a
     business role, so a namesake singer never becomes the new CFO.
LinkedIn is offered as a one-tap search link rather than scraped (its terms forbid it).
"""
import re
from urllib.parse import quote

from .. import llm, store
from ..net import FetchError, fetch_json
from ..sources import pdf

HON = r"(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?|Shri|Smt\.?|Prof\.?|CA)"
NAME = re.compile(HON + r"\s+((?:[A-Z][A-Za-z.'\-]*\.?\s?){1,4})")
ROLE = re.compile(r"(managing director(?: (?:and|&) (?:chief executive officer|ceo))?|md (?:and|&) ceo|chief executive officer|"
                  r"chief financial officer|chief operating officer|chief technology officer|chief risk officer|"
                  r"whole[- ]time director|executive director|non-executive director|independent director|"
                  r"additional director|nominee director|chair(?:man|person)|company secretary|compliance officer|"
                  r"\bceo\b|\bcfo\b|\bcoo\b|\bcto\b|\bmd\b|statutory auditors?|senior management personnel|president)", re.I)
IN_WORDS = re.compile(r"appoint|assum|designat|elevat|join|re-?appoint|induct|take(?:s)? (?:over|charge)|becomes", re.I)
OUT_WORDS = re.compile(r"resign|vacat|cessation|ceas|retire|step(?:s|ped)? down|demise|superannuat|relinquish|completion of (?:his|her) tenure", re.I)


STOP = {"as", "has", "is", "the", "of", "and", "with", "from", "who", "was", "managing", "director", "chief",
        "executive", "officer", "company", "secretary", "deputy", "chairman", "chairperson", "president", "group",
        "head", "independent", "additional", "whole", "non", "md", "ceo", "cfo", "coo", "cto", "designation", "din"}


def _clean_name(n):
    n = re.sub(r"\s+", " ", n).strip(" .,")
    out = []
    for w in n.split():
        if not w[0].isupper() or w.lower().strip(".,") in STOP:
            break
        out.append(w)
    return " ".join(out[:4])


def _direction(before, after):
    """The verb closest to the name decides: 'appointment of Mr X' vs 'resignation of Ms Y'."""
    b = before[-70:]
    b = re.split(r"[.;,]\s|\sand\s|\swhile\s", b)[-1]  # only the clause that holds the name
    last_in = max((m.end() for m in IN_WORDS.finditer(b)), default=-1)
    last_out = max((m.end() for m in OUT_WORDS.finditer(b)), default=-1)
    if last_in >= 0 or last_out >= 0:
        return "in" if last_in > last_out else "out"
    a = after[:140]
    fi, fo = IN_WORDS.search(a), OUT_WORDS.search(a)
    if fi or fo:
        return "in" if fi and (not fo or fi.start() < fo.start()) else "out"
    return "?"


def extract_people(text):
    """[(name, direction, role)] from free text; direction in {'in','out','?'}."""
    people = {}
    for m in NAME.finditer(text):
        name = _clean_name(m.group(1))
        if len(name) < 4 or len(name.split()) < 2:
            continue
        before = text[max(0, m.start() - 160):m.start()]
        after = text[m.start() + len(m.group(0).split(name)[0]) + len(name):][:200]
        d = _direction(before, after)
        rm = ROLE.search(after[:120]) or ROLE.search(before[-80:])
        role = rm.group(1) if rm else None
        key = name.lower()
        if key not in people or (people[key][1] == "?" and d != "?") or (not people[key][2] and role):
            people[key] = (name, d if d != "?" else people.get(key, (0, "?"))[1], role or people.get(key, (0, 0, None))[2])
    return list(people.values())


def _profile_from_text(text, name):
    """Find a 'brief profile' style paragraph that mentions the person."""
    last = name.split()[-1]
    for m in re.finditer(r"(brief )?profile|background|experience|qualification", text, re.I):
        chunk = text[m.start():m.start() + 1400]
        if last.lower() in chunk.lower() or "brief profile" in chunk.lower():
            chunk = re.sub(r"\s+", " ", chunk)
            sents = re.split(r"(?<=[.;])\s+(?=[A-Z])", chunk)
            body = [s for s in sents[1:] if len(s) > 40][:4] or sents[:3]
            if body:
                return " ".join(body)[:900]
    return None


def _wikipedia(name, company):
    try:
        res = fetch_json("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3"
                         f"&srsearch={quote(name)}", ttl=7 * 86400)
    except (FetchError, ValueError):
        return None
    first = company.split()[0].lower()
    for hit in res.get("query", {}).get("search", []):
        if hit["title"].lower() != name.lower():
            continue
        try:
            s = fetch_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(hit['title'].replace(' ', '_'))}",
                           ttl=7 * 86400)
        except (FetchError, ValueError):
            continue
        ext = s.get("extract", "")
        if first in ext.lower() or re.search(r"\b(banker|executive|business|chief|director|officer|industrialist|company)\b", ext, re.I):
            return {"text": ext[:700], "url": s.get("content_urls", {}).get("desktop", {}).get("page")}
    return None


BIO_PROMPT = """From the text below (a stock-exchange filing about {name}), extract a compact career profile.
Return JSON: {{"headline": "one line, e.g. 'ICICI veteran, ran ICICI Securities'", "previous": ["role, org", ...max 4],
"education": "short or null", "years_experience": number or null}}. Use only the text. If the text has no
profile, return {{"headline": null}}.

TEXT:
{text}"""


def enrich(filing, company_name):
    text = f"{filing.get('title','')}. {filing.get('summary','')}"
    pages = pdf.pages(filing["url"], max_pages=12) if filing.get("url", "").lower().split("?")[0].endswith(".pdf") or "AnnPdfOpen" in filing.get("url", "") or "nsearchives" in filing.get("url", "") else []
    full = "\n".join(pages)
    people = extract_people(full or text) or extract_people(text)
    # prefer CXO-level people, incoming first
    rank = lambda p: (p[1] != "in", not (p[2] and re.search(r"chief|managing|ceo|cfo|md|chair", p[2], re.I)))
    people.sort(key=rank)
    directed = [p for p in people if p[1] != "?"]
    people = (directed or [p for p in people if p[2]])[:3]
    out = []
    for name, direction, role in people:
        prof = {"name": name, "direction": direction, "role": (role or "").title().replace("Md", "MD").replace("Ceo", "CEO").replace("Cfo", "CFO"),
                "bio": None, "bio_source": None, "structured": None,
                "linkedin": f"https://www.linkedin.com/search/results/people/?keywords={quote(name + ' ' + company_name.split()[0])}"}
        if direction != "out":
            bio = _profile_from_text(full, name) if full else None
            if bio:
                prof.update(bio=bio, bio_source="filing")
            else:
                ref = re.search(r"(?:already )?(?:been )?provided in the (?:intimation|disclosure|letter) dated ([A-Z][a-z]+ \d{1,2}, \d{4})", full)
                for f in store.filings_since(0, {filing.get("symbol")}):
                    if f["id"] != filing.get("id") and name.split()[-1] in (f.get("summary", "") + f.get("title", "")):
                        prof.update(bio=f.get("summary"), bio_source="earlier filing")
                        break
                if not prof["bio"]:
                    w = _wikipedia(name, company_name)
                    if w:
                        prof.update(bio=w["text"], bio_source="wikipedia", bio_url=w["url"])
                    elif ref:
                        prof["bio_hint"] = f"Profile was filed with the exchange on {ref.group(1)}"
            if prof["bio"] and prof["bio_source"] != "wikipedia":
                js = llm.ask_json(BIO_PROMPT.format(name=name, text=prof["bio"]), tier="cheap", max_tokens=300)
                if isinstance(js, dict) and js.get("headline"):
                    prof["structured"] = js
        out.append(prof)
    return out
