import re

import checks
import llm
import search

# search terms for each figure. statement names help push results away from the notes
FIGURES = {
    "revenue": "revenue turnover total sales for the year consolidated income statement",
    "ebitda": "EBITDA adjusted EBITDA operating profit for the year",
    "net_income": "profit loss after tax profit for the year net income consolidated income statement",
    "interest": "finance costs finance expense interest payable consolidated income statement",
    "debt": "total borrowings loans bonds debt non-current current balance sheet",
    "cash": "cash and cash equivalents at the end of the year balance sheet",
}

# what the AI is told it's looking for. "net_income" on its own meant nothing to it
DESCRIBE = {
    "revenue": "total revenue (turnover) for the year, from the income statement",
    "ebitda": "EBITDA for the year (if not reported, operating profit)",
    "net_income": "profit or loss for the year after tax - the bottom line of the income statement",
    "interest": "total finance costs / finance expense from the income statement, not a breakdown from the notes",
    "debt_noncurrent": "non-current borrowings (due after more than one year) from the balance sheet",
    "debt_current": "current borrowings (due within one year) from the balance sheet",
    "cash": "cash and cash equivalents from the balance sheet (statement of financial position), not the cash flow statement",
}

# debt is two lines on a balance sheet, so it gets read twice and added up here
DEBT_PARTS = {
    "debt_noncurrent": "non-current borrowings loans bonds due after one year balance sheet",
    "debt_current": "current borrowings loans due within one year balance sheet",
}

# these live on the main statements, so look there first
ON_STATEMENTS = {"revenue", "net_income", "interest", "debt_noncurrent", "debt_current", "cash"}

# can be a loss, keep the sign
CAN_BE_NEGATIVE = {"ebitda", "net_income"}

# to millions
UNITS = {"thousands": 0.001, "millions": 1, "billions": 1000}

PROMPT = """You extract one financial figure from an annual report.

Figure wanted: {figure}

Sources (each starts with its page number; tables keep one row per line):
{sources}

Reply with JSON only, in exactly this shape:
{{"label": "line item name as written in the report",
  "current_year": "the latest year, e.g. 2025",
  "current": "the latest year's number exactly as written, e.g. 4,213.5",
  "prior": "the previous year's number exactly as written, or null",
  "unit": "thousands, millions or billions",
  "currency": "GBP, USD, EUR etc.",
  "page": page number,
  "quote": "copy the exact line that contains the number(s)"}}

Rules:
- Group (consolidated) figures, not parent company only.
- If EBITDA is not reported, use operating profit and say so in "label".
- Tables usually show the latest year first. Check the column headings.
- Use the TOTAL line from the main group statement, not a smaller line from a note or one business segment.
- If each year has several columns (e.g. Underlying, Exceptional items, Total), use the Total column.
- "prior" must come from the same column as "current", one year earlier (Total 2025 -> Total 2024).
- Take the unit from the table heading: £m or "millions" = millions, £'000 or "thousands" = thousands.
- Copy numbers in brackets with their brackets, e.g. (1,690.7). Brackets mean a loss or negative.
- If you cannot find the figure, reply {{"current": null}}.
"""


def verify(number_text, quote, found):
    if number_text in (None, "", "null"):
        return None, "Not found"
    if not checks.is_grounded(quote, found):
        return None, "Rejected: quote not in report"
    if not checks.number_in_text(str(number_text), quote):
        return None, "Rejected: number not in quote"
    return checks.parse_number(number_text), "Verified"


def is_statement(chunk):
    return chunk.get("statement") and chunk["kind"] == "rows"


def page_rows(index, page):
    lines = []
    for chunk in index["chunks"]:
        if chunk["page"] == page and chunk["kind"] == "rows":
            for line in chunk["text"].splitlines():
                if line not in lines:  # chunks overlap
                    lines.append(line)
    return lines


def ask(name, found, client):
    return llm.call_json(PROMPT.format(figure=DESCRIBE[name], sources=llm.format_sources(found)), client)


def read_figure(name, query, index, embedder, client):
    found = []
    if name in ON_STATEMENTS:
        # statement pages only (the notes kept winning on long reports), and the whole
        # page rather than bits of it - they're short and a row we need kept getting cut off
        best = search.search(query, index, embedder, only=is_statement)
        pages = list(dict.fromkeys(c["page"] for c in best))[:2]
        found = [{"page": p, "kind": "rows", "ocr": False, "statement": True,
                  "text": "\n".join(page_rows(index, p))} for p in pages]
    data = ask(name, found, client) if found else {}

    if data.get("current") in (None, "", "null"):
        found = search.search(query, index, embedder)  # not on the statements, try everywhere
        data = ask(name, found, client)

    # if it trimmed the quote a bit, swap in the real line (same label + same number)
    original = data.get("quote") or ""
    quote = checks.real_line(original, data.get("label"), data.get("current"), found)

    # several columns per year? read the Total ones by position instead of trusting the AI
    repaired = quote != original
    by_position = None
    # the label as the AI quoted it - the full line might start with another table's row
    label = re.split(r"[\d|£$€]", original or quote)[0].strip(" :-(")
    for page in dict.fromkeys(c["page"] for c in found if checks.is_grounded(quote, [c])):
        rows = page_rows(index, page)
        line = next((r for r in rows if checks.clean(quote) in checks.clean(r)), None)
        by_position = checks.total_columns(line, label, rows) if line else None
        if by_position:
            data["current"], data["prior"] = by_position
            data["page"] = page
            quote = line
            break
    unit = str(data.get("unit", "")).lower().strip()
    to_millions = UNITS.get(unit, 1)  # default millions

    current, status = verify(data.get("current"), quote, found)
    prior, prior_status = verify(data.get("prior"), quote, found)

    # right column?
    if status == "Verified" and by_position:
        status = "Verified (Total column)"
    elif status == "Verified":
        order = checks.column_order_ok(data.get("current"), data.get("prior"), quote, found)
        if order is False:
            current = prior = None
            status = prior_status = "Rejected: looks like the wrong year's column"
        elif order is None:
            status = "Verified (column not checked)"

    if status.startswith("Verified") and repaired and not by_position:
        status += " (quote matched to the real line)"

    # OCR can misread digits
    if status.startswith("Verified"):
        from_scan = any(chunk.get("ocr") and checks.is_grounded(quote, [chunk]) for chunk in found)
        if from_scan:
            status += " (scanned page, check the number)"

    def in_millions(value):
        if value is None:
            return None
        # costs are in brackets, we just want the size. losses keep their sign
        if name not in CAN_BE_NEGATIVE:
            value = abs(value)
        return round(value * to_millions, 1)

    return {
        "figure": name,
        "current_m": in_millions(current),
        "prior_m": in_millions(prior),
        "status": status,
        "prior_status": prior_status,
        "label": data.get("label", ""),
        "year": data.get("current_year", ""),
        "unit": data.get("unit", ""),
        "currency": data.get("currency", ""),
        "page": data.get("page"),
        "quote": quote,
    }


def add_debt(long_term, short_term):
    if long_term["current_m"] is None:
        return dict(long_term, figure="debt")  # can't do much without the big one

    total = dict(long_term, figure="debt", label="Borrowings (non-current + current)")
    if short_term["current_m"] is None:
        # some companies really have none due this year, but say so
        total["status"] += " (non-current only, current borrowings not found)"
        return total

    total["current_m"] = round(long_term["current_m"] + short_term["current_m"], 1)
    if long_term["prior_m"] is not None and short_term["prior_m"] is not None:
        total["prior_m"] = round(long_term["prior_m"] + short_term["prior_m"], 1)
    else:
        total["prior_m"] = None
    if not short_term["status"].startswith("Verified") or "not checked" in short_term["status"]:
        total["status"] = "Verified (column not checked)"
    total["quote"] = long_term["quote"] + "  +  " + short_term["quote"]
    return total


def extract_figure(name, index, embedder, client):
    if name == "debt":
        parts = {part: read_figure(part, query, index, embedder, client) for part, query in DEBT_PARTS.items()}
        return add_debt(parts["debt_noncurrent"], parts["debt_current"])
    return read_figure(name, FIGURES[name], index, embedder, client)


def extract_all(index, embedder, client):
    return [extract_figure(name, index, embedder, client) for name in FIGURES]