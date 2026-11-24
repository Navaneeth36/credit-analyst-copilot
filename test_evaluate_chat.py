import evaluate_chat

PAGES = {104: "Profit/(loss) for the year | (1,513.8) | 75.4"}


def test_right_answer_right_page():
    r = evaluate_chat.score("A loss of £1,513.8m (page 104).", [], [(104, True)], [("1,513.8", True)],
                            "1,513.8", PAGES)
    assert r["correct"] and not r["made_up"] and r["right_page"]


def test_wrong_number():
    r = evaluate_chat.score("A loss of £1,690.7m (page 104).", [], [(104, True)], [("1,690.7", True)],
                            "1,513.8", PAGES)
    assert not r["correct"]


def test_right_number_wrong_page():
    r = evaluate_chat.score("A loss of £1,513.8m (page 12).", [], [(12, False)], [("1,513.8", True)],
                            "1,513.8", PAGES)
    assert r["correct"] and r["made_up"] and not r["right_page"]


def test_trick_question_admitted():
    r = evaluate_chat.score("I couldn't find this in the report.", [], [], [], "", PAGES)
    assert r["correct"] and not r["made_up"]


def test_trick_question_made_up():
    r = evaluate_chat.score("They run 40 stores in France (page 3).", [], [(3, True)], [], "", PAGES)
    assert not r["correct"] and r["made_up"]
