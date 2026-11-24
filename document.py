import functools
import re

import pymupdf

import config

IMAGE_TYPES = ("png", "jpg", "jpeg")

# main statement headings - figures should come from these pages, not the notes
STATEMENT_HEADING = re.compile(
    r"(income statement|profit and loss|statement of financial position|balance sheet|cash flows?)", re.I)


@functools.lru_cache(maxsize=1)
def ocr_engine():
    # slow to load, only do it once (and only if a scan actually comes in)
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def ocr_words(page):
    # returns words in the same shape as page.get_text("words"), plus confidence at the end
    picture = page.get_pixmap(dpi=config.OCR_DPI)
    result, _ = ocr_engine()(picture.tobytes("png"),
                             box_thresh=config.OCR_BOX_THRESHOLD,
                             unclip_ratio=config.OCR_UNCLIP)

    # pixels -> PDF points
    scale = 72 / config.OCR_DPI

    words = []
    for box, text, confidence in result or []:
        xs = [corner[0] for corner in box]
        ys = [corner[1] for corner in box]
        words.append((min(xs) * scale, min(ys) * scale, max(xs) * scale, max(ys) * scale,
                      text, float(confidence)))
    return words


def page_words(page):
    words = page.get_text("words")
    real_chars = sum(len(w[4]) for w in words)
    if real_chars >= config.MIN_TEXT_CHARS or not config.OCR_ENABLED:
        return words, False
    return ocr_words(page), True


def group_rows(words, tolerance=3):
    # group words by height so table rows stay together
    # (get_text() often reads tables column by column)
    words = sorted(words, key=lambda w: (round(w[1]), w[0]))

    rows = []
    row = []
    row_y = None
    for w in words:
        y = w[1]
        if row_y is None or abs(y - row_y) <= tolerance:
            row.append(w)
            if row_y is None:
                row_y = y
        else:
            rows.append(row)
            row = [w]
            row_y = y
    if row:
        rows.append(row)
    return rows


def row_text(row):
    # big gap = new column, marked with ' | '
    row = sorted(row, key=lambda w: w[0])
    text = row[0][4]
    for left, word in zip(row, row[1:]):
        gap = word[0] - left[2]
        text += (" | " if gap > config.COLUMN_GAP else " ") + word[4]
    return text


def page_lines(page):
    lines = page.get_text("text").splitlines()
    return [" ".join(line.split()) for line in lines if line.strip()]


def to_pdf_bytes(file_bytes, file_name):
    # photos -> 1 page pdf
    extension = file_name.rsplit(".", 1)[-1].lower()
    if extension in IMAGE_TYPES:
        return pymupdf.open(stream=file_bytes, filetype=extension).convert_to_pdf()
    return file_bytes


def read_pdf(file_bytes, file_name="report.pdf"):
    doc = pymupdf.open(stream=to_pdf_bytes(file_bytes, file_name), filetype="pdf")
    pages = []
    empty_pages = []

    for number, page in enumerate(doc, start=1):
        words, used_ocr = page_words(page)
        if not words:
            empty_pages.append(number)
            continue

        rows = [row_text(r) for r in group_rows(words)]

        # rows work better for tables, lines for normal paragraphs. keep both
        if used_ocr:
            lines = [r.replace(" | ", " ") for r in rows]
        else:
            lines = page_lines(page)

        confidence = None
        if used_ocr:
            confidence = round(sum(w[5] for w in words) / len(words), 2)

        # only check the top of the page. consolidated = group, not parent company
        top = " ".join(lines[:4])
        is_statement = bool(STATEMENT_HEADING.search(top))
        pages.append({"page": number, "lines": lines, "rows": rows,
                      "ocr": used_ocr, "confidence": confidence,
                      "statement": is_statement and "consolidated" in top.lower()})

    # smaller companies don't say "consolidated"
    if not any(p["statement"] for p in pages):
        for p in pages:
            p["statement"] = bool(STATEMENT_HEADING.search(" ".join(p["lines"][:4])))

    return pages, empty_pages


def make_chunks(pages, size=config.CHUNK_LINES, overlap=config.OVERLAP_LINES):
    chunks = []
    step = size - overlap

    for p in pages:
        for kind in ("lines", "rows"):
            items = p[kind]
            start = 0
            while start < len(items):
                window = items[start:start + size]
                chunks.append({"page": p["page"], "kind": kind, "ocr": p["ocr"],
                               "statement": p.get("statement", False), "text": "\n".join(window)})
                if start + size >= len(items):
                    break
                start += step

    return chunks
