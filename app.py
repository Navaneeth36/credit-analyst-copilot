import pandas as pd
import streamlit as st

import config
import extract
import flags
import llm
import pipeline
import qa
import ratios
import report
import search

st.set_page_config(page_title="Credit Analyst Copilot", layout="wide")
st.title("Credit Analyst Copilot")
st.write("Drop in an annual report to get the key numbers, debt ratios and any red flags, "
         "each with the page it came from.")

DOTS = {"Green": "🟢", "Amber": "🟠", "Red": "🔴", "No data": "⚪"}
FLAG_ICONS = {"Found": "🚩", "Unverified": "❓", "Not found": "✅"}

try:
    client = llm.get_client()
except RuntimeError as e:
    st.error(str(e))
    st.stop()

st.sidebar.write(f"**Model:** `{llm.settings()['model']}`")
if config.PROVIDER == "ollama":
    st.sidebar.caption("Running locally. The report stays on this computer.")
else:
    st.sidebar.caption("Running on Groq. Repeat runs are cached.")


# streamlit reruns everything on each click, so cache the slow bits
@st.cache_resource
def get_embedder():
    return search.load_embedder()


@st.cache_resource
def prepare(file_bytes, file_name):
    return pipeline.prepare(file_bytes, get_embedder(), file_name)


def change(now, before, fmt):
    # "+0.30x vs prior" text under the metric
    if now is None or before is None:
        return None
    return fmt.format(now - before)


# ---------------------------------------------------------------- upload
uploaded = st.file_uploader("Annual report (PDF, or a photo/scan as PNG or JPG)",
                            type=["pdf", "png", "jpg", "jpeg"])
if uploaded is None:
    st.info("Upload a PDF to start. Most companies put their annual report on their website.")
    st.stop()

# different file uploaded -> reset
if st.session_state.get("file") != uploaded.name:
    st.session_state.clear()
    st.session_state["file"] = uploaded.name

with st.spinner("Reading the report (scanned pages take a few seconds each)..."):
    prepared = prepare(uploaded.getvalue(), uploaded.name)
embedder = get_embedder()

total_pages = len(prepared["pages"]) + len(prepared["empty_pages"])
st.success(f"Read {total_pages} pages into {len(prepared['chunks'])} searchable chunks.")

scanned = [p for p in prepared["pages"] if p["ocr"]]
if scanned:
    average = sum(p["confidence"] for p in scanned) / len(scanned)
    st.info(f"{len(scanned)} page(s) were scanned images, so they were read with OCR "
            f"(average confidence {average:.0%}). OCR can misread characters, so figures from "
            "these pages are labelled for you to double-check.")
    if average < 0.7:
        st.warning("OCR confidence is low. The scan might be blurry or small, so expect more rejected figures.")
if prepared["empty_pages"]:
    st.caption(f"{len(prepared['empty_pages'])} page(s) had no text at all, even with OCR (e.g. photos).")

tab_health, tab_flags, tab_ask, tab_report = st.tabs(
    ["Financial health", "Red flags", "Ask a question", "Download report"])

# ---------------------------------------------------------------- health
with tab_health:
    if st.button("Extract figures and check health"):
        with st.spinner("Finding each figure (6 AI calls)..."):
            st.session_state["figures"] = extract.extract_all(prepared["index"], embedder, client)

    if "figures" in st.session_state:
        figures = st.session_state["figures"]

        # remember the original status so clearing a typed value puts it back
        for f in figures:
            f.setdefault("ai_status", f["status"])

        needs_fix = [f for f in figures if not f["ai_status"].startswith("Verified")]
        if needs_fix:
            st.caption("These couldn't be verified. Type the correct latest-year value (in millions) "
                       "from the report, or leave it blank.")
            for f in needs_fix:
                typed = st.number_input(f"{f['figure']} ({f['ai_status']})", value=None,
                                        key=f"fix_{f['figure']}")
                f["current_m"] = typed
                f["status"] = f["ai_status"] if typed is None else "Entered by user"

        columns = ["figure", "current_m", "prior_m", "status", "label", "year", "currency", "page", "quote"]
        st.dataframe(pd.DataFrame(figures)[columns], width="stretch", hide_index=True)

        results = ratios.compute(figures)
        st.session_state["ratios"] = results
        st.session_state["warnings"] = ratios.sanity_warnings(figures)

        now, before = results["current"], results["prior"]
        st.subheader("Health check (latest year vs prior year)")

        # show warnings before the tiles
        for w in st.session_state["warnings"]:
            st.warning(w)
        if any(not f["status"].startswith(("Verified", "Entered")) for f in figures):
            st.caption("Some figures are missing, so some ratios below can't be worked out.")
        c1, c2, c3 = st.columns(3)

        lev = now["Net debt / EBITDA"]
        c1.metric(f"{DOTS[now['Leverage flag']]} Net debt / EBITDA",
                  "-" if lev is None else f"{lev}x",
                  change(lev, before["Net debt / EBITDA"], "{:+.2f}x vs prior"),
                  delta_color="inverse")  # higher leverage = worse

        cover = now["Interest cover"]
        c2.metric(f"{DOTS[now['Cover flag']]} Interest cover",
                  "-" if cover is None else f"{cover}x",
                  change(cover, before["Interest cover"], "{:+.2f}x vs prior"))

        margin = now["Profit margin %"]
        c3.metric("Profit margin",
                  "-" if margin is None else f"{margin}%",
                  change(margin, before["Profit margin %"], "{:+.1f} pts vs prior"))

        st.caption("Rules: net debt/EBITDA under 3 = green, 3-5 = amber, over 5 = red. "
                   "Interest cover above 4 = green, 2-4 = amber, under 2 = red.")

# ---------------------------------------------------------------- red flags
with tab_flags:
    if st.button("Scan for red flags"):
        with st.spinner(f"Checking {len(flags.RED_FLAGS)} warning signs..."):
            st.session_state["flags"] = flags.scan_all(prepared["index"], embedder, client)

    if "flags" in st.session_state:
        results = st.session_state["flags"]
        found = [r for r in results if r["status"] == "Found"]
        if found:
            st.error(f"{len(found)} warning sign(s) found: " + ", ".join(r["name"] for r in found))
        else:
            st.success("No verified warning signs found.")

        for r in results:
            st.markdown(f"**{FLAG_ICONS[r['status']]} {r['name']}**: {r['status']}")
            if r["status"] != "Not found":
                st.write(r["explanation"])
                st.caption(f"Page {r['page']}: \"{r['quote']}\"")
        st.caption("'Not found' means it wasn't in the passages searched - not proof it isn't there.")

# ---------------------------------------------------------------- questions
with tab_ask:
    question = st.text_input("Your question", placeholder="e.g. What are the main risks to cash flow?")
    if question:
        with st.spinner("Thinking..."):
            answer, checked, sources = qa.answer_question(question, prepared["index"], embedder, client)
        st.write(answer)

        pages = qa.check_pages(answer, sources)
        numbers = qa.check_numbers(answer, sources)
        problems = [q for q, ok in checked if not ok] + [p for p, ok in pages if not ok] \
            + [n for n, ok in numbers if not ok]

        if qa.NOT_FOUND in answer.lower():
            st.caption("The AI said the report doesn't cover this.")
        elif problems:
            st.error("Some of this answer couldn't be checked against the report. See below.")
        elif checked:
            st.success("Every quote, page and figure in this answer was found in the report.")

        if not checked and qa.NOT_FOUND not in answer.lower():
            st.warning("No quote from the report, so this answer can't be checked. "
                       "Look at the sources below before trusting it.")
        for quote, ok in checked:
            label = "✅ Found in report: " if ok else "❌ NOT in report, treat with caution: "
            st.write(label + f"\"{quote}\"")
        for page, ok in pages:
            if not ok:
                st.write(f"❌ Cites page {page}, but it wasn't given that page. It may have guessed.")
        for number, ok in numbers:
            if not ok:
                st.write(f"❌ The figure {number} isn't in the sources. It may be made up or worked out.")

        with st.expander("Sources the AI was given"):
            for s in sources:
                st.markdown(f"**Page {s['page']}** ({s['kind']}, score {s['score']})")
                st.text(s["text"])

# ---------------------------------------------------------------- report
with tab_report:
    if "figures" not in st.session_state or "flags" not in st.session_state:
        st.info("Run both 'Financial health' and 'Red flags' first.")
    else:
        company = st.text_input("Company name", value=uploaded.name.rsplit(".", 1)[0])
        note = report.build(company, st.session_state["figures"], st.session_state["ratios"],
                            st.session_state["warnings"], st.session_state["flags"])
        st.download_button("Download screening note (Markdown)", note,
                           file_name=f"{company}_credit_note.md")
        st.markdown(note)