# Credit Analyst Copilot

Give it a company's annual report (PDF) and it pulls out six key figures for this year and last year,
works out the credit health ratios, looks for six warning signs lenders care about, and writes a short
screening note. It works for private companies too, which you can't get from stock-market data feeds.

**The main rule: the AI only reads. Plain code does the checking and the maths.**
Every figure has to come with an exact quote from the report, the number has to be in that quote,
and it has to be in the latest-year column. If any of that fails, the figure is rejected and left
for a person to fill in.

## Why not just "chat with a PDF"?

Those tools go wrong in a few predictable ways. Here's what this one does about each:

| Problem | What this does |
|---|---|
| The AI makes things up | Every quote is checked word for word against the report |
| It copies the wrong number | The number has to appear in its own quote |
| It takes last year's column | Reads the year headings in the table and checks which column the number sits in |
| PDF tables come out scrambled | Rebuilds rows from where words sit on the page; wide gaps become ` \| ` column breaks |
| Searching by meaning misses exact terms like "going concern" | Searches two ways at once: by meaning (embeddings) and by keyword (BM25) |
| Wrong units or impossible numbers | Common-sense checks, e.g. EBITDA bigger than revenue, mixed currencies, 5x jumps, interest far too low for the debt |
| Long reports where search lands on the notes | The main statement pages (income statement, balance sheet, cash flow) are spotted and always given to the AI |
| Scanned PDFs and photos | Pages with no real text are read with free local OCR (RapidOCR). PNG/JPG uploads work too, and figures from scanned pages are labelled for checking |
| No idea how accurate it is | `evaluate.py` scores it against figures you've checked by hand |
| Free-tier limits | Every AI answer is cached, so re-runs cost nothing |
| Confidential reports going to the cloud | Runs fully offline with Ollama by default, so nothing leaves your computer |
| Stuck with one AI provider | Works with Groq (free cloud) or Ollama (free, local) |

## Setup (offline version)

You need internet **once** for the downloads. After that: no internet, no account, no key.

```bash
# 1. Install Ollama from https://ollama.com and open it once.

# 2. Get the AI model (about 4.7 GB) and build this project's version of it
ollama pull qwen2.5:7b
ollama create credit-copilot -f Modelfile

# 3. Python environment and libraries
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Save the embedding model inside the project (about 90 MB)
python download_models.py

# 5. Check everything - it should finish with "All good"
python check_setup.py

# 6. Run it (this part works with Wi-Fi off)
streamlit run app.py
```

On an 8 GB Mac, change the first line of `Modelfile` to `FROM qwen2.5:3b`, run `ollama pull qwen2.5:3b`,
then `ollama create credit-copilot -f Modelfile` again. It's faster, but a bit less accurate.

To use Groq instead: `export LLM_PROVIDER=groq` and `export GROQ_API_KEY="gsk_..."`.

## Measuring accuracy

1. Put 5-10 annual report PDFs in a `reports/` folder.
2. Open each one, look up the six figures yourself, and add a row to `ground_truth.csv`
   (values in millions, red flags as `yes` / `no`, blank if you're not sure).
3. Run `python evaluate.py reports/ ground_truth.csv`

It prints accuracy for each figure, how many wrong answers still got through as "Verified"
(the dangerous kind), red flags caught and false alarms. Full detail goes to `evaluation_results.csv`.

## Testing the chat

The "Ask a question" tab checks every answer three ways: quotes must be word for word in the report,
cited pages must be pages the AI was actually given, and every figure in the answer must appear in
the sources. Anything that fails is marked with a ❌.

To score it properly, write some questions you know the answers to in `chat_questions.csv`
(leave `expect` blank for trick questions the report can't answer), then run:

```bash
python evaluate_chat.py reports/ chat_questions.csv
```

## Tests

`pytest -q` runs everything. The tests use a fake AI, so no internet or key needed.

## Limitations

- OCR can misread characters on blurry scans. Figures from scanned pages are labelled, so check them.
  It also takes a few seconds per scanned page.
- "Not found" for a red flag means it wasn't in the passages searched, not that it definitely isn't there.
- The checks prove a quote is real and the number is in the right place. They don't prove the AI
  picked the right line item, so always confirm against the cited page.
- Lots of UK companies don't report EBITDA. When that happens it uses operating profit and says so.
