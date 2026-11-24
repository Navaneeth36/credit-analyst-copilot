"""Compare extracted figures/flags with ones checked by hand.

Usage:  python evaluate.py reports/ ground_truth.csv
"""
import os
import sys

import pandas as pd

import flags
import llm
import pipeline
import search

FLAG_COLUMNS = {f["name"]: f["column"] for f in flags.RED_FLAGS}


def close_enough(found, truth, tolerance=0.01):
    if found is None or pd.isna(truth):
        return False
    return abs(found - truth) <= abs(truth) * tolerance


def evaluate(folder, truth_csv):
    truth = pd.read_csv(truth_csv)
    embedder = search.load_embedder()
    client = llm.get_client()
    rows = []

    for _, expected in truth.iterrows():
        name = expected["file"]
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            print("Skipping", name, "- not in", folder)
            continue
        print("Checking", name, "...")
        with open(path, "rb") as f:
            # needs the name for png/jpg
            result = pipeline.analyse(pipeline.prepare(f.read(), embedder, name), embedder, client)

        for fig in result["figures"]:
            target = expected.get(fig["figure"])
            if pd.isna(target):
                continue
            rows.append({"file": name, "type": "figure", "item": fig["figure"],
                         "expected": target, "got": fig["current_m"], "status": fig["status"],
                         "correct": close_enough(fig["current_m"], target)})

        for flag in result["flags"]:
            target = expected.get(FLAG_COLUMNS[flag["name"]])
            if pd.isna(target):
                continue
            said_yes = flag["status"] == "Found"
            rows.append({"file": name, "type": "flag", "item": flag["name"],
                         "expected": target, "got": "yes" if said_yes else "no", "status": flag["status"],
                         "correct": said_yes == (str(target).lower() == "yes")})

    results = pd.DataFrame(rows)
    results.to_csv("evaluation_results.csv", index=False)

    figures = results[results["type"] == "figure"] if len(results) else results
    if len(figures):
        print("\nFigure accuracy (within 1%):")
        per_figure = figures.groupby("item")["correct"].agg(["sum", "count"])
        print(per_figure.rename(columns={"sum": "correct", "count": "checked"}))

        # this is the one that matters
        verified = figures["status"].str.startswith("Verified")
        wrong_but_verified = figures[verified & ~figures["correct"]]
        print(f"\nVerified but wrong (the dangerous kind): {len(wrong_but_verified)}")
        print(f"Rejected or not found (safe failures): {(~verified).sum()}")

    flag_rows = results[results["type"] == "flag"] if len(results) else results
    if len(flag_rows):
        answers = flag_rows["expected"].astype(str).str.lower()
        should_be_yes = flag_rows[answers == "yes"]
        should_be_no = flag_rows[answers == "no"]
        print(f"\nRed flags caught: {should_be_yes['correct'].sum()} of {len(should_be_yes)}")
        print(f"False alarms: {(~should_be_no['correct']).sum()} of {len(should_be_no)}")

    print("\nFull detail saved to evaluation_results.csv")
    return results


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    evaluate(sys.argv[1], sys.argv[2])
