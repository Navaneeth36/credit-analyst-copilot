# numbers taken from a bad run on the Thames Water 2025 report
import checks
import extract
import ratios


def fig(name, current, prior=None, unit="millions"):
    return {"figure": name, "current_m": current, "prior_m": prior, "status": "Verified",
            "unit": unit, "currency": "GBP", "year": "2025", "quote": "", "page": 1}


def test_loss_stays_negative(monkeypatch):
    line = "Profit/(loss) for the year (1,690.7) (1,513.8)"
    chunk = {"page": 104, "text": line, "ocr": False, "kind": "rows"}
    monkeypatch.setattr(extract.search, "search", lambda *a, **k: [chunk])
    monkeypatch.setattr(extract.llm, "call_json", lambda *a, **k: {
        "current": "(1,690.7)", "prior": "(1,513.8)", "unit": "millions", "quote": line})

    result = extract.extract_figure("net_income", {"chunks": [chunk]}, None, None)
    assert result["current_m"] == -1690.7
    assert result["prior_m"] == -1513.8


def test_costs_still_positive(monkeypatch):
    line = "Finance costs (1,234.5) (1,100.0)"
    chunk = {"page": 30, "text": line, "ocr": False, "kind": "rows"}
    monkeypatch.setattr(extract.search, "search", lambda *a, **k: [chunk])
    monkeypatch.setattr(extract.llm, "call_json", lambda *a, **k: {
        "current": "(1,234.5)", "prior": "(1,100.0)", "unit": "millions", "quote": line})

    assert extract.extract_figure("interest", {"chunks": [chunk]}, None, None)["current_m"] == 1234.5


def test_tiny_net_income_is_flagged():
    figures = [fig("ebitda", 1250.1), fig("net_income", 0.1)]
    assert any("unit is probably wrong" in w for w in ratios.sanity_warnings(figures))


def test_interest_too_small_for_the_debt():
    # 1.3%
    figures = [fig("interest", 165.9), fig("debt", 13255.8)]
    assert any("too low to be the full bill" in w for w in ratios.sanity_warnings(figures))


def test_normal_interest_gives_no_warning():
    figures = [fig("interest", 700.0), fig("debt", 13255.8)]
    assert not any("of debt" in w for w in ratios.sanity_warnings(figures))


def test_debt_with_negative_ebitda_is_red_not_green():
    result = ratios.ratios_for({"ebitda": -50.0, "debt": 13255.8, "cash": 209.4})
    assert result["Leverage flag"] == "Red"


def test_profit_to_loss_is_not_called_a_unit_mixup():
    figures = [fig("net_income", -1690.7, 120.0)]
    assert not any("changed more than 5x" in w for w in ratios.sanity_warnings(figures))


# rows as they come out of page 105 (balance sheet)
NON_CURRENT = "Borrowings | 19 (16,651.9) | – (16,651.9) (15,426.5) | – (15,426.5) (13,828.1) | – (13,828.1)"
CURRENT = "Borrowings | 19 | (324.1) | – | (324.1) | (922.0) | – | (922.0) (1,909.8) | – (1,909.8)"
BALANCE_SHEET = [{"page": 105, "kind": "rows", "ocr": False, "statement": True,
                  "text": "31 March 2025 | 31 March 2024 | 1 April 2023\n" + CURRENT + "\n" + NON_CURRENT}]
INDEX = {"chunks": BALANCE_SHEET}


def fake_ai(monkeypatch, answers):
    # answers: words to look for in the prompt -> what the AI says back
    def call_json(prompt, client):
        for words, data in answers.items():
            if words in prompt:
                return data
        return {"current": None}
    monkeypatch.setattr(extract.search, "search", lambda *a, **k: BALANCE_SHEET)
    monkeypatch.setattr(extract.llm, "call_json", call_json)


def test_trimmed_quote_gets_the_real_line(monkeypatch):
    # what the AI actually gave on the Thames run - it dropped a couple of repeated numbers
    fake_ai(monkeypatch, {"non-current borrowings": {
        "label": "Borrowings", "current": "(16,651.9)", "prior": "(15,426.5)", "unit": "millions",
        "quote": "Borrowings | 19 (16,651.9) | – (15,426.5) (13,828.1) | – (13,828.1)"}})
    result = extract.read_figure("debt_noncurrent", "", INDEX, None, None)
    assert result["current_m"] == 16651.9
    assert result["quote"] == NON_CURRENT
    assert "matched to the real line" in result["status"]


def test_made_up_number_still_rejected(monkeypatch):
    fake_ai(monkeypatch, {"non-current borrowings": {
        "label": "Borrowings", "current": "(99,999.9)", "unit": "millions",
        "quote": "Borrowings | (99,999.9)"}})
    result = extract.read_figure("debt_noncurrent", "", INDEX, None, None)
    assert result["current_m"] is None and result["status"].startswith("Rejected")


def test_debt_is_both_lines_added_up(monkeypatch):
    fake_ai(monkeypatch, {
        "non-current borrowings": {"label": "Borrowings", "current": "(16,651.9)", "prior": "(15,426.5)",
                                   "unit": "millions", "quote": NON_CURRENT},
        "current borrowings (due within": {"label": "Borrowings", "current": "(324.1)", "prior": "(922.0)",
                                           "unit": "millions", "quote": CURRENT},
    })
    debt = extract.extract_figure("debt", INDEX, None, None)
    assert debt["figure"] == "debt"
    assert debt["current_m"] == 16976.0
    assert debt["prior_m"] == 16348.5


def test_debt_without_the_current_part_says_so(monkeypatch):
    fake_ai(monkeypatch, {"non-current borrowings": {
        "label": "Borrowings", "current": "(16,651.9)", "unit": "millions", "quote": NON_CURRENT}})
    debt = extract.extract_figure("debt", INDEX, None, None)
    assert debt["current_m"] == 16651.9
    assert "non-current only" in debt["status"]


def test_ai_is_told_what_the_figure_means(monkeypatch):
    prompts = []
    monkeypatch.setattr(extract.search, "search", lambda *a, **k: BALANCE_SHEET)
    monkeypatch.setattr(extract.llm, "call_json", lambda p, c: prompts.append(p) or {"current": None})
    extract.extract_figure("net_income", INDEX, None, None)
    assert "bottom line of the income statement" in prompts[0]
    assert "same column" in prompts[0]


# page 104 / 105 rows - several columns per year, Total is the last one
INCOME_STATEMENT = [
    "Thames Water Annual Report 2024/25 | 104",
    "2025 | 2024 | 2025 | 2024",
    "Underlying | items | BTL | Total | Underlying | items | BTL | Total | Underlying | items | BTL | Total",
    "Note | £m | £m | £m | £m | £m | £m | £m | £m",
    "Revenue | 2 | 2,602.8 | – | 135.4 | 2,738.2 | 2,401.4 | – | 116.8 | 2,518.2 | Profit/(loss)for the year | 12.6 (1,690.7) | 164.3 | (1,513.8) | 139.8 | (151.8) | 87.4 | 75.4",
    "Finance expense | 5 | (670.6) | (192.5) | – | (863.1) | (669.8) | – | – | (669.8)",
]
BALANCE = [
    "31 March 2025 | 31 March 2024 | 1 April 2023 | 31 March 2025 | 31 March 2024 | 1 April 2023",
    "Underlying | BTL | Total | Underlying | BTL | Total | Underlying | BTL | Total",
    "Property, plant and equipment 11 20,836.2 | – 20,836.2 19,371.8 | – 19,371.8 18,017.4 | – 18,017.4 | " + NON_CURRENT,
    "Cash and cash equivalents | 17 | 280.6 | 25.8 | 306.4 | 1,274.9 | 6.3 | 1,281.2 | 1,829.3 | 7.0 | 1,836.3",
]


def test_total_column_read_by_position():
    assert checks.total_columns(INCOME_STATEMENT[4], "Revenue", INCOME_STATEMENT) == ("2,738.2", "2,518.2")
    assert checks.total_columns(INCOME_STATEMENT[5], "Finance expense", INCOME_STATEMENT) == ("(863.1)", "(669.8)")


def test_second_table_on_the_same_row():
    # profit for the year sits to the right of revenue on the page
    assert checks.total_columns(INCOME_STATEMENT[4], "Profit/(loss)for the year",
                                INCOME_STATEMENT) == ("(1,513.8)", "75.4")


def test_three_years_side_by_side():
    assert checks.total_columns(BALANCE[3], "Cash and cash equivalents", BALANCE) == ("306.4", "1,281.2")
    assert checks.total_columns(BALANCE[2], "Borrowings", BALANCE) == ("(16,651.9)", "(15,426.5)")


def test_simple_two_column_table_left_alone():
    lines = ["2025 | 2024", "Revenue | 4,213.5 | 3,980.1"]
    assert checks.total_columns(lines[1], "Revenue", lines) is None


def test_footer_year_is_ignored():
    # "2024/25" in the footer shouldn't make it think the oldest year is first
    assert checks.total_columns(INCOME_STATEMENT[4], "Revenue", INCOME_STATEMENT) is not None


def test_wrong_column_from_the_ai_gets_corrected(monkeypatch):
    page = [{"page": 104, "kind": "rows", "ocr": False, "statement": True, "text": "\n".join(INCOME_STATEMENT)}]
    monkeypatch.setattr(extract.search, "search", lambda *a, **k: page)
    # what the model said on the real run: the Exceptional column, and this year's total as "prior"
    monkeypatch.setattr(extract.llm, "call_json", lambda *a, **k: {
        "label": "Profit/(loss) for the year", "current": "(1,690.7)", "prior": "(1,513.8)",
        "unit": "millions", "quote": "Profit/(loss)for the year | 12.6 (1,690.7) | 164.3 | (1,513.8)"})
    result = extract.extract_figure("net_income", {"chunks": page}, None, None)
    assert (result["current_m"], result["prior_m"]) == (-1513.8, 75.4)
    assert result["status"] == "Verified (Total column)"