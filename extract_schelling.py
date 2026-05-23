#!/usr/bin/env python3
"""
Extract Schelling's Sämmtliche Werke from the Total Verlag PDF into
per-page JSON files, organized by Abteilung/Band (sw-I-01 … sw-II-04).

Uses pymupdf block-level extraction for proper paragraph separation
and span-level font info for italic (= Sperrsatz) markup.
"""

import fitz
import json
import re
from pathlib import Path

PDF_PATH = Path(__file__).parent / "schelling_werke.pdf"
OUT_ROOT = Path(__file__).parent / "ocr"

VOLUMES = [
    (1,  1,    9),
    (1,  2,  306),
    (1,  3,  653),
    (1,  4, 1050),
    (1,  5, 1400),
    (1,  6, 1827),
    (1,  7, 2157),
    (1,  8, 2487),
    (1,  9, 2752),
    (1, 10, 3039),
    (2,  1, 3297),
    (2,  2, 3642),
    (2,  3, 4038),
    (2,  4, 4347),
]

HEADER_RE = re.compile(
    r"E\.?\s*Hahn.*CD-ROM\s+Schelling\s+Werke.*TOTAL\s+VERLAG.*1997"
)
PAGE_MARKER_RE = re.compile(r"^\[?(I{1,2}),(\d+),(\d+|[IVXLC]+)\]?$")
INLINE_MARKER_RE = re.compile(r"\s*\|\s*\[S\.\d+\]")
INLINE_ABT_MARKER_RE = re.compile(r"\[I{1,2},\d+,\d+\]")


def roman_to_int(s: str) -> int | None:
    rom = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    try:
        total = 0
        for i, c in enumerate(s):
            val = rom[c]
            if i + 1 < len(s) and rom[s[i + 1]] > val:
                total -= val
            else:
                total += val
        return total
    except KeyError:
        return None


def work_id(abt: int, band: int) -> str:
    return f"sw-{'I' * abt}-{band:02d}"


def get_volume_end(vol_idx: int) -> int:
    if vol_idx + 1 < len(VOLUMES):
        return VOLUMES[vol_idx + 1][2]
    return 4557


def block_to_text_with_emphasis(block: dict) -> str:
    """Build text from a block, wrapping italic spans in *asterisks*."""
    parts = []
    for line in block["lines"]:
        line_parts = []
        for span in line["spans"]:
            text = span["text"]
            if not text.strip():
                line_parts.append(text)
                continue
            is_italic = bool(span["flags"] & 2)
            is_bold = bool(span["flags"] & 16)
            size = span["size"]
            # Skip the Total Verlag header
            if is_bold and size <= 10 and "Hahn" in text:
                return ""
            if is_italic and size >= 11:
                line_parts.append(f"*{text}*")
            else:
                line_parts.append(text)
        parts.append("".join(line_parts))
    text = " ".join(parts)
    # Clean up emphasis markers: collapse adjacent *end**start* → continuous
    text = re.sub(r"\*\s*\*", " ", text)
    # Fix Sperrsatz spacing artifacts: "*Monotheismu s.*" → "*Monotheismus.*"
    # When a word inside emphasis has a stray space before the last 1-2 chars
    text = re.sub(r"\*([^*]+)\s+([a-zäöüß]{1,2})\.\*", r"*\1\2.*", text)
    text = re.sub(r"\*([^*]+)\s+([a-zäöüß]{1,2})\*", r"*\1\2*", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_footnote_block(block: dict) -> bool:
    """Detect footnote blocks by font size (10pt vs 12pt body text)."""
    sizes = []
    for line in block["lines"]:
        for span in line["spans"]:
            if span["text"].strip():
                sizes.append(span["size"])
    if not sizes:
        return False
    avg_size = sum(sizes) / len(sizes)
    return avg_size <= 10.5


def is_page_marker_block(block: dict) -> tuple[bool, int | None, str | None]:
    """Check if block is a standalone page marker like I,1,155."""
    text = ""
    for line in block["lines"]:
        for span in line["spans"]:
            text += span["text"]
    text = text.strip()
    m = PAGE_MARKER_RE.match(text)
    if m:
        abt_str, band_str, page_str = m.group(1), m.group(2), m.group(3)
        abt_len = len(abt_str)
        band_num = int(band_str)
        if page_str.isdigit():
            return True, int(page_str), f"{abt_str},{band_str},{page_str}"
        else:
            return True, roman_to_int(page_str), f"{abt_str},{band_str},{page_str}"
    return False, None, None


def is_pdf_page_number(block: dict, page_height: float) -> bool:
    """Check if block is just the PDF page number at the bottom."""
    text = ""
    for line in block["lines"]:
        for span in line["spans"]:
            text += span["text"]
    text = text.strip()
    if re.fullmatch(r"\d{1,4}", text) and block["bbox"][1] > page_height * 0.9:
        return True
    return False


def is_header_block(block: dict) -> bool:
    text = ""
    for line in block["lines"]:
        for span in line["spans"]:
            text += span["text"]
    return bool(HEADER_RE.search(text))


def classify_block_kind(text: str) -> tuple[str, int | None]:
    """Classify a paragraph's kind based on its text content."""
    if not text:
        return "paragraph", None

    clean = re.sub(r"\*", "", text)

    if re.fullmatch(r"§\.\s*[IVXLC\d]+\.?", clean):
        return "subheading", None

    if clean.isupper() and len(clean) < 150:
        # Exclude formula-like patterns (sequences of single letters/symbols)
        tokens = clean.split()
        single_chars = sum(1 for t in tokens if len(t) <= 2)
        if len(tokens) >= 2 and single_chars / len(tokens) > 0.6:
            return "paragraph", None
        return "heading", None

    heading_patterns = [
        r"^(Erste[rs]?|Zweite[rs]?|Dritte[rs]?|Vierte[rs]?|Fünfte[rs]?|Sechste[rs]?|Siebente[rs]?|Achte[rs]?|Neunte[rs]?|Zehnte[rs]?)\s+(Buch|Kapitel|Abschnitt|Theil|Abtheilung|Vorlesung)",
        r"^(Erster|Zweiter|Dritter|Vierter|Fünfter|Sechster|Siebenter|Achter|Neunter|Zehnter)\s+Band",
        r"^Vorwort\b",
        r"^Vorrede\b",
        r"^Einleitung\b",
        r"^Vorbemerkung",
    ]
    if len(clean) < 150:
        for pat in heading_patterns:
            if re.match(pat, clean):
                return "heading", None

    return "paragraph", None


def classify_page_kind(paragraphs: list[dict], all_text: str) -> str:
    lower = all_text.lower()
    if not all_text.strip():
        return "blank"
    if "sämmtliche werke" in lower and len(paragraphs) <= 8:
        return "title_page"
    if any(p["text"].lower().startswith("vorwort") or p["text"].lower().startswith("vorrede") for p in paragraphs[:3]):
        if len(paragraphs) < 5:
            return "frontmatter"
    if any("inhaltsverzeichnis" in p["text"].lower() or p["text"].strip().lower() == "inhalt" for p in paragraphs[:3]):
        return "toc"
    # Check all paragraphs for standalone Inhalt/Uebersicht headings
    for p in paragraphs:
        pt = re.sub(r"\*", "", p["text"]).strip().lower()
        if pt in ("inhalt", "inhalt.", "inhaltsverzeichniß", "inhaltsverzeichniß.",
                   "inhaltsverzeichnis", "inhaltsverzeichnis.",
                   "inhalts-uebersicht", "inhalts-uebersicht.",
                   "inhaltsübersicht", "inhaltsübersicht.",
                   "uebersicht", "uebersicht."):
            return "toc"
    # Dotted leader lines (e.g. "Vorrede ....................... 1")
    dots = len(re.findall(r"\.{4,}", all_text))
    if dots >= 3:
        return "toc"
    # Dense "S. NNN" page references (lecture listings in Abt. II)
    s_refs = len(re.findall(r"S\.\s*\d+", all_text))
    if s_refs >= 8:
        return "toc"
    return "body"


def extract_page(doc: fitz.Document, pdf_idx: int, abt: int, band: int) -> dict:
    page = doc[pdf_idx]
    page_height = page.rect.height
    data = page.get_text("dict")
    blocks = data["blocks"]

    page_book = None
    paragraphs = []
    has_footnotes = False
    all_texts = []

    for block in blocks:
        if block["type"] != 0:
            continue

        if is_header_block(block):
            continue

        if is_pdf_page_number(block, page_height):
            continue

        is_marker, marker_page, marker_str = is_page_marker_block(block)
        if is_marker:
            if page_book is None:
                page_book = marker_page
            continue

        is_fn = is_footnote_block(block)
        if is_fn:
            has_footnotes = True

        text = block_to_text_with_emphasis(block)
        if not text:
            continue

        # Clean inline page markers
        text = INLINE_MARKER_RE.sub("", text)
        text = INLINE_ABT_MARKER_RE.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            continue

        all_texts.append(text)

        if is_fn:
            paragraphs.append({"kind": "footnote", "text": text, "level": None})
        else:
            kind, level = classify_block_kind(text)
            if kind in ("heading", "subheading"):
                # Strip trailing footnote markers stuck to words
                text = re.sub(r"([a-zäöüß])[0-9](\.\s*)$", r"\1\2", text)
            paragraphs.append({"kind": kind, "text": text, "level": level})

    full_text = " ".join(all_texts)
    page_kind = classify_page_kind(paragraphs, full_text)

    toc_entries = []
    if page_kind == "toc":
        for p in paragraphs:
            for m in re.finditer(r"(.+?)\s+\.{2,}\s*(\d+)", p["text"]):
                toc_entries.append({"title": m.group(1).strip(), "page": int(m.group(2))})

    return {
        "page_pdf": pdf_idx + 1,
        "page_book": page_book,
        "page_kind": page_kind,
        "running_header": None,
        "paragraphs": paragraphs,
        "toc_entries": toc_entries,
        "has_footnote_apparatus": has_footnotes,
        "notes": None,
    }


def main():
    doc = fitz.open(str(PDF_PATH))
    print(f"Opened PDF: {len(doc)} pages")

    total_written = 0

    for vol_idx, (abt, band, start) in enumerate(VOLUMES):
        end = get_volume_end(vol_idx)
        wid = work_id(abt, band)
        out_dir = OUT_ROOT / wid
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"Processing {wid}: Abt. {'I'*abt}, Band {band}")
        print(f"  PDF pages {start+1}–{end} ({end - start} pages)")

        for pdf_idx in range(start, end):
            page_data = extract_page(doc, pdf_idx, abt, band)
            page_num = pdf_idx - start + 1
            out_file = out_dir / f"page_{page_num:04d}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(page_data, f, ensure_ascii=False, indent=2)
            total_written += 1

            if (pdf_idx - start) % 50 == 0:
                print(f"  page {page_num}/{end - start} (PDF {pdf_idx+1})", end="\r")

        print(f"  ✓ {end - start} pages written to {out_dir}")

    intro_dir = OUT_ROOT / "sw-intro"
    intro_dir.mkdir(parents=True, exist_ok=True)
    for pdf_idx in range(0, 9):
        page_data = extract_page(doc, pdf_idx, 0, 0)
        page_data["page_kind"] = "frontmatter"
        out_file = intro_dir / f"page_{pdf_idx+1:04d}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(page_data, f, ensure_ascii=False, indent=2)
        total_written += 1

    doc.close()
    print(f"\n{'='*60}")
    print(f"Done. {total_written} JSON files written to {OUT_ROOT}")


if __name__ == "__main__":
    main()
