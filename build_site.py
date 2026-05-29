#!/usr/bin/env python3
"""
Build Schelling Edition site data from OCR JSON files.
Produces:
  - assets/edition-data.js   (global metadata + works list)
  - assets/work-sw-*.js      (per-volume page data for the reader)
  - assets/search-data.js    (full-text search index)
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone

OCR_ROOT = Path(__file__).parent / "ocr"
SITE_ROOT = Path(__file__).parent / "digitalehegeledition" / "assets"

VOLUME_META = [
    ("sw-I-01",  "I",  "1",  "SW I.1",  "Jugendschriften (1792–1797)"),
    ("sw-I-02",  "I",  "2",  "SW I.2",  "Naturphilosophie I (1797–1798)"),
    ("sw-I-03",  "I",  "3",  "SW I.3",  "Naturphilosophie II (1799–1800)"),
    ("sw-I-04",  "I",  "4",  "SW I.4",  "Identitätsphilosophie (1800–1802)"),
    ("sw-I-05",  "I",  "5",  "SW I.5",  "Schriften 1802–1803"),
    ("sw-I-06",  "I",  "6",  "SW I.6",  "Philosophie und Religion (1804)"),
    ("sw-I-07",  "I",  "7",  "SW I.7",  "Schriften 1805–1808"),
    ("sw-I-08",  "I",  "8",  "SW I.8",  "Schriften 1811–1815"),
    ("sw-I-09",  "I",  "9",  "SW I.9",  "Schriften 1815–1830"),
    ("sw-I-10", "I", "10",  "SW I.10", "Schriften 1830–1850"),
    ("sw-II-01", "II",  "1",  "SW II.1", "Philosophie der Mythologie I"),
    ("sw-II-02", "II",  "2",  "SW II.2", "Philosophie der Mythologie II"),
    ("sw-II-03", "II",  "3",  "SW II.3", "Philosophie der Offenbarung I"),
    ("sw-II-04", "II",  "4",  "SW II.4", "Philosophie der Offenbarung II"),
]


def load_volume_pages(work_id: str) -> list[dict]:
    vol_dir = OCR_ROOT / work_id
    if not vol_dir.exists():
        return []
    pages = []
    for f in sorted(vol_dir.glob("page_*.json")):
        pages.append(json.loads(f.read_text(encoding="utf-8")))
    return pages


_ORDINALS = (
    r"Erste[rs]?|Zweite[rs]?|Dritte[rs]?|Vierte[rs]?|Fünfte[rs]?|"
    r"Sechste[rs]?|Siebente[rs]?|Achte[rs]?|Neunte[rs]?|Zehnte[rs]?|"
    r"Eilfte[rs]?|Zwölfte[rs]?|Dreizehnte[rs]?|Vierzehnte[rs]?|"
    r"Fünfzehnte[rs]?|Sechzehnte[rs]?|Siebzehnte[rs]?|"
    r"Achtzehnte[rs]?|Neunzehnte[rs]?|Zwanzigste[rs]?|"
    r"Einundzwanzigste[rs]?|Zweiundzwanzigste[rs]?|Dreiundzwanzigste[rs]?|"
    r"Vierundzwanzigste[rs]?|Fünfundzwanzigste[rs]?|Sechsundzwanzigste[rs]?|"
    r"Siebenundzwanzigste[rs]?|Achtundzwanzigste[rs]?|Neunundzwanzigste[rs]?|"
    r"Dreißigste[rs]?|Einunddreißigste[rs]?|Zweiunddreißigste[rs]?|"
    r"Dreiunddreißigste[rs]?|Vierunddreißigste[rs]?|Fünfunddreißigste[rs]?|"
    r"Sechsunddreißigste[rs]?|Siebenunddreißigste[rs]?|"
    r"Achtunddreißigste[rs]?|Neununddreißigste[rs]?|Vierzigste[rs]?"
)

HEADING_PATTERNS = [
    re.compile(rf"^({_ORDINALS})\s+"
               r"(Buch|Kapitel|Abschnitt|Theil|Abtheilung|Vorlesung|Band)", re.I),
    re.compile(r"^Vorwort\b", re.I),
    re.compile(r"^Vorrede\b", re.I),
    re.compile(r"^Einleitung\b", re.I),
    re.compile(r"^Vorbemerkung", re.I),
    re.compile(r"^Anhang\b", re.I),
    re.compile(r"^Nachwort\b", re.I),
    re.compile(r"^Beschluß\b", re.I),
    re.compile(r"^Zusätze?\b", re.I),
    re.compile(r"^\*?Vorrede", re.I),
    re.compile(r"^\*?Einleitung", re.I),
]


def mark_headings(pages: list[dict]):
    """Deterministically promote paragraphs that match structural heading
    patterns (Buch, Kapitel, Abschnitt, Vorrede, Einleitung, Zusatz, §, ...).

    The OCR already marks most headings as kind=heading; this is a safety net
    for any it missed. It performs NO fuzzy / probabilistic matching against the
    TOC — section structure now comes from the hand-verified toc_src data, so
    the old guesswork (which produced false and missing headings) is gone."""
    for p in pages:
        for para in p.get("paragraphs", []):
            if para.get("kind") != "paragraph":
                continue
            clean = re.sub(r"\*", "", para["text"]).strip()
            if len(clean) > 150:
                continue
            for pat in HEADING_PATTERNS:
                if pat.search(clean):
                    para["kind"] = "heading"
                    break


def paragraphs_to_units(paragraphs: list[dict]) -> list[dict]:
    units = []
    for p in paragraphs:
        kind = p.get("kind", "paragraph")
        text = p.get("text", "")
        if kind in ("heading", "subheading"):
            units.append({"type": "heading", "text": text, "level": p.get("level")})
        elif kind == "footnote":
            units.append({"type": "footnote", "text": text})
        else:
            units.append({"type": "paragraph", "text": text})
    return units


def build_work_data(work_id: str, meta_tuple: tuple) -> dict:
    _, abt, band, siglum, title = meta_tuple
    pages = load_volume_pages(work_id)

    # Load the authoritative TOC (toc_src-derived for Abt. I; legacy PDF parse
    # for Abt. II). Abt. I entries additionally carry {level, kind}.
    toc_file = Path(__file__).parent / "toc" / f"{work_id}.json"
    if toc_file.exists():
        raw_toc = json.loads(toc_file.read_text(encoding="utf-8"))
    else:
        raw_toc = []

    mark_headings(pages)

    web_pages = []
    headings_count = 0
    paragraphs_count = 0
    footnotes_count = 0
    pages_body = 0

    for p in pages:
        units = paragraphs_to_units(p.get("paragraphs", []))
        for u in units:
            if u["type"] == "heading":
                headings_count += 1
            elif u["type"] == "footnote":
                footnotes_count += 1
            else:
                paragraphs_count += 1

        page_kind = p.get("page_kind", "body")
        if page_kind == "body":
            pages_body += 1

        web_pages.append({
            "page_pdf": p["page_pdf"],
            "page_book": p.get("page_book"),
            "page_kind": page_kind,
            "sigel": siglum,
            "units": units,
        })

    # Book page numbers are now ~99% complete, so a TOC's printed page almost
    # always has an exact body page_book. Keep exact matches verbatim; only when
    # a page is genuinely missing do we snap to the nearest existing body
    # page_book (preferring at-or-after the target). The reader still refines via
    # heading-text matching within ±5 pages.
    body_book_pages = sorted({
        p["page_book"] for p in web_pages
        if p.get("page_book") is not None and p["page_kind"] == "body"
    })
    body_book_set = set(body_book_pages)

    def snap_page(pg):
        if pg is None or not body_book_pages or pg in body_book_set:
            return pg
        return min(body_book_pages, key=lambda x: (abs(x - pg), x < pg))

    # Build TOC. Abt. I entries carry authoritative {level, kind} from toc_src;
    # legacy entries (Abt. II, no level) keep the "N-te Vorlesung" truncation.
    toc = []
    vorlesung_re = re.compile(r"^(.+?Vorlesung)\.\s+.+", re.DOTALL)
    for entry in raw_toc:
        out = {"title": entry["title"], "page": snap_page(entry.get("page"))}
        if "level" in entry:
            out["level"] = entry["level"]
            out["kind"] = entry.get("kind", "section")
        else:
            vm = vorlesung_re.match(entry["title"])
            if vm:
                out["title"] = vm.group(1)
        toc.append(out)

    return {
        "metadata": {
            "work_id": work_id,
            "series": "SW",
            "band": f"{abt},{band}" if abt == "II" else band,
            "volume_number": band,
            "title": title,
            "short_title": title,
            "source_title": title,
            "siglum": siglum,
            "edition": "Total Verlag 1997 (Sämmtliche Werke 1856–1861)",
            "collection_title": "Digitale Schelling-Edition",
        },
        "toc_printed": toc,
        "pages": web_pages,
        "stats": {
            "pages_total": len(pages),
            "pages_body": pages_body,
            "headings": headings_count,
            "paragraphs": paragraphs_count,
            "footnotes": footnotes_count,
        },
    }


def build_search_entry(work_id: str, page: dict, unit: dict) -> dict | None:
    text = unit.get("text", "").strip()
    if not text or len(text) < 10:
        return None
    label = unit.get("type", "paragraph")
    return {
        "work_id": work_id,
        "page_pdf": page["page_pdf"],
        "page_book": page.get("page_book"),
        "label": label,
        "text": re.sub(r"\*", "", text)[:300],
    }


def main():
    SITE_ROOT.mkdir(parents=True, exist_ok=True)

    all_works = []
    search_index = []
    total_pages = 0
    total_headings = 0
    total_search = 0

    for meta in VOLUME_META:
        work_id = meta[0]
        print(f"Building {work_id}: {meta[4]}...")

        work_data = build_work_data(work_id, meta)
        stats = work_data["stats"]
        total_pages += stats["pages_total"]
        total_headings += stats["headings"]

        # Write work JS file
        work_js = SITE_ROOT / f"work-{work_id}.js"
        work_js.write_text(
            f"window.SCHELLING_WORK_DATA = {json.dumps(work_data, ensure_ascii=False)};",
            encoding="utf-8",
        )
        print(f"  -> {work_js.name} ({stats['pages_total']} pages, {stats['headings']} headings)")

        # Build search entries
        work_search = 0
        for page in work_data["pages"]:
            for unit in page["units"]:
                entry = build_search_entry(work_id, page, unit)
                if entry:
                    search_index.append(entry)
                    work_search += 1
        total_search += work_search

        all_works.append({
            "work_id": work_id,
            "series": "SW",
            "band": work_data["metadata"]["band"],
            "volume_number": meta[3],
            "title": meta[4],
            "short_title": meta[4],
            "siglum": meta[3],
            "stats": {
                "pages_total": stats["pages_total"],
                "pages_body": stats["pages_body"],
                "headings": stats["headings"],
                "paragraphs": stats["paragraphs"],
                "footnotes": stats["footnotes"],
                "search_entries": work_search,
            },
        })

    # Write edition-data.js
    edition = {
        "metadata": {
            "title": "Digitale Schelling-Edition",
            "collection_title": "Friedrich Wilhelm Joseph von Schelling · Sämmtliche Werke",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "works_count": len(all_works),
            "default_work_id": "sw-I-01",
            "stats": {
                "pages_total": total_pages,
                "search_entries": total_search,
                "footnotes": sum(w["stats"]["footnotes"] for w in all_works),
                "headings": total_headings,
            },
        },
        "works": all_works,
    }

    ed_js = SITE_ROOT / "edition-data.js"
    ed_js.write_text(
        f"window.SCHELLING_EDITION = {json.dumps(edition, ensure_ascii=False, indent=2)};",
        encoding="utf-8",
    )
    print(f"\n-> {ed_js.name}")

    # Write search-data.js
    search_js = SITE_ROOT / "search-data.js"
    search_js.write_text(
        f"window.SCHELLING_SEARCH_INDEX = {json.dumps(search_index, ensure_ascii=False)};",
        encoding="utf-8",
    )
    print(f"-> {search_js.name} ({len(search_index)} entries)")

    print(f"\nDone. {total_pages} pages across {len(all_works)} volumes.")


if __name__ == "__main__":
    main()
