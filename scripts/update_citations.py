#!/usr/bin/env python3
"""Refresh data/citations.json from Google Scholar.

Two sources, in order of reliability:
  1. SerpApi (https://serpapi.com) — used if env SERPAPI_API_KEY is set.
     Reliable; free tier (~100 searches/mo) is plenty for a weekly run.
  2. `scholarly` — free, no key, but Google Scholar often blocks CI runners,
     so it may fail. That's fine: we fail soft and keep the last-known-good file.

Run in CI (see .github/workflows/update-citations.yml). On ANY error the existing
data/citations.json is left untouched, so the website keeps showing 570 etc.
"""
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

SCHOLAR_ID = "n_TR1LcAAAAJ"  # Beomyoung Kim on Google Scholar
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "citations.json")

# arXiv id  ->  lowercase keyword that uniquely identifies the paper's GS title
PAPER_MATCH = [
    ("2411.00626", "zero-shot image matting"),
    ("2404.00921", "label-efficient human matting"),
    ("2404.00918", "saliency-guided weakly"),
    ("2403.20126", "continual learning in panoptic"),
    ("2204.01209", "lightweight face detection"),
    ("2303.15062", "devil is in the points"),
    ("2109.09477", "beyond semantic to instance"),
    ("2202.02777", "parameter-free layers"),
    ("2104.11435", "tricubenet"),
    ("2106.11562", "semantic segmentation with unknown label"),
    ("2103.07246", "discriminative region suppression"),
]


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "beomyoung-kim.github.io citation updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def from_serpapi(key):
    """Return (total, hindex, i10, rows[(title, cites)]) from SerpApi."""
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(
        {"engine": "google_scholar_author", "author_id": SCHOLAR_ID, "num": 100, "api_key": key}
    )
    d = _get_json(url)
    table = {list(x)[0]: x[list(x)[0]] for x in d.get("cited_by", {}).get("table", [])}
    total = table.get("citations", {}).get("all")
    hindex = table.get("h_index", {}).get("all")
    i10 = table.get("i10_index", {}).get("all")
    rows = [(a.get("title", ""), (a.get("cited_by") or {}).get("value") or 0)
            for a in d.get("articles", [])]
    return total, hindex, i10, rows


def from_scholarly():
    """Return (total, hindex, i10, rows[(title, cites)]) via the scholarly scraper."""
    from scholarly import scholarly  # imported lazily so SerpApi path needs no dep
    a = scholarly.fill(scholarly.search_author_id(SCHOLAR_ID),
                       sections=["basics", "indices", "publications"])
    rows = [(p.get("bib", {}).get("title", ""), p.get("num_citations", 0) or 0)
            for p in a.get("publications", [])]
    return a.get("citedby"), a.get("hindex"), a.get("i10index"), rows


def map_papers(rows):
    papers = {}
    for title, cites in rows:
        t = (title or "").lower()
        for arxiv, kw in PAPER_MATCH:
            if kw in t:
                papers[arxiv] = max(papers.get(arxiv, 0), int(cites or 0))
                break
    return papers


def main():
    key = os.environ.get("SERPAPI_API_KEY")
    if key:
        print("Source: SerpApi (Google Scholar)")
        total, hindex, i10, rows = from_serpapi(key)
    else:
        print("Source: scholarly (Google Scholar) — no SERPAPI_API_KEY set")
        total, hindex, i10, rows = from_scholarly()

    if not total:
        raise RuntimeError("no total citation count returned")

    out = {
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%d"),
        "source": "Google Scholar",
        "total": int(total),
        "hindex": int(hindex) if hindex is not None else None,
        "i10": int(i10) if i10 is not None else None,
        "papers": map_papers(rows),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("Wrote %s  total=%s hindex=%s i10=%s papers=%d"
          % (OUT, out["total"], out["hindex"], out["i10"], len(out["papers"])))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never fail the workflow; keep last-known-good file
        print("update_citations failed (keeping existing file):", e, file=sys.stderr)
        sys.exit(0)
