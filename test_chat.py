# chat checks, with a fake llm
import qa

SOURCES = [
    {"page": 104, "kind": "rows", "ocr": False,
     "text": "Profit/(loss) for the year | 12.6 | (1,690.7) | 164.3 | (1,513.8) | 139.8 | 75.4"},
    {"page": 156, "kind": "lines", "ocr": False,
     "text": "In May 2025 Ofwat announced that the Company would be fined £122.7 million."},
]


def ask(monkeypatch, pretend_answer):
    monkeypatch.setattr(qa.search, "search", lambda *a, **k: SOURCES)
    monkeypatch.setattr(qa.llm, "call_text", lambda *a, **k: pretend_answer)
    answer, checked, found = qa.answer_question("anything", None, None, None)
    return answer, checked, qa.check_pages(answer, found), qa.check_numbers(answer, found)


def test_good_answer_passes_every_check(monkeypatch):
    _, quotes, pages, numbers = ask(monkeypatch,
        'Ofwat fined the company £122.7 million (page 156): '
        '"Ofwat announced that the Company would be fined £122.7 million"')
    assert quotes and all(ok for _, ok in quotes)
    assert pages == [(156, True)]
    assert all(ok for _, ok in numbers)


def test_made_up_quote_is_caught(monkeypatch):
    _, quotes, _, _ = ask(monkeypatch,
        'They were fined (page 156): "the regulator fined the company a record amount"')
    assert quotes == [("the regulator fined the company a record amount", False)]


def test_made_up_number_is_caught(monkeypatch):
    _, _, _, numbers = ask(monkeypatch, "The fine was £450.0 million (page 156).")
    assert ("450.0", False) in numbers


def test_wrong_page_is_caught(monkeypatch):
    _, _, pages, _ = ask(monkeypatch, "The fine was £122.7 million (page 12).")
    assert pages == [(12, False)]


def test_loss_in_brackets_matches(monkeypatch):
    _, _, _, numbers = ask(monkeypatch, "The loss for the year was (1,513.8) (page 104).")
    assert numbers == [("1,513.8", True)]


def test_years_and_page_numbers_are_not_treated_as_figures(monkeypatch):
    _, _, _, numbers = ask(monkeypatch, "In 2025 the company was fined (pages 156 and 104).")
    assert numbers == []


def test_several_pages_in_one_citation():
    assert qa.cited_pages("See (pages 104, 105 and 156) and (p. 12)") == [12, 104, 105, 156]


def test_curly_quotes_still_found(monkeypatch):
    _, quotes, _, _ = ask(monkeypatch,
        "Fined (page 156): “Ofwat announced that the Company would be fined”")
    assert quotes and quotes[0][1] is True


def test_not_found_answer(monkeypatch):
    answer, quotes, pages, numbers = ask(monkeypatch, "I couldn't find this in the report.")
    assert qa.NOT_FOUND in answer.lower()
    assert quotes == [] and pages == [] and numbers == []


def test_statement_pages_always_included(monkeypatch):
    notes = [{"page": 164, "kind": "lines", "ocr": False, "text": "Expected credit losses 317.6"}]
    statement = [{"page": 104, "kind": "rows", "ocr": False, "statement": True,
                  "text": "Profit/(loss) for the year | 12.6 (1,690.7) | 164.3 | (1,513.8)"}]
    monkeypatch.setattr(qa.search, "search", lambda *a, **k: statement if k.get("only") else list(notes))
    shown = []
    monkeypatch.setattr(qa.llm, "call_text", lambda prompt, c: shown.append(prompt) or "ok")
    _, _, found = qa.answer_question("what was the loss for this year", None, None, None)
    assert [c["page"] for c in found] == [104, 164]
    assert "(1,513.8)" in shown[0]