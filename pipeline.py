# shared by app.py and evaluate.py
import document
import extract
import flags
import ratios
import search


def prepare(file_bytes, embedder, file_name="report.pdf"):
    pages, empty_pages = document.read_pdf(file_bytes, file_name)
    chunks = document.make_chunks(pages)
    index = search.build_index(chunks, embedder)
    return {"pages": pages, "empty_pages": empty_pages, "chunks": chunks, "index": index}


def analyse(prepared, embedder, client):
    figures = extract.extract_all(prepared["index"], embedder, client)
    return {
        "figures": figures,
        "ratios": ratios.compute(figures),
        "warnings": ratios.sanity_warnings(figures),
        "flags": flags.scan_all(prepared["index"], embedder, client),
    }
