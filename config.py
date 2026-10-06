"""Everything you are likely to tune lives here. The defaults target junior finance / data /
automation roles in Europe; change the patterns and the profile to point it at something else."""
import os
import re

DAYS = 7           # ignore offers older than this
DAYS_BOARDS = 21   # company career boards are updated less often, so look further back

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")

REPORT_MIN_SCORE = 7     # offers at or above this go to the "recommended" table
MAYBE_MIN_SCORE = 5      # offers in [MAYBE_MIN_SCORE, REPORT_MIN_SCORE) go to the collapsed "maybe" table
SECOND_PASS_MAX = 60     # borderline offers re-scored after fetching their full description

# Search terms for the sources that need a query
QUERIES = ["financial analyst", "fp&a", "controller", "business analyst", "data analyst", "automation",
           "operations analyst", "revenue operations", "investment analyst"]

# A title must match TITLE_INCLUDE and must not match TITLE_EXCLUDE to be scored at all
TITLE_INCLUDE = re.compile(
    r"financ|fp&a|fpa\b|controll|accounting|treasury|audit|risk|credit|invest|private equity|venture|"
    r"m&a|corporate development|valuation|analyst|analytik|reporting|business intelligence|\bbi\b|data|"
    r"daten|automat|revops|revenue operations|sales operations|business operations|operations|process|"
    r"n8n|\bai\b|\bki\b|prompt|werkstudent|working student|intern\b|internship|trainee|graduate|"
    r"junior|strategy|consult|compliance|kyc|aml|tax|payroll|procurement|knowledge|chatbot|bot\b|"
    r"workflow|no-?code|low-?code|rpa|enablement|biz ?ops", re.I)
TITLE_EXCLUDE = re.compile(
    r"senior|\bsr\.?\b|lead\b|head of|director|manager|principal|staff|architect|vp\b|vice president|chief|"
    r"software engineer|developer|entwickler|devops|front-?end|back-?end|full[- ]?stack|\bsre\b|"
    r"machine learning engineer|ml engineer|data engineer|data scientist|designer|recruiter|talent|"
    r"sales development|account executive|customer success|support agent|nurse|driver|physician|teacher|"
    r"counsel|attorney|lawyer|clinical|sales representative|business development representative", re.I)

# Remote offers restricted to a region only pass if the region text matches this
REGION_OK = re.compile(
    r"europe|\beu\b|emea|european|germany|deutschland|berlin|munich|hamburg|frankfurt|cologne|austria|vienna|"
    r"switzerland|zurich|netherlands|amsterdam|ireland|dublin|sweden|stockholm|denmark|copenhagen|norway|oslo|"
    r"finland|helsinki|belgium|brussels|luxembourg|worldwide|anywhere|global|\bcet\b", re.I)

# Locations to drop even if the offer is remote (leave the default to keep everything).
# Example for a candidate who does not want roles based in France: re.compile(r"france|paris|lyon", re.I)
EXCLUDE_LOCATION = re.compile(r"(?!x)x")
# ...unless the offer is open to a wider region than the excluded one
EXCLUDE_EXCEPTION = re.compile(r"europe|emea|worldwide|anywhere|\beu\b|european", re.I)

REMOTE_WORDS = re.compile(r"remote|home ?office|work from home|distributed|anywhere|telework", re.I)

# ISO country codes accepted for the remote offers of SmartRecruiters boards
ADZUNA_COUNTRIES = ["de", "at", "ch", "nl"]
EU_COUNTRY_CODES = {"de", "es", "at", "ch", "nl", "fr", "it", "pt", "be", "ie", "pl", "lu", "dk", "se", "fi", "no", "cz", "gr"}
