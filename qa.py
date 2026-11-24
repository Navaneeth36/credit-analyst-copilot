import re

import checks
import llm
import search

PROMPT = """You are a credit analyst's assistant. Answer using ONLY the sources below.

Rules:
- If the sources don't contain the answer, say "I couldn't find this in the report."
- Cite the page after each fact, like (page 12).
- Include at least one exact quote from the sources in double quotes as evidence.
- For figures, use the main financial statements (income statement, balance sheet, cash flow) over the notes.
- Say which year a figure is for. "This year" means the latest year in the report.
- Keep it short and in plain English.

Sources:
{sources}

Question: {question}
"""

NOT_FOUND = "couldn't find this in the report"

# "(page 12)", "(pages 12 and 14)", "(p. 12)"
PAGE_REF = re.compile(r"\((?:pages?|p\.)\s*([\d,\s&and-]+)\)", re.I)

# 1,513.8 / (863.1) / 122.7, not small counts
NUMBER = re.compile(r"\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\(?\d+\.\d+\)?|\b\d{3,}\b")


def find_quotes(answer):
    # 15+ chars, shorter ones are usually just a quoted word
    return re.findall(r'"([^"]{15,})"', checks.plain(answer))


def cited_pages(answer):
    pages = []
    for group in PAGE_REF.findall(answer):
        pages += [int(n) for n in re.findall(r"\d+", group)]
    return sorted(set(pages))


def check_pages(answer, found):
    # was each cited page actually in the sources?
    given = {chunk["page"] for chunk in found}
    return [(page, page in given) for page in cited_pages(answer)]


def check_numbers(answer, found):
    # any number not in the sources was made up (or calculated)
    text = PAGE_REF.sub("", checks.plain(answer))
    for quote in find_quotes(answer):
        text = text.replace(quote, "")
    sources = " ".join(chunk["text"] for chunk in found)

    results = []
    for raw in NUMBER.findall(text):
        number = raw.strip("()")
        if re.fullmatch(r"(19|20)\d\d", number):
            continue  # year
        if number not in [n for n, _ in results]:
            results.append((number, checks.number_in_text(number, sources)))
    return results


def on_statement(chunk):
    return chunk.get("statement") and chunk["kind"] == "rows"


def answer_question(question, index, embedder, client):
    found = search.search(question, index, embedder)
    # plain search kept missing the income statement ("what was the loss" went to the notes)
    # so always add the best bits of the main statements
    have = {(c["page"], c["kind"], c["text"]) for c in found}
    for chunk in reversed(search.search(question, index, embedder, k=2, only=on_statement)):
        if (chunk["page"], chunk["kind"], chunk["text"]) not in have:
            found.insert(0, chunk)
    answer = llm.call_text(PROMPT.format(sources=llm.format_sources(found), question=question), client)

    checked = [(quote, checks.is_grounded(quote, found)) for quote in find_quotes(answer)]
    return answer, checked, found