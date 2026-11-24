import re

# PDFs use curly quotes/dashes, the model usually types plain ones
REPLACEMENTS = {
    "‘": "'", "’": "'",  # ‘ ’
    "“": '"', "”": '"',  # “ ”
    "–": "-", "—": "-",  # – —
    "−": "-",                 # minus sign
    " ": " ",                 # non-breaking space
}


def plain(text):
    text = text or ""
    for fancy, simple in REPLACEMENTS.items():
        text = text.replace(fancy, simple)
    return text


def clean(text):
    return " ".join(plain(text).replace("|", " ").split()).lower()


def is_grounded(quote, found):
    quote = clean(quote).strip(" .\"'")
    if len(quote) < 8:
        return False  # too short to mean anything

    sources = clean(" ".join(chunk["text"] for chunk in found))
    if quote in sources:
        return True

    # model sometimes shortens with "..." - ok if each piece is in there
    pieces = [p.strip(" .") for p in quote.split("...") if p.strip(" .")]
    return len(pieces) > 1 and all(p in sources for p in pieces)


def real_line(quote, label, number_text, found):
    # quote not word for word? find the real line it came from
    if not quote or is_grounded(quote, found) or not number_text:
        return quote
    # label from the AI, or whatever words the quote starts with
    names = [clean(label or ""), clean(re.split(r"[\d|£$€]", quote)[0])]
    names = [n.strip(" :-(") for n in names if len(n.strip(" :-(")) >= 4]
    for chunk in found:
        for line in chunk["text"].splitlines():
            text = clean(line)
            for n in names:
                # label can be halfway along when two tables sit side by side
                at = text.find(n)
                if at != -1 and number_in_text(number_text, text[at:]):
                    return line
    return quote


VALUE = re.compile(r"^\(?-?\d[\d,]*(\.\d+)?\)?$|^-$")
NOTE_REF = re.compile(r"^\d{1,2}(,\d{1,2})*$")   # "19", "3,16"


def row_values(line, label):
    # numbers/dashes after the label, up to the next text
    text = clean(line)
    start = text.find(clean(label))
    if start == -1:
        return None
    tokens = text[start + len(clean(label)):].split()
    values = []
    for t in tokens:
        if re.search("[a-z]", t):
            break  # next table's label on a side-by-side page
        if not values and NOTE_REF.match(t):
            continue
        if VALUE.match(t):
            values.append(t)
    return values


def columns_per_year(header):
    # "Underlying | items | BTL | Total | Underlying ..." -> 4
    cells = [c for c in clean(header).split() if c not in ("£m", "£000", "note", "$m", "€m")]
    return cells.index("total") + 1 if "total" in cells else None


def total_columns(line, label, page_lines):
    # tables with Underlying / Exceptional / Total per year: take both Totals by position.
    # None if the table isn't like that
    if not label or line not in page_lines:
        return None
    above = page_lines[:page_lines.index(line)]
    headers = [h for h in above if clean(h).split().count("total") >= 2]
    if not headers:
        return None
    block = columns_per_year(headers[-1])

    # nearest line above with two different years in it, e.g. "2025 | 2024"
    # (not the page footer "Annual Report 2024/25")
    year_lines = [re.findall(r"\b(20\d\d)\b(?!/)", h) for h in above]
    year_lines = [[int(y) for y in ys] for ys in year_lines if len(set(ys)) >= 2]
    if not year_lines or year_lines[-1][0] < max(year_lines[-1][1:]):
        return None  # only trust it when the latest year comes first

    values = row_values(line, label)
    if not block or block < 2 or not values or len(values) < 2 * block or len(values) % block:
        return None
    current, prior = values[block - 1], values[2 * block - 1]
    return (None if current == "-" else current), (None if prior == "-" else prior)


def find_number(number_text, text):
    digits = clean(str(number_text)).replace(",", "").strip("()-")
    if not digits:
        return None

    # whole numbers only (213 shouldn't match 4,213.5), and 300 should match 300.0
    pattern = r"(?<![\d.])" + re.escape(digits) + r"(?:\.0+)?(?!\.?\d)"
    match = re.search(pattern, clean(text).replace(",", ""))
    return match.start() if match else None


def number_in_text(number_text, text):
    return find_number(number_text, text) is not None


# e.g. "2025 2024" or "2025 £m 2024"
YEAR_HEADER = re.compile(r"\b(20\d{2})\b(?:\s+\S{1,3}){0,3}\s+(20\d{2})\b")


def column_order_ok(current_text, prior_text, quote, found):
    # True = ok, False = looks swapped, None = can't tell
    if not current_text or not prior_text:
        return None
    if clean(str(current_text)) == clean(str(prior_text)):
        return None

    # year headings from whichever chunk the quote came from
    lines = []
    for chunk in found:
        if is_grounded(quote, [chunk]):
            lines += chunk["text"].splitlines()

    header = None
    for line in lines:
        header = YEAR_HEADER.search(line)
        if header:
            break
    if header is None:
        return None

    latest_first = int(header.group(1)) > int(header.group(2))

    where_current = find_number(current_text, quote)
    where_prior = find_number(prior_text, quote)
    if where_current is None or where_prior is None or where_current == where_prior:
        return None

    return (where_current < where_prior) == latest_first


def parse_number(number_text):
    # brackets = negative
    if number_text is None:
        return None
    text = clean(str(number_text)).replace(",", "")
    negative = "(" in text or text.lstrip("£$€ ").startswith("-")

    match = re.search(r"\d+(\.\d+)?", text)
    if not match:
        return None
    value = float(match.group(0))
    return -value if negative else value