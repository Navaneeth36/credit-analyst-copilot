"""Scores the chat answers against questions you've checked yourself.

Usage:  python evaluate_chat.py reports/ chat_questions.csv

chat_questions.csv columns:
  file      - the report in the folder
  question  - what to ask
  expect    - text the right answer must contain, e.g. 1,513.8
              Leave it blank for a trick question the report can't answer -
              then the right answer is "I couldn't find this in the report."
"""
import os
import sys

import pandas as pd

import checks
import llm
import pipeline
import qa
import search


def score(answer, quotes, pages, numbers, expect, page_text):
    said_not_found = qa.NOT_FOUND in answer.lower()

    if not expect:  # trick question
        return {"correct": said_not_found, "made_up": not said_not_found,
                "right_page": None, "note": "should say it couldn't find this"}

    correct = checks.clean(expect).replace(",", "") in checks.clean(answer).replace(",", "")
    made_up = any(not ok for _, ok in quotes + pages + numbers)

    cited = [p for p, _ in pages]
    right_page = any(checks.number_in_text(expect, page_text.get(p, "")) or
                     checks.clean(expect) in checks.clean(page_text.get(p, "")) for p in cited)

    note = []
    if not correct:
        note.append("missing the expected answer")
    if made_up:
        note.append("has a quote, page or figure not in the report")
    if not cited:
        note.append("no page cited")
    elif not right_page:
        note.append("cited page doesn't contain the answer")
    return {"correct": correct, "made_up": made_up, "right_page": right_page, "note": "; ".join(note)}


def evaluate(folder, questions_csv):
    questions = pd.read_csv(questions_csv, keep_default_na=False)
    embedder = search.load_embedder()
    client = llm.get_client()
    rows = []

    for name, group in questions.groupby("file"):
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            print("Skipping", name, "- not in", folder)
            continue
        print("Reading", name, "...")
        with open(path, "rb") as f:
            prepared = pipeline.prepare(f.read(), embedder, name)
        page_text = {p["page"]: "\n".join(p["lines"] + p["rows"]) for p in prepared["pages"]}

        for _, q in group.iterrows():
            answer, quotes, found = qa.answer_question(q["question"], prepared["index"], embedder, client)
            result = score(answer, quotes, qa.check_pages(answer, found), qa.check_numbers(answer, found),
                           str(q["expect"]).strip(), page_text)
            rows.append({"file": name, "question": q["question"], "expect": q["expect"],
                         **result, "answer": answer})
            print(("PASS " if result["correct"] and not result["made_up"] else "FAIL ") + q["question"])

    results = pd.DataFrame(rows)
    results.to_csv("chat_results.csv", index=False)
    if len(results):
        print(f"\nRight answer:          {results['correct'].sum()} of {len(results)}")
        print(f"Made something up:     {results['made_up'].sum()} of {len(results)}  (aim for 0)")
        real = results[results["expect"] != ""]
        if len(real):
            print(f"Cited the right page:  {real['right_page'].sum()} of {len(real)}")
    print("\nEvery answer saved to chat_results.csv")
    return results


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    evaluate(sys.argv[1], sys.argv[2])
