# job-radar

A small tool that finds remote job offers every day, ignores what it already showed me, and uses a **local LLM**
to score each new offer against my own profile. The output is one HTML page with the offers worth reading.

I built it for my own job search, with [Claude Code](https://claude.com/claude-code) writing most of the code and me
deciding what it should do, checking the output and fixing what broke. Nothing leaves my machine except the requests
to the public job APIs; the scoring runs on [Ollama](https://ollama.com).

## What it does

1. **Collects** offers from public sources: remote job feeds (Remotive, Arbeitnow, RemoteOK, Himalayas, Jobicy,
   Working Nomads), the Swedish and Norwegian public employment APIs, optionally Adzuna, and the career boards of
   ~120 companies on Greenhouse, Lever, Ashby, Recruitee, Personio and SmartRecruiters.
2. **Filters** by date, by region of the remote offer and by title (all patterns live in `config.py`).
3. **Deduplicates** against everything seen before (`seen.json`) and across sources.
4. **Scores** each remaining offer from 0 to 10 with a local model, using `profile.md` (who I am and what I want).
   Offers scored 6-7 without a full description get a second pass after fetching the offer page.
5. **Reports**: `latest.html` with the recommended offers and a collapsed list of "maybe" ones, with the reason for each score.

A first run collects about 450 offers; roughly 40 survive the title filter and get scored (a few seconds each).
After that, each daily run only scores what appeared since the day before.

## Run it

```bash
pip install -r requirements.txt
ollama pull qwen3.5:9b                 # or any model; set OLLAMA_MODEL
cp profile.example.md profile.md       # then describe yourself and your preferences
python radar.py --test                 # quick check, touches nothing
python radar.py                        # real run, open latest.html afterwards
```

Run it daily with Windows Task Scheduler or cron. `python discover_boards.py <slug> ...` adds company boards.

## Design choices

- **Only public APIs and career boards.** No logins, no scraping behind a wall. Sources that block automated access
  (Indeed, Glassdoor, LinkedIn's apply flow, InfoJobs...) are deliberately not in here.
- **One broken source never stops a run.** Every source is wrapped, and the report shows how many offers each returned.
- **The preferences are text, not code.** Language requirements, seniority, location and deal-breakers go in
  `profile.md` and the model applies them, so changing job-hunt goals does not mean editing the pipeline.
- **A small model is enough** when the prompt is strict and the output is forced to JSON. Thinking mode is switched
  off and the answer is capped at 300 tokens, which keeps scoring at a few seconds per offer on a consumer GPU.

## Limitations

- Titles are filtered before scoring, so an unusual title for a good role can be missed. Widen `TITLE_INCLUDE`.
- Many boards give no description in the listing, so those offers are first scored on title and location only
  (capped at 7) and rescored in the second pass if they land at 6-7.
- "Remote" is what the offer says. Residence or work-permit conditions only show up if the model finds them in the text.
- The Norwegian API rate-limits hard, so that source is best-effort.
