"""Batch refresh: all sources, then every dossier.  python -m finn.refresh"""
import time

from . import ingest
from .config import PORTFOLIO_SYMBOLS, RESEARCH_DEMO
from .pull import research


def main():
    ingest.refresh_all(force=True)
    for s in RESEARCH_DEMO + PORTFOLIO_SYMBOLS:
        research.start(s, force=True)
        while (research.get(s) or {}).get("status") == "running":
            time.sleep(1)
        print(s, research.get(s).get("status"), flush=True)


if __name__ == "__main__":
    main()
