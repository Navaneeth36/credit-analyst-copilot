import checks
import llm
import search

# "column" = column name in ground_truth.csv
RED_FLAGS = [
    {"name": "Going concern doubt", "column": "going_concern",
     "search": "going concern material uncertainty significant doubt ability to continue",
     "question": "Does the report state a material uncertainty or significant doubt about the group's ability to continue as a going concern?"},
    {"name": "Covenant breach or pressure", "column": "covenant",
     "search": "covenant breach waiver headroom lenders amendment",
     "question": "Does the report say the company breached, nearly breached, or needed a waiver or amendment for its loan covenants?"},
    {"name": "Debt due soon", "column": "debt_due",
     "search": "refinancing maturity borrowings due within one year current liabilities",
     "question": "Does the report say a significant amount of borrowings is due within twelve months or must be refinanced?"},
    {"name": "Large write-down", "column": "write_down",
     "search": "impairment write-down goodwill charge",
     "question": "Does the report record a significant impairment or write-down in the latest year?"},
    {"name": "Auditor concern", "column": "auditor",
     "search": "qualified opinion emphasis of matter auditor resigned appointed",
     "question": "Does the report contain a qualified audit opinion, an emphasis of matter, or an auditor resignation?"},
    {"name": "Major legal or regulatory case", "column": "legal",
     "search": "litigation legal proceedings claim lawsuit fine regulator investigation",
     "question": "Does the report describe a major lawsuit, regulatory investigation or fine against the company?"},
]

# without the last rule it flagged every report's risk section
PROMPT = """You check an annual report for one warning sign.

Question: {question}

Sources:
{sources}

Reply with JSON only, in exactly this shape:
{{"found": true or false,
  "explanation": "one plain-English sentence",
  "page": page number or null,
  "quote": "exact quote from the sources, or empty if not found"}}

Only answer true if the sources clearly say so. Routine risk-factor wording
(e.g. "we may face litigation") is NOT enough. Do not guess.
"""


def check_flag(flag, index, embedder, client):
    found = search.search(flag["search"], index, embedder)
    prompt = PROMPT.format(question=flag["question"], sources=llm.format_sources(found))
    data = llm.call_json(prompt, client)

    said_yes = data.get("found") is True
    quote = data.get("quote") or ""

    if said_yes and checks.is_grounded(quote, found):
        status = "Found"
    elif said_yes:
        status = "Unverified"
    else:
        status = "Not found"

    return {"name": flag["name"], "status": status,
            "explanation": data.get("explanation", ""),
            "page": data.get("page"), "quote": quote}


def scan_all(index, embedder, client):
    return [check_flag(flag, index, embedder, client) for flag in RED_FLAGS]
