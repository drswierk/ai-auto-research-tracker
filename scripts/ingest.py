#!/usr/bin/env python3
"""
Pull recent arXiv papers per research-lifecycle stage and append new candidates
to data.json. Dedupes by link and (lowercased) title. Stdlib only — no pip installs.

Run locally:   python scripts/ingest.py
In CI:         called by .github/workflows/update-tracker.yml, which opens a PR
               so a human approves every new entry before it goes live.
"""
import json, re, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data.json"
API = "http://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
MAX_PER_STAGE = 15  # how many recent hits to consider per stage

# One search query per stage. Tune the terms to taste.
QUERIES = {
    "S1":  '("research idea generation" OR "hypothesis generation") AND "large language model"',
    "S2":  '("literature review" OR "deep research agent" OR "survey generation") AND LLM',
    "S3":  '("automated experiment" OR "research code" OR "reproducibility") AND (agent OR LLM)',
    "S5":  '("scientific paper writing" OR "manuscript generation") AND LLM',
    "S6":  '("automated peer review" OR "LLM reviewer") AND (benchmark OR evaluation)',
    "S7":  '("rebuttal generation" OR "author response") AND LLM',
    "S8":  '("paper to poster" OR "paper to slides" OR "research dissemination") AND LLM',
    "E2E": '("AI scientist" OR "autonomous research" OR "research agent") AND "end-to-end"',
}

def norm_title(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", t.lower())).strip()

def fetch(stage, query):
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "sortBy": "submittedDate", "sortOrder": "descending",
        "max_results": MAX_PER_STAGE,
    })
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": "auto-research-tracker"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.findall(f"{ATOM}entry"):
        title = (e.findtext(f"{ATOM}title") or "").strip()
        link = (e.findtext(f"{ATOM}id") or "").strip()
        summary = re.sub(r"\s+", " ", (e.findtext(f"{ATOM}summary") or "").strip())
        published = (e.findtext(f"{ATOM}published") or "")[:10]
        year = int(published[:4]) if published[:4].isdigit() else 0
        out.append({
            "method": title, "stage": stage, "category": "(unclassified)",
            "venue": "arXiv", "year": year, "link": link, "github": False,
            "eval": (summary[:140] + "…") if len(summary) > 140 else summary,
        })
    return out

def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    seen_links = {d.get("link") for d in data}
    seen_titles = {norm_title(d.get("method", "")) for d in data}

    added = 0
    for stage, q in QUERIES.items():
        try:
            for c in fetch(stage, q):
                if c["link"] in seen_links or norm_title(c["method"]) in seen_titles:
                    continue
                data.append(c); seen_links.add(c["link"]); seen_titles.add(norm_title(c["method"]))
                added += 1
                print(f"+ [{stage}] {c['method']}")
        except Exception as ex:
            print(f"! {stage} query failed: {ex}", file=sys.stderr)
        time.sleep(3)  # be polite to the arXiv API

    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nDone. Added {added} new candidate(s). Total: {len(data)}.")
    print("New rows have category='(unclassified)' — review and edit before merging.")

if __name__ == "__main__":
    main()
