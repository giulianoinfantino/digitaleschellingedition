#!/usr/bin/env python3
"""
Parse authoritative TOC from the Inhaltsverzeichnis pages of each volume
in the Schelling Sämmtliche Werke PDF.

Produces toc/<volume_id>.json — the definitive table of contents used by
build_site.py, replacing heuristic heading detection.
"""

import fitz
import json
import re
from pathlib import Path

PDF_PATH = Path(__file__).parent / "schelling_werke.pdf"
OCR_ROOT = Path(__file__).parent / "ocr"
TOC_OUT = Path(__file__).parent / "toc"


def get_toc_pdf_pages(vol_id: str) -> list[int]:
    vol_dir = OCR_ROOT / vol_id
    pages = []
    for f in sorted(vol_dir.glob("page_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("page_kind") == "toc":
            pages.append(data["page_pdf"])
    return pages


def clean_title(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    for prefix in ["Inhaltsverzeichniß", "Inhaltsübersicht", "Inhalts-Uebersicht", "Inhalt"]:
        t = re.sub(rf"^{re.escape(prefix)}\.?\s*", "", t)
    t = re.sub(r"^[\.\s,]+", "", t)
    t = re.sub(r"^Seite\s+", "", t)
    t = re.sub(r"^\d+[\.\)]\s+", "", t)
    t = re.sub(r"\[?I{1,2},\d+,\d+\]?\s*", "", t)
    t = t.strip(". ")
    return t


def parse_dotted_leader_toc(text: str) -> list[dict]:
    entries = []
    lines = [l for l in text.split("\n") if not l.startswith("E.Hahn:")]
    current = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Sub-entry listings without page numbers AND without continuation
        # (bare "a) Title" / "b) Title" lines in sw-I-05 style)
        # Only skip if the line ends with a period (complete sentence) and has no dots
        if re.match(r"^[a-g]\)\s", line) and "..." not in line and line.endswith("."):
            current = ""
            continue

        m = re.match(r"^(.+?)\s*\.{3,}\s*(\d+)\s*$", line)
        if m:
            title_part = m.group(1).strip()
            if current:
                title_part = current + " " + title_part
            current = ""
            t = clean_title(title_part)
            if t:
                entries.append({"title": t, "page": int(m.group(2))})
            continue

        m2 = re.match(r"^(.+?)\s{3,}(\d+)\s*$", line)
        if m2:
            title_part = m2.group(1).strip()
            if current:
                title_part = current + " " + title_part
            current = ""
            t = clean_title(title_part)
            if t:
                entries.append({"title": t, "page": int(m2.group(2))})
            continue

        if re.search(r"\.{3,}\s*$", line):
            c = re.sub(r"\.{3,}\s*$", "", line).strip()
            current = (current + " " + c).strip() if current else c
            continue

        if len(line) > 2:
            current = (current + " " + line).strip() if current else line

    return entries


VORLESUNG_NAMES = (
    "Erste|Zweite|Dritte|Vierte|Fünfte|Sechste|Siebente|Achte|Neunte|Zehnte|"
    "Eilfte|Zwölfte|Dreizehnte|Vierzehnte|Fünfzehnte|Sechzehnte|Siebzehnte|"
    "Achtzehnte|Neunzehnte|Zwanzigste|Einundzwanzigste|Zweiundzwanzigste|"
    "Dreiundzwanzigste|Vierundzwanzigste|Fünfundzwanzigste|Sechsundzwanzigste|"
    "Siebenundzwanzigste|Achtundzwanzigste|Neunundzwanzigste|Dreißigste|"
    "Einunddreißigste|Zweiunddreißigste|Dreiunddreißigste|Vierunddreißigste|"
    "Fünfunddreißigste|Sechsunddreißigste|Siebenunddreißigste|"
    "Achtunddreißigste|Neununddreißigste|Vierzigste"
)


def parse_vorlesung_toc(text: str) -> list[dict]:
    entries = []
    pattern = re.compile(
        rf"({VORLESUNG_NAMES})\s+Vorlesung\.\s+(.+?)(?:,\s*)?S\.\s*(\d+)\.",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        vorlesung = m.group(1).strip() + " Vorlesung"
        topic = re.sub(r"\s+", " ", m.group(2).strip()).rstrip(",. ")
        page = int(m.group(3))
        entries.append({"title": f"{vorlesung}. {topic}", "page": page})
    return entries


def is_overview_toc_page(text: str) -> bool:
    """Check if a page is the volume-level overview TOC (has dotted leaders
    and starts with 'Seite' or 'Inhaltsverzeichniß')."""
    dots = len(re.findall(r"\.{5,}", text))
    has_seite = bool(re.search(r"(?:^|\n)\s*Seite\s*$", text, re.MULTILINE))
    has_marker = any(m in text for m in ["Inhaltsverzeichniß", "Inhaltsübersicht"])
    return dots >= 2 and (has_seite or has_marker)


def find_overview_page(doc, toc_pdf_pages: list[int]) -> int | None:
    """Find the main overview TOC page among all TOC pages of a volume."""
    for pdf_page in toc_pdf_pages:
        text = doc[pdf_page - 1].get_text("text")
        if is_overview_toc_page(text):
            return pdf_page
    return None


def build_abt1_toc(doc, vol_id: str) -> list[dict]:
    toc_pdf_pages = get_toc_pdf_pages(vol_id)
    if not toc_pdf_pages:
        return []

    overview_page = find_overview_page(doc, toc_pdf_pages)
    if overview_page is None:
        return []

    text = doc[overview_page - 1].get_text("text")
    for marker in ["Inhaltsverzeichniß", "Inhaltsübersicht", "Inhalt.", "Inhalt\n", "Seite\n"]:
        pos = text.find(marker)
        if pos >= 0:
            text = text[pos:]
            break

    entries = parse_dotted_leader_toc(text)

    # Filter noise: skip entries that look like body text remnants
    clean = []
    for e in entries:
        if len(e["title"]) < 3:
            continue
        if e["title"].startswith("Schließlich"):
            continue
        clean.append(e)

    return clean


def build_abt2_toc(doc, vol_id: str) -> list[dict]:
    toc_pdf_pages = get_toc_pdf_pages(vol_id)
    if not toc_pdf_pages:
        return []

    all_text = ""
    for pdf_page in toc_pdf_pages:
        all_text += doc[pdf_page - 1].get_text("text") + "\n"

    for marker in ["Inhaltsübersicht", "Inhalts-Uebersicht", "Inhalt."]:
        pos = all_text.find(marker)
        if pos >= 0:
            all_text = all_text[pos:]
            break

    return parse_vorlesung_toc(all_text)


def main():
    doc = fitz.open(str(PDF_PATH))
    TOC_OUT.mkdir(exist_ok=True)

    volumes = [
        "sw-I-01", "sw-I-02", "sw-I-03", "sw-I-04", "sw-I-05",
        "sw-I-06", "sw-I-07", "sw-I-08", "sw-I-09", "sw-I-10",
        "sw-II-01", "sw-II-02", "sw-II-03", "sw-II-04",
    ]

    total = 0
    for vol_id in volumes:
        if vol_id.startswith("sw-II"):
            entries = build_abt2_toc(doc, vol_id)
        else:
            entries = build_abt1_toc(doc, vol_id)

        out_file = TOC_OUT / f"{vol_id}.json"
        out_file.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total += len(entries)
        print(f"{vol_id}: {len(entries)} entries")
        for e in entries:
            pg = f"S.{e['page']:>4}" if e["page"] else "     "
            print(f"  {pg}: {e['title'][:100]}")
        print()

    doc.close()
    print(f"Total: {total} TOC entries across {len(volumes)} volumes.")


if __name__ == "__main__":
    main()
