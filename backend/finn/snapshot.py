"""Export / import a seed snapshot so a fresh deploy works even if a data source is down
or blocks the host's IP.  python -m finn.snapshot export|import"""
import gzip
import json
import sys

from . import store
from .config import SEED_DIR

NAMESPACES = ["company", "eod", "guidance", "research", "results_card", "people", "pdftext", "nse", "llm"]


def export():
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    with store._lock:
        kv = store._conn.execute(f"SELECT ns, k, v, ts FROM kv WHERE ns IN ({','.join('?' * len(NAMESPACES))})",
                                 NAMESPACES).fetchall()
        filings = store._conn.execute("SELECT * FROM filings").fetchall()
    data = {"kv": kv, "filings": filings}
    path = SEED_DIR / "seed.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB, {len(kv)} kv, {len(filings)} filings)")


def load(only_if_empty=True):
    path = SEED_DIR / "seed.json.gz"
    if not path.exists():
        return False
    with store._lock:
        n = store._conn.execute("SELECT COUNT(*) FROM kv WHERE ns='company'").fetchone()[0]
    if only_if_empty and n:
        return False
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    with store._lock:
        store._conn.executemany("INSERT OR IGNORE INTO kv VALUES (?,?,?,?)", data["kv"])
        store._conn.executemany(f"INSERT OR IGNORE INTO filings VALUES ({','.join('?' * len(store.FILING_COLS))})", data["filings"])
        store._conn.commit()
    return True


if __name__ == "__main__":
    {"export": export, "import": lambda: print("loaded" if load(only_if_empty=False) else "no seed")}[sys.argv[1]]()
