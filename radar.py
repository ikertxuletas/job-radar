"""Daily job radar: collect remote offers from public sources, drop what was already seen, score each new
offer against profile.md with a local LLM (Ollama) and write an HTML report.

  python radar.py            # normal run, remembers what it has seen in seen.json
  python radar.py --test     # few queries, does not touch seen.json
"""
import argparse
import html
import io
import json
import os
import re
import sys
from datetime import datetime

import requests

import config
import sources

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN = os.path.join(HERE, "seen.json")
REPORTS = os.path.join(HERE, "reports")

PROMPT = """You are a career advisor. Score how well the job offer fits the candidate in PROFILE, including every \
preference stated there (location, languages, seniority, remote work). Answer ONLY with JSON:
{{"score": 0-10, "reason": "1-2 sentences", "language_required": "...", "remote": "yes|no|unclear", "level": "junior|mid|senior"}}
Be strict and do not hand out points. 8-10 only when role, level, remote setup and languages all clearly fit; \
5-7 partial fit or open questions; 0-4 a hard conflict with the profile's preferences or a different field. \
If the description is missing, judge by title and location and give at most 7.

PROFILE:
{profile}

OFFER:
Title: {title}
Company: {company}
Location: {location}
Source: {source}
Description: {description}"""


def score(profile, offer):
    description = offer["description"][:1500] or "(no description available)"
    prompt = PROMPT.format(profile=profile, title=offer["title"], company=offer["company"], location=offer["location"],
                           source=offer["source"], description=description)
    try:
        r = requests.post(config.OLLAMA_URL, json={
            "model": config.OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json", "think": False,
            "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 300}}, timeout=300)
        result = json.loads(r.json()["response"])
        result["score"] = int(float(result.get("score", 0)))
        return result
    except Exception as e:
        return {"score": 0, "reason": f"not scored ({e})", "language_required": "?", "remote": "?", "level": "?"}


def enrich(offer):
    """Full description for offers whose source did not include it."""
    if offer.get("desc_type"):
        return sources.lazy_description(offer)
    return sources.page_text(offer["url"])


def table(offers):
    rows = []
    for o in offers:
        ev = o["eval"]
        rows.append(
            f"<tr><td><b>{ev['score']}</b></td>"
            f"<td><a href='{html.escape(o['url'] or '')}'>{html.escape(o['title'])}</a><br><small>{html.escape(o['company'])}"
            f" · {html.escape(o['location'])} · {o['date']} · {o['source']}</small></td>"
            f"<td>{html.escape(str(ev.get('reason', '')))}<br><small>language: {html.escape(str(ev.get('language_required', '')))}"
            f" · remote: {ev.get('remote', '')} · level: {ev.get('level', '')}</small></td></tr>")
    return "<table>" + ("".join(rows) or "<tr><td colspan=3>Nothing.</td></tr>") + "</table>"


def write_report(offers, day, counts):
    os.makedirs(REPORTS, exist_ok=True)
    ranked = sorted(offers, key=lambda o: -o["eval"]["score"])
    top = [o for o in ranked if o["eval"]["score"] >= config.REPORT_MIN_SCORE]
    maybe = [o for o in ranked if config.MAYBE_MIN_SCORE <= o["eval"]["score"] < config.REPORT_MIN_SCORE]
    per_source = " · ".join(f"{k}: {v}" for k, v in counts.items())
    doc = (
        f"<html><head><meta charset='utf-8'><title>Job radar {day}</title>"
        "<style>body{font-family:Segoe UI,Arial;max-width:1100px;margin:24px auto;padding:0 16px}"
        "table{border-collapse:collapse;width:100%}td{border-bottom:1px solid #ddd;padding:8px;vertical-align:top}"
        "td:first-child{font-size:20px;color:#1f7a4d}details{margin-top:24px}summary{cursor:pointer;font-size:17px}"
        "small{color:#555}</style></head><body>"
        f"<h2>Job radar {day}</h2><p>{len(offers)} new offers scored · {len(top)} recommended · {len(maybe)} maybe.</p>"
        f"<p><small>Collected per source (before filtering): {html.escape(per_source)}</small></p>"
        f"<h3>Recommended (&ge; {config.REPORT_MIN_SCORE})</h3>{table(top)}"
        f"<details><summary>Maybe ({config.MAYBE_MIN_SCORE}-{config.REPORT_MIN_SCORE - 1}): {len(maybe)}</summary>{table(maybe)}</details>"
        "</body></html>")
    path = os.path.join(REPORTS, f"offers_{day}.html")
    io.open(path, "w", encoding="utf-8").write(doc)
    io.open(os.path.join(HERE, "latest.html"), "w", encoding="utf-8").write(doc)
    return path, len(top)


def dedupe_key(o):
    return re.sub(r"\W+", "", (o["company"] + o["title"]).lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="few queries, does not update seen.json")
    args = ap.parse_args()
    day = datetime.now().strftime("%Y-%m-%d")

    profile_path = os.path.join(HERE, "profile.md")
    if not os.path.exists(profile_path):
        sys.exit("profile.md not found. Copy profile.example.md to profile.md and describe yourself and your preferences.")
    profile = io.open(profile_path, encoding="utf-8").read()
    seen = json.load(open(SEEN, encoding="utf-8")) if os.path.exists(SEEN) else {}

    collected, counts = sources.collect_all(args.test)
    print("collected per source:", counts)

    fresh, ids, keys = [], set(), set()
    for o in collected:
        if o["id"] in seen or o["id"] in ids or not sources.title_ok(o["title"]) or not sources.location_ok(o):
            continue
        k = dedupe_key(o)
        if k in keys:
            continue
        ids.add(o["id"])
        keys.add(k)
        fresh.append(o)
    print(f"collected {len(collected)} | new with a relevant title: {len(fresh)}")

    for o in fresh:
        if not o["description"] and o.get("desc_type"):
            o["description"] = enrich(o)
        o["eval"] = score(profile, o)
        print(f"  {o['eval']['score']:>2}  {o['source'][:9]:<9} {o['title'][:50]:<50} {o['company'][:22]}")

    borderline = sorted((o for o in fresh if 6 <= o["eval"]["score"] <= 7 and len(o["description"]) < 500),
                        key=lambda o: -o["eval"]["score"])[:config.SECOND_PASS_MAX]
    improved = 0
    for o in borderline:
        text = enrich(o)
        if len(text) > len(o["description"]):
            o["description"] = text
            new = score(profile, o)
            print(f"  second pass {o['eval']['score']} -> {new['score']}  {o['title'][:50]}")
            o["eval"] = new
            improved += 1
    print(f"second pass: {len(borderline)} borderline, {improved} re-scored with the full description")

    if not args.test:
        for o in fresh:
            seen[o["id"]] = {"date": day, "score": o["eval"]["score"], "title": o["title"], "company": o["company"], "url": o["url"]}
        json.dump(seen, open(SEEN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    path, n = write_report(fresh, day, counts)
    print(f"[OK] report: {path} ({n} recommended)")


if __name__ == "__main__":
    main()
