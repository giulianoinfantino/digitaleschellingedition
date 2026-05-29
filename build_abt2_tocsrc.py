#!/usr/bin/env python3
"""
Derive hierarchical toc_src/sw-II-*.json from the legacy flat toc/sw-II-*.json.

Abteilung II (Mythologie / Offenbarung) is a lecture course. The printed
Uebersicht is discursive prose, but it consistently opens each entry with
"<Ordinal> Vorlesung. <lead topic> …" and embeds numbered sub-points "1) … 2) …".
We promote each lecture to a level-1 head (ordinal label + concise lead title +
start page) and lift its numbered sub-points to level-2 children (with the page
that follows them, when present). Scan-only structure that the legacy parse
missed — Buch dividers, an omitted lecture, appended works — is supplied by
PATCHES below (hand-read from toc_src/png/sw-II-*).

Output matches the Abt. I toc_src schema so build_toc.py treats both alike.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
# Original flat Abt. II TOCs (snapshot from git, before build_toc.py rewrites
# toc/ from toc_src/). Reading from here keeps this build idempotent.
TOC_LEGACY = ROOT / "abt2_legacy"
TOC_SRC = ROOT / "toc_src"
OCR_ROOT = ROOT / "ocr"

# A standalone lecture heading in the body text, e.g. "Zweite Vorlesung."
HEADING_LECTURE = re.compile(r"^(\S*(?:te|ste))\s+Vorlesung\.?$", re.UNICODE)


def ocr_lecture_pages(vol_id: str) -> dict:
    """Map each lecture's ordinal word → the printed page_book on which its
    heading actually appears in the body OCR. This is authoritative; the legacy
    Uebersicht page was often the *last* 'S. NN' on the entry line, not the
    lecture's start."""
    pages = {}
    vol_dir = OCR_ROOT / vol_id
    for f in sorted(vol_dir.glob("page_*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        if p.get("page_kind") != "body" or p.get("page_book") is None:
            continue
        for para in p.get("paragraphs", []):
            # Lecture headings are usually kind=heading, but the OCR also leaves
            # some as kind=paragraph (build_site promotes them later). Match on a
            # standalone "<Ordinal> Vorlesung." line regardless of kind; the
            # full-string anchor excludes mid-text cross-references.
            m = HEADING_LECTURE.match(para.get("text", "").strip())
            if m:
                pages.setdefault(m.group(1), p["page_book"])
    return pages

# German ordinals are single compound tokens ("Fünfundzwanzigste"), so the
# ordinal is just the word before "Vorlesung.". Require it to end like an
# ordinal (…te / …ste) to avoid matching stray prose.
VOL_LABEL = re.compile(r"^(\S*(?:te|ste))\s+Vorlesung\.\s*", re.UNICODE)

PAGE_REF = re.compile(r"\.?\s*,?\s*S\.\s*(\d+)\.?")
NUM_SUB = re.compile(r"(?<![\dA-Za-zÄÖÜäöü])(\d{1,2})\)\s*")


# Running headers ("II,4,VII", "II,1,X") sometimes bled into the legacy text.
RUNNING_HDR = re.compile(r"\s*\b[IVX]{1,3},\s*\d+,\s*[IVXLC]+\b\s*")


def strip_stars(s: str) -> str:
    s = s.replace("*", "")
    s = RUNNING_HDR.sub(" ", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def make_lead(rest: str) -> str:
    """Concise lecture title: text up to the first page ref or numbered sub-point."""
    cut = len(rest)
    m_pg = PAGE_REF.search(rest)
    if m_pg:
        cut = min(cut, m_pg.start())
    m_num = NUM_SUB.search(rest)
    if m_num:
        cut = min(cut, m_num.start())
    lead = rest[:cut].strip(" ,;:.—–-")
    if cut == len(rest):  # no break found — trim long prose to first sentence
        ms = re.search(r"\.\s", lead)
        if ms and ms.start() < 140:
            lead = lead[: ms.start()]
        elif len(lead) > 130:
            lead = lead[:130].rsplit(" ", 1)[0] + "…"
    return lead.strip()


def make_subpoints(rest: str, parent_page) -> list[dict]:
    """Lift numbered sub-points '1) … 2) …' to level-2 entries. The page is the
    first 'S. NN' that appears before the next numbered marker (else parent)."""
    subs = []
    marks = list(NUM_SUB.finditer(rest))
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(rest)
        segment = rest[start:end]
        pg_m = PAGE_REF.search(segment)
        page = int(pg_m.group(1)) if pg_m else parent_page
        # title = phrase up to its first page ref, trimmed
        phrase = segment[: pg_m.start()] if pg_m else segment
        phrase = strip_stars(phrase).strip(" ,;:.—–-")
        if len(phrase) > 110:
            phrase = phrase[:110].rsplit(" ", 1)[0] + "…"
        if len(phrase) < 3:
            continue
        subs.append({
            "label": m.group(1),  # bare digit → "1. phrase" like Abt. I
            "title": phrase,
            "kind": "section",
            "level": 2,
            "page": page,
            "ref": None,
        })
    return subs


def convert(vol_id: str) -> list[dict]:
    legacy = json.loads((TOC_LEGACY / f"{vol_id}.json").read_text(encoding="utf-8"))
    ocr_pages = ocr_lecture_pages(vol_id)
    entries = []
    for e in legacy:
        raw = strip_stars(e.get("title", ""))
        page = e.get("page")
        m = VOL_LABEL.match(raw)
        if not m:
            # Non-lecture entry (e.g. appended work) — keep as a level-0 work.
            entries.append({"label": "", "title": raw, "kind": "work",
                            "level": 0, "page": page, "ref": None})
            continue
        ordinal = m.group(1)
        label = m.group(0).strip().rstrip(".")  # "<Ordinal> Vorlesung"
        rest = raw[m.end():]
        subs = make_subpoints(rest, page)
        # Prefer the authoritative page from the body OCR heading. Fall back to
        # the earliest page among the legacy head and its numbered sub-points.
        sub_pages = [s["page"] for s in subs if s["page"] is not None]
        head_page = ocr_pages.get(ordinal)
        if head_page is None:
            head_page = min([page] + sub_pages) if (page is not None and sub_pages) else page
        entries.append({"label": label, "title": make_lead(rest), "kind": "section",
                        "level": 1, "page": head_page, "ref": None})
        entries.extend(subs)
    return entries


# ── Scan-only structure the legacy PDF parse missed ─────────────────────────
# Each patch is applied after conversion. `insert_before_page` puts a divider
# just before the first level-1 lecture at/after that page; `insert` adds a
# lecture the legacy data dropped (positioned by page order).
PATCHES = {
    "sw-II-01": {
        "books": [
            {"title": "Historisch-kritische Einleitung in die Philosophie der Mythologie (Erstes Buch)",
             "page": 1},
            {"title": "Philosophische Einleitung in die Philosophie der Mythologie (Zweites Buch)",
             "page": 257},
        ],
        "missing_lectures": [
            {"label": "Siebzehnte Vorlesung",
             "title": "Fortgang zur Exposition der rationalen Philosophie; das Verhältniß der drei Ursachen (Potenzen) zu einander",
             "page": 386},
        ],
        "appended_works": [
            {"title": "Ueber die Quelle der ewigen Wahrheiten (Abhandlung)", "page": 575},
        ],
    },
    "sw-II-02": {
        "books": [
            {"title": "Der Monotheismus (Erstes Buch)", "page": 1},
            {"title": "Die Mythologie (Zweites Buch)", "page": 135},
        ],
    },
    "sw-II-03": {
        "books": [
            {"title": "Einleitung in die Philosophie der Offenbarung (Erstes Buch)", "page": 1},
            {"title": "Der Philosophie der Offenbarung erster Theil (Zweites Buch)", "page": 177},
        ],
        "missing_lectures": [
            {"label": "Siebente Vorlesung",
             "title": "Ueber das Verhalten des höheren Empirismus und sein Verhältniß zur positiven Philosophie",
             "page": 115},
            {"label": "Neunzehnte Vorlesung",
             "title": "Fortgang zu den Mysterien; die Stellung der Demeter im Moment ihrer Versöhnung",
             "page": 411},
        ],
    },
    "sw-II-04": {
        # The Uebersicht page carrying the book divider and the 24th lecture is
        # not in the scan set, so the lecture sequence here begins at the 25th.
        "appended_works": [
            {"title": "Andere Deduktion der Principien der positiven Philosophie", "page": 335},
            {"title": "Erste Vorlesung in Berlin", "page": 357},
        ],
    },
}


def apply_patches(vol_id: str, entries: list[dict]) -> list[dict]:
    patch = PATCHES.get(vol_id)
    if not patch:
        return entries

    ocr_pages = ocr_lecture_pages(vol_id)

    # Insert missing lectures in page order (prefer the OCR heading page).
    for ml in patch.get("missing_lectures", []):
        page = ocr_pages.get(ml["label"].split()[0], ml["page"])
        new = {"label": ml["label"], "title": ml["title"], "kind": "section",
               "level": 1, "page": page, "ref": None}
        pos = len(entries)
        for i, e in enumerate(entries):
            if (e.get("page") or 0) > page:
                pos = i
                break
        entries.insert(pos, new)

    # Append separate works at their page position.
    for aw in patch.get("appended_works", []):
        new = {"label": "", "title": aw["title"], "kind": "work",
               "level": 0, "page": aw["page"], "ref": None}
        pos = len(entries)
        for i, e in enumerate(entries):
            if (e.get("page") or 0) >= aw["page"] and e.get("level") == 1:
                # place before the first lecture at/after the work's page
                if (e.get("page") or 0) >= aw["page"]:
                    pos = i
                    break
        entries.insert(pos, new)

    # Book dividers (level-0) before the first lecture at/after their page.
    for bk in sorted(patch.get("books", []), key=lambda b: b["page"], reverse=True):
        new = {"label": "", "title": bk["title"], "kind": "work",
               "level": 0, "page": bk["page"], "ref": None}
        pos = 0
        for i, e in enumerate(entries):
            if e.get("level") == 1 and (e.get("page") or 0) >= bk["page"]:
                pos = i
                break
        entries.insert(pos, new)

    return entries


def main():
    src_png = ROOT / "toc_src" / "png"
    for vol_dir in sorted(src_png.glob("sw-II-*")):
        vol_id = vol_dir.name
        legacy_file = TOC_LEGACY / f"{vol_id}.json"
        if not legacy_file.exists():
            print(f"{vol_id}: no legacy toc, skipping")
            continue
        entries = convert(vol_id)
        entries = apply_patches(vol_id, entries)
        pages = sorted(int(p.stem[1:]) for p in vol_dir.glob("p*.png"))
        out = {
            "work_id": vol_id,
            "source_pdf_pages": pages,
            "note": ("Derived from the legacy discursive Uebersicht: each lecture "
                     "promoted to a level-1 head with numbered sub-points lifted to "
                     "level-2; Buch dividers / omitted lectures / appended works "
                     "patched from the printed Uebersicht scans."),
            "entries": entries,
        }
        out_file = TOC_SRC / f"{vol_id}.json"
        out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        n_lec = sum(1 for e in entries if e["level"] == 1)
        n_sub = sum(1 for e in entries if e["level"] == 2)
        n_work = sum(1 for e in entries if e["level"] == 0)
        print(f"{vol_id}: {len(entries)} entries "
              f"({n_work} works/books, {n_lec} lectures, {n_sub} sub-points)")


if __name__ == "__main__":
    main()
