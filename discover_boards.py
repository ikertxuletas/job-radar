"""Checks which company slugs have a public job board on each applicant-tracking system and stores the
valid ones in boards.json, which sources.company_boards() then reads.

  python discover_boards.py                 # test the built-in COMPANIES list and rewrite boards.json
  python discover_boards.py acme globex     # test only these slugs and add the valid ones to boards.json
"""
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "boards.json")
HEADERS = {"User-Agent": "job-radar/1.0 (personal job-search tool)"}

COMPANIES = """
n26 traderepublic scalablecapital taxfix getmoss moss pleo qonto mollie adyen gocardless sumup billie forto
celonis personio deepl contentful auto1 getyourguide hellofresh zalando deliveryhero trivago soundcloud babbel wefox
raisin lendable upvest solarisbank solaris bunq tide wise monzo vivid vividmoney penta finom payhawk pennylane agicap
alan spendesk libeo stripe datadog elastic gitlab hashicorp canonical mongodb snowflake databricks doctolib mambu
fonoa taxdoo pitch bitpanda kraken coinbase ledger nuri checkout rapyd airwallex remote deel oyster papaya lano
factorial holded billin jobandtalent glovo cabify typeform travelperk sennder flix helsing zapier n8n make airtable
notion linear retool postman miro lokalise vercel supabase posthog mistral voiceflow preqin moonfare carta
dealroom sifted tracxn ebury payoneer flywire lemonway capmo enpal 1komma5 planetly tado choco everphone adahealth kry
revolut klarna paysafe nium thunes clark friday getsafe luko ottonova nextmarkets bux smartbroker ginmon
growney finanzguru vaamo knip moneyfarm scalapay satispay nexi worldline mangopay swan shine
qover alpian yapily truelayer plaid tink fintecture stitch moneyhub openpayd cobee clip
tourlane omio holidu wunderflats quandoo lieferando rocket-internet
unzer payone concardis ratepay hometogo tier bolt voi lime
blackrock pimco dws amundi robeco schroders fidelity
mckinsey bcg bain oliverwyman rolandberger simon-kucher
stepstone datev lexware sage xero freshworks hubspot salesforce zendesk intercom
algolia contentstack storyblok commercetools shopify bigcommerce spryker
""".split()

PLATFORMS = {
    "greenhouse": lambda s: f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
    "lever": lambda s: f"https://api.lever.co/v0/postings/{s}?mode=json&limit=1",
    "ashby": lambda s: f"https://api.ashbyhq.com/posting-api/job-board/{s}",
    "recruitee": lambda s: f"https://{s}.recruitee.com/api/offers/",
    "personio": lambda s: f"https://{s}.jobs.personio.de/xml",
    "smartrecruiters": lambda s: f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=1",
}


def has_board(platform, slug):
    try:
        r = requests.get(PLATFORMS[platform](slug), headers=HEADERS, timeout=15)
    except Exception:
        return False
    if r.status_code != 200:
        return False
    try:
        if platform in ("greenhouse", "ashby"):
            return len(r.json().get("jobs", [])) > 0
        if platform == "lever":
            return isinstance(r.json(), list) and len(r.json()) > 0
        if platform == "recruitee":
            return len(r.json().get("offers", [])) > 0
        if platform == "personio":
            return "<position>" in r.text
        if platform == "smartrecruiters":
            return r.json().get("totalFound", 0) > 0
    except Exception:
        return False
    return False


def main():
    extra = sys.argv[1:]
    slugs = sorted(set(s.lower() for s in (extra or COMPANIES)))
    boards = json.load(open(OUTPUT, encoding="utf-8")) if (extra and os.path.exists(OUTPUT)) else {p: [] for p in PLATFORMS}
    tasks = [(p, s) for p in PLATFORMS for s in slugs]
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(lambda t: (t, has_board(*t)), tasks))
    for (platform, slug), ok in results:
        if ok and slug not in boards.setdefault(platform, []):
            boards[platform].append(slug)
    for platform in boards:
        boards[platform] = sorted(boards[platform])
    io.open(OUTPUT, "w", encoding="utf-8").write(json.dumps(boards, indent=1, ensure_ascii=False))
    for platform, found in boards.items():
        print(f"{platform:16}{len(found):>3}  {', '.join(found)}")
    print("companies with a board:", sum(len(v) for v in boards.values()))


if __name__ == "__main__":
    main()
