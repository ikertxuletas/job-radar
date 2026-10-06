"""Job sources. Every function returns a list of offers shaped like
{source, id, title, company, location, date (YYYY-MM-DD), url, description, remote}.
One source failing never stops the others: collect_all() logs it and moves on.

Only public APIs and company career boards are used. No logins, no scraping behind a wall."""
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

import config

HEADERS = {"User-Agent": "job-radar/1.0 (personal job-search tool)"}
HERE = os.path.dirname(os.path.abspath(__file__))


def _get(url, **kw):
    kw.setdefault("headers", HEADERS)
    kw.setdefault("timeout", 30)
    r = requests.get(url, **kw)
    r.raise_for_status()
    return r


def _text(s):
    s = html.unescape(s or "")
    s = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _date(x):
    """ISO string, epoch seconds/milliseconds or dd/mm/yyyy -> YYYY-MM-DD ('' if unknown)."""
    if x in (None, ""):
        return ""
    try:
        if isinstance(x, (int, float)) or (isinstance(x, str) and x.isdigit()):
            v = float(x)
            if v > 1e11:
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%d")
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", x)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return x[:10]
    except Exception:
        return ""


def _recent(date, days=config.DAYS):
    if not date:
        return True
    try:
        return datetime.fromisoformat(date) >= datetime.now() - timedelta(days=days)
    except Exception:
        return True


def _offer(source, id_, title, company, location, date, url, description="", remote=False, **extra):
    d = {"source": source, "id": id_, "title": (title or "").strip(), "company": (company or "").strip(),
         "location": (location or "").strip(), "date": date, "url": url, "description": description, "remote": remote}
    d.update(extra)
    return d


def title_ok(title):
    return bool(config.TITLE_INCLUDE.search(title)) and not config.TITLE_EXCLUDE.search(title)


def location_ok(offer):
    loc = offer.get("location", "")
    return not (config.EXCLUDE_LOCATION.search(loc) and not config.EXCLUDE_EXCEPTION.search(loc))


def _remote_region_ok(location, remote):
    """Remote offers pass when they name no region or a region matching config.REGION_OK."""
    if not remote:
        return False
    return location.strip().lower() in ("", "remote", "home office", "homeoffice") or bool(config.REGION_OK.search(location))


# ---------------------------------------------------------------- remote job feeds
def remotive(test=False):
    out = []
    for q in config.QUERIES[:1] if test else config.QUERIES:
        for j in _get("https://remotive.com/api/remote-jobs", params={"search": q, "limit": 50}).json().get("jobs", []):
            loc = j.get("candidate_required_location", "")
            if _recent(j.get("publication_date", "")[:10]) and config.REGION_OK.search(loc or "worldwide"):
                out.append(_offer("remotive", "rm:" + str(j["id"]), j["title"], j.get("company_name"), "Remote - " + loc,
                                  j.get("publication_date", "")[:10], j["url"], _text(j.get("description", ""))[:3000], True))
    return out


def arbeitnow(test=False):
    out = []
    for page in range(1, 2 if test else 5):
        for j in _get("https://www.arbeitnow.com/api/job-board-api", params={"page": page}).json().get("data", []):
            date = _date(j.get("created_at"))
            remote = bool(j.get("remote")) or bool(config.REMOTE_WORDS.search(j.get("location", "") + " " + j["title"]))
            if _recent(date) and remote:
                out.append(_offer("arbeitnow", "an:" + j["slug"], j["title"], j.get("company_name"),
                                  j.get("location", "") + " (remote)", date, j["url"], _text(j.get("description", ""))[:3000], True))
    return out


def remoteok(test=False):
    out = []
    for j in _get("https://remoteok.com/api").json()[1:]:
        loc = j.get("location", "")
        date = _date(j.get("date"))
        if _recent(date) and (not loc or config.REGION_OK.search(loc)):
            out.append(_offer("remoteok", "ro:" + str(j["id"]), j.get("position"), j.get("company"), "Remote " + loc, date,
                              j.get("url") or j.get("apply_url"), _text(j.get("description", ""))[:3000], True))
    return out


def himalayas(test=False):
    out, cursor = [], None
    for _ in range(3 if test else 25):
        params = {"limit": 20}
        if cursor:
            params["cursor"] = cursor
        d = _get("https://himalayas.app/jobs/api", params=params).json()
        old = 0
        for j in d.get("jobs", []):
            date = _date(j.get("pubDate"))
            if not _recent(date):
                old += 1
                continue
            restrictions = j.get("locationRestrictions") or []
            loc = ", ".join(restrictions)
            if restrictions and not config.REGION_OK.search(loc):
                continue
            out.append(_offer("himalayas", "hm:" + (j.get("guid") or j["title"]), j["title"], j.get("companyName"),
                              "Remote " + (loc or "worldwide"), date, j.get("applicationLink") or j.get("guid"),
                              _text(j.get("description", ""))[:3000], True))
        cursor = d.get("nextCursor")
        if not cursor or old >= 15:
            break
        time.sleep(0.5)
    return out


def jobicy(test=False):
    out, seen = [], set()
    queries = [("europe", "accounting-finance"), ("europe", "data-science"), ("europe", "business"), ("europe", "management"),
               ("germany", ""), ("netherlands", ""), ("switzerland", ""), ("ireland", ""), ("denmark", ""), ("sweden", "")]
    for geo, industry in queries[:1] if test else queries:
        params = {"count": 50, "geo": geo}
        if industry:
            params["industry"] = industry
        for j in _get("https://jobicy.com/api/v2/remote-jobs", params=params).json().get("jobs", []):
            if j["id"] in seen:
                continue
            seen.add(j["id"])
            date = _date(j.get("pubDate"))
            if _recent(date):
                out.append(_offer("jobicy", "jb:" + str(j["id"]), j.get("jobTitle"), j.get("companyName"),
                                  "Remote - " + str(j.get("jobGeo", "")), date, j["url"],
                                  _text(j.get("jobDescription") or j.get("jobExcerpt", ""))[:3000], True))
        time.sleep(1)
    return out


def workingnomads(test=False):
    out = []
    for j in _get("https://www.workingnomads.com/api/exposed_jobs/").json():
        loc = j.get("location", "")
        date = _date(j.get("pub_date"))
        if _recent(date) and config.REGION_OK.search(loc or "anywhere"):
            out.append(_offer("workingnomads", "wn:" + j["url"], j["title"], j.get("company_name"), "Remote - " + loc, date,
                              j["url"], _text(j.get("description", ""))[:3000], True))
    return out


# ---------------------------------------------------------------- national open APIs
def jobtech_se(test=False):
    """Sweden: Arbetsformedlingen open API, remote offers only."""
    out, seen = [], set()
    since = (datetime.now() - timedelta(days=config.DAYS)).strftime("%Y-%m-%dT00:00:00")
    for q in config.QUERIES[:1] if test else config.QUERIES:
        d = _get("https://jobsearch.api.jobtechdev.se/search",
                 params={"q": q, "remote": "true", "limit": 50, "published-after": since}).json()
        for h in d.get("hits", []):
            if h["id"] in seen:
                continue
            seen.add(h["id"])
            city = (h.get("workplace_address") or {}).get("municipality") or ""
            out.append(_offer("jobtech_se", "se:" + h["id"], h.get("headline"), (h.get("employer") or {}).get("name"),
                              f"{city} Sweden (remote)".strip(), _date(h.get("publication_date")), h.get("webpage_url"),
                              _text((h.get("description") or {}).get("text", ""))[:3000], True))
        time.sleep(0.5)
    return out


def nav_no(test=False):
    """Norway: NAV open API, ads whose working language is English and that mention remote work.
    The API rate-limits quickly; on HTTP 429 we return what we have."""
    out, seen = [], set()
    for q in config.QUERIES[:1] if test else config.QUERIES:
        for extra in ("remote", "hjemmekontor"):
            try:
                d = _get("https://arbeidsplassen.nav.no/stillinger/api/search", params={"q": f"{q} {extra}"}).json()
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    return out
                continue
            time.sleep(4)
            for hit in d.get("hits", {}).get("hits", []):
                s = hit["_source"]
                props = s.get("properties") or {}
                if s["uuid"] in seen or "Engelsk" not in str(props.get("workLanguage", "")):
                    continue
                seen.add(s["uuid"])
                date = _date(s.get("published"))
                if not _recent(date):
                    continue
                city = ((s.get("locationList") or [{}])[0]).get("city", "")
                out.append(_offer("nav_no", "no:" + s["uuid"], s.get("title"), s.get("businessName"),
                                  f"{city} Norway (remote?)".strip(), date,
                                  "https://arbeidsplassen.nav.no/stillinger/stilling/" + s["uuid"],
                                  " | ".join(str(x) for x in (props.get("jobtitle"), props.get("keywords"), props.get("education"))), True))
    return out


def adzuna(test=False):
    """Aggregator. Optional: set ADZUNA_APP_ID and ADZUNA_APP_KEY (free at developer.adzuna.com)."""
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    out, seen = [], set()
    for country in config.ADZUNA_COUNTRIES[:1] if test else config.ADZUNA_COUNTRIES:
        for q in config.QUERIES[:1] if test else config.QUERIES:
            try:
                d = _get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params={
                    "app_id": app_id, "app_key": app_key, "what": q + " remote", "max_days_old": config.DAYS,
                    "results_per_page": 50, "sort_by": "date", "content-type": "application/json"}).json()
            except Exception:
                continue
            for j in d.get("results", []):
                text = j.get("title", "") + " " + j.get("description", "")
                if j["id"] in seen or not config.REMOTE_WORDS.search(text):
                    continue
                seen.add(j["id"])
                out.append(_offer("adzuna", "az:" + str(j["id"]), j.get("title"), (j.get("company") or {}).get("display_name"),
                                  ((j.get("location") or {}).get("display_name") or "") + " (remote)", _date(j.get("created")),
                                  j.get("redirect_url"), _text(j.get("description", ""))[:1500], True))
            time.sleep(0.5)
    return out


# ---------------------------------------------------------------- company career boards (ATS public APIs)
def _greenhouse(slug):
    for j in _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs").json().get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        yield _offer("greenhouse", f"gh:{slug}:{j['id']}", j["title"], j.get("company_name") or slug, loc,
                     _date(j.get("first_published") or j.get("updated_at")), j["absolute_url"], "",
                     bool(config.REMOTE_WORDS.search(loc + " " + j["title"])),
                     desc_url=f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{j['id']}", desc_type="gh")


def _lever(slug):
    for j in _get(f"https://api.lever.co/v0/postings/{slug}?mode=json").json():
        cat = j.get("categories") or {}
        loc = " / ".join([cat.get("location", "")] + (cat.get("allLocations") or []))
        remote = (j.get("workplaceType") or "").lower() == "remote" or bool(config.REMOTE_WORDS.search(loc + " " + j["text"]))
        yield _offer("lever", f"lv:{slug}:{j['id']}", j["text"], slug, loc, _date(j.get("createdAt")), j["hostedUrl"],
                     (j.get("descriptionPlain") or "")[:3000], remote)


def _ashby(slug):
    for j in _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}").json().get("jobs", []):
        if not j.get("isListed", True):
            continue
        secondary = " / ".join(s.get("location", "") for s in (j.get("secondaryLocations") or []))
        loc = " / ".join(x for x in (j.get("location", ""), secondary) if x)
        remote = bool(j.get("isRemote")) or (j.get("workplaceType") or "").lower() == "remote"
        yield _offer("ashby", f"as:{slug}:{j['id']}", j["title"], slug, loc, _date(j.get("publishedAt")), j["jobUrl"],
                     (j.get("descriptionPlain") or "")[:3000], remote)


def _recruitee(slug):
    for j in _get(f"https://{slug}.recruitee.com/api/offers/").json().get("offers", []):
        yield _offer("recruitee", f"rc:{slug}:{j['id']}", j["title"], j.get("company_name") or slug, j.get("location", ""),
                     _date(j.get("published_at")), j.get("careers_url"), _text(j.get("description", ""))[:3000], bool(j.get("remote")))


def _smartrecruiters(slug):
    d = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 100}).json()
    for j in d.get("content", []):
        loc = j.get("location") or {}
        in_region = (loc.get("country") or "").lower() in config.EU_COUNTRY_CODES
        yield _offer("smartrecruiters", f"sr:{slug}:{j['id']}", j["name"], (j.get("company") or {}).get("name", slug),
                     f"{loc.get('city', '')}, {loc.get('country', '')}" + (" (remote)" if loc.get("remote") else ""),
                     _date(j.get("releasedDate")), f"https://jobs.smartrecruiters.com/{slug}/{j['id']}", "",
                     bool(loc.get("remote")) and in_region, desc_url=j.get("ref"), desc_type="sr",
                     force_region=bool(loc.get("remote")) and in_region)


def _personio(slug):
    root = ET.fromstring(_get(f"https://{slug}.jobs.personio.de/xml").content)
    for p in root.findall("position"):
        name, office = p.findtext("name") or "", p.findtext("office") or ""
        desc = _text(" ".join((jd.findtext("value") or "") for jd in p.findall(".//jobDescription")))[:3000]
        yield _offer("personio", f"pe:{slug}:{p.findtext('id')}", name, slug, office, _date(p.findtext("createdAt")),
                     f"https://{slug}.jobs.personio.de/job/{p.findtext('id')}", desc,
                     bool(config.REMOTE_WORDS.search(name + " " + office)))


_ATS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby, "recruitee": _recruitee,
        "smartrecruiters": _smartrecruiters, "personio": _personio}


def company_boards(test=False):
    """Open offers of every company in boards.json (see discover_boards.py), filtered by date and region."""
    path = os.environ.get("JOB_RADAR_BOARDS", os.path.join(HERE, "boards.json"))
    if not os.path.exists(path):
        return []
    boards = json.load(open(path, encoding="utf-8"))
    tasks = [(p, s) for p, slugs in boards.items() for s in slugs]
    if test:
        tasks = tasks[:6]

    def one(task):
        platform, slug = task
        try:
            return list(_ATS[platform](slug))
        except Exception as e:
            print(f"  [{platform}:{slug}] failed: {str(e)[:80]}")
            return []

    with ThreadPoolExecutor(max_workers=8) as ex:
        batches = list(ex.map(one, tasks))
    out = []
    for batch in batches:
        for o in batch:
            if _recent(o["date"], config.DAYS_BOARDS) and (o.pop("force_region", False) or _remote_region_ok(o["location"], o["remote"])):
                out.append(o)
    return out


# ---------------------------------------------------------------- descriptions
def lazy_description(o):
    """Fetch the description of offers whose board only returns it in a second call."""
    try:
        if o.get("desc_type") == "gh":
            return _text(_get(o["desc_url"]).json().get("content", ""))[:3000]
        if o.get("desc_type") == "sr":
            sections = _get(o["desc_url"]).json().get("jobAd", {}).get("sections", {})
            return _text(" ".join(v.get("text", "") for v in sections.values()))[:3000]
    except Exception:
        pass
    return ""


def page_text(url):
    """Description scraped from the offer's own page (JSON-LD JobPosting if present, else main text)."""
    try:
        h = _get(url, timeout=25).text
        for block in re.findall(r'(?s)<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h):
            try:
                data = json.loads(block)
            except Exception:
                continue
            for d in (data if isinstance(data, list) else [data]):
                if isinstance(d, dict) and d.get("@type") == "JobPosting" and d.get("description"):
                    return _text(d["description"])[:3000]
        body = re.search(r"(?s)<(?:main|article)[^>]*>(.*?)</(?:main|article)>", h)
        return _text(body.group(1) if body else h)[:3000]
    except Exception:
        return ""


SOURCES = [("remotive", remotive), ("arbeitnow", arbeitnow), ("remoteok", remoteok), ("himalayas", himalayas),
           ("jobicy", jobicy), ("workingnomads", workingnomads), ("jobtech_se", jobtech_se), ("nav_no", nav_no),
           ("adzuna", adzuna), ("company_boards", company_boards)]


def collect_all(test=False):
    """Returns (offers, per_source_counts). A broken source does not take the others down."""
    offers, counts = [], {}
    for name, fn in SOURCES:
        try:
            batch = fn(test)
            counts[name] = len(batch)
            offers.extend(batch)
        except Exception as e:
            counts[name] = f"ERROR {str(e)[:60]}"
            print(f"  [{name}] failed: {e}")
    return offers, counts
