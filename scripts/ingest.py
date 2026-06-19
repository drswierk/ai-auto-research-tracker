#!/usr/bin/env python3
"""
Pull recent arXiv papers per research-lifecycle stage and append new candidates
to data.json. Dedupes by link and (lowercased) title. Stdlib only — no pip installs.

Tuned to stay quiet: few results per stage, recent papers only, and a title-keyword
filter to cut off-topic noise. Every new entry still goes through a PR for human review.
"""
import json, re, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data.json"
API = "http://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"

MAX_PER_STAGE = 6     # how many recent hits to consider per stage (was 15)
DAYS_BACK = 30        # only keep papers submitted within this many days
CATS = "(cat:cs.CL OR cat:cs.AI OR cat:cs.LG OR cat:cs.DL OR cat:cs.IR OR cat:stat.ML)"

# One search query per stage + keywords that MUST appear in the title.
# A candidate is dropped if its title contains none of the stage keywords.
STAGES = {
    "S1":  ('(ti:"research idea generation" OR ti:"hypothesis generation" OR abs:"scientific hypothesis generation")',
            ["idea generation", "hypothesis generation", "ideation"]),
    "S2":  ('(ti:"literature review" OR ti:"deep research" OR ti:"survey generation")',
            ["literature review", "deep research", "survey generation", "related work"]),
    "S3":  ('(ti:"research code" OR ti:"experiment" OR ti:"reproducibility") AND abs:agent',
            ["reproducibility", "research code", "experiment", "replication"]),
    "S5":  ('(ti:"paper writing" OR ti:"manuscript generation" OR ti:"scientific writing")',
            ["paper writing", "manuscript", "scientific writing"]),
    "S6":  ('(ti:"peer review" OR ti:"automated review" OR ti:"LLM reviewer")',
            ["peer review", "reviewer", "review generation"]),
    "S7":  ('(ti:rebuttal OR ti:"author response")',
            ["rebuttal", "author response"]),
    "S8":  ('(ti:"paper to poster" OR ti:"paper to slides" OR ti:"research dissemination")',
            ["poster", "slides", "dissemination"]),
    "E2E": ('(ti:"AI scientist" OR ti:"autonomous research" OR ti:"research agent")',
            ["ai scientist", "autonomous research", "research agent", "end-to-end"]),
}

def norm_title(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", t.lower())).strip()

def recent_enough(published):
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        return dt >= datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    except Exception:
        return False

def fetch(stage, query, keywords):
    params = urllib.parse.urlencode({
        "search_query": f"({query}) AND {CATS}",
        "sortBy": "submittedDate", "sortOrder": "descending",
        "max_results": MAX_PER_STAGE,
    })
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": "auto-research-tracker"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.findall(f"{ATOM}entry"):
        title = (e.findtext(f"{ATOM}title") or "").strip()
        published = (e.findtext(f"{ATOM}published") or "")
        if not recent_enough(published):
            continue
        tl = title.lower()
        if not any(k in tl for k in keywords):   # title-keyword filter (cuts noise)
            continue
        link = (e.findtext(f"{ATOM}id") or "").strip()
        summary = re.sub(r"\s+", " ", (e.findtext(f"{ATOM}summary") or "").strip())
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
    for stage, (query, keywords) in STAGES.items():
        try:
            for c in fetch(stage, query, keywords):
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
