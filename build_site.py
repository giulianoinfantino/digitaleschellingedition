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


def _norm(s: str) -> str:
    return re.sub(r"[*\s.]+", " ", s).strip().upper()


def promote_headings(pages: list[dict], toc_entries: list[dict]):
    """Promote paragraphs that match TOC titles or heading patterns to headings."""
    page_by_book = {}
    for p in pages:
        pb = p.get("page_book")
        if pb is not None:
            page_by_book[pb] = p

    SKIP_WORDS = {"DER", "DIE", "DAS", "DES", "DEM", "DEN", "UND", "ODER",
                   "ALS", "WIE", "VON", "ZUR", "ZUM", "AUS", "AUF", "BEI",
                   "MIT", "FÜR", "BIS", "ÜBER", "NACH", "SEIT", "VOM",
                   "EINE", "EINEM", "EINEN", "EINER", "EINES"}

    toc_words = {}
    for entry in toc_entries:
        target = entry.get("page")
        if target is None:
            continue
        words = [w for w in _norm(entry["title"]).split()
                 if len(w) > 2 and w not in SKIP_WORDS]
        if len(words) >= 2:
            toc_words[target] = words

    for target, words in toc_words.items():
        threshold = len(words) if len(words) <= 3 else max(3, int(len(words) * 0.6 + 0.99))
        promoted = False
        for delta in range(-1, 6):
            if promoted:
                break
            pg = page_by_book.get(target + delta)
            if not pg:
                continue
            paras = pg.get("paragraphs", [])
            for i, para in enumerate(paras):
                if para.get("kind") != "paragraph":
                    continue
                text = para["text"]
                clean = re.sub(r"\*", "", text).strip()
                if len(clean) > 120 or len(clean) < 3:
                    continue
                if re.search(r"\[?Anmerkung des Herausgeber", clean):
                    continue
                # Never start matching from a lowercase paragraph (sentence continuation)
                if clean[0].islower():
                    continue
                normed = _norm(text)
                matched = sum(1 for w in words if w in normed)
                if matched >= threshold:
                    para["kind"] = "heading"
                    promoted = True
                    break
                # Try combining consecutive short paragraphs
                combined = normed
                run = [i]
                found_run = False
                for j in range(i + 1, min(i + 6, len(paras))):
                    nxt = paras[j]
                    if nxt.get("kind") != "paragraph":
                        break
                    nxt_clean = re.sub(r"\*", "", nxt["text"]).strip()
                    if len(nxt_clean) > 120:
                        break
                    if re.search(r"\[?Anmerkung des Herausgeber", nxt_clean):
                        break
                    combined += " " + _norm(nxt["text"])
                    run.append(j)
                    m = sum(1 for w in words if w in combined)
                    if m >= threshold and len(run) >= 2:
                        found_run = True
                if found_run:
                    for idx in run:
                        paras[idx]["kind"] = "heading"
                    promoted = True
                    break

    # Structural pass: on TOC target pages, short paragraphs at the top
    # (before body text) are title-page headings even if words don't match
    toc_target_pages = set()
    for entry in toc_entries:
        target = entry.get("page")
        if target is not None:
            for delta in range(-2, 6):
                toc_target_pages.add(target + delta)

    for pb in toc_target_pages:
        pg = page_by_book.get(pb)
        if not pg:
            continue
        paras = pg.get("paragraphs", [])
        # Pass A: promote short paragraphs at the top (before first body text)
        prev_was_heading = False
        for i, para in enumerate(paras):
            if para.get("kind") == "footnote":
                continue
            if para.get("kind") in ("heading", "subheading"):
                prev_was_heading = True
                continue
            clean = re.sub(r"\*", "", para.get("text", "")).strip()
            if len(clean) > 80:
                break
            if len(clean) < 2:
                continue
            if re.search(r"\[?Anmerkung des Herausgeber", clean):
                continue
            if clean[0].islower():
                if prev_was_heading:
                    para["kind"] = "heading"
                else:
                    break
                continue
            para["kind"] = "heading"
            prev_was_heading = True
        # Pass B: find title blocks mid-page (2+ consecutive short paragraphs
        # starting with uppercase, after body text)
        i = 0
        while i < len(paras):
            para = paras[i]
            if para.get("kind") != "paragraph":
                i += 1
                continue
            clean = re.sub(r"\*", "", para.get("text", "")).strip()
            if len(clean) > 80 or len(clean) < 2 or not clean[0].isupper():
                i += 1
                continue
            if re.search(r"\[?Anmerkung des Herausgeber", clean):
                i += 1
                continue
            # Found a short uppercase paragraph — check if it starts a cluster
            cluster = [i]
            for j in range(i + 1, min(i + 6, len(paras))):
                nxt = paras[j]
                if nxt.get("kind") == "footnote":
                    cluster.append(j)
                    continue
                if nxt.get("kind") in ("heading", "subheading"):
                    break
                nxt_clean = re.sub(r"\*", "", nxt.get("text", "")).strip()
                if len(nxt_clean) > 80:
                    break
                if len(nxt_clean) < 2:
                    cluster.append(j)
                    continue
                cluster.append(j)
            # Only promote if cluster has 2+ short paragraphs (not footnotes)
            para_indices = [k for k in cluster
                           if paras[k].get("kind") == "paragraph"
                           and len(re.sub(r"\*", "", paras[k].get("text", "")).strip()) <= 80
                           and len(re.sub(r"\*", "", paras[k].get("text", "")).strip()) >= 2]
            if len(para_indices) >= 2:
                for k in para_indices:
                    pk = paras[k]
                    pk_clean = re.sub(r"\*", "", pk.get("text", "")).strip()
                    if re.search(r"\[?Anmerkung des Herausgeber", pk_clean):
                        continue
                    pk["kind"] = "heading"
            i = cluster[-1] + 1 if cluster else i + 1

    # First-body-page pass: promote short paragraphs at the very start of each
    # volume (band titles like "*Philosophie der Offenbarung*")
    body_pages = [p for p in pages if p.get("page_kind") == "body"
                  and p.get("page_book") is not None]
    first_body = min(body_pages, key=lambda p: p["page_book"]) if body_pages else None
    if first_body and first_body.get("page_book") not in toc_target_pages:
        for para in first_body.get("paragraphs", []):
            if para.get("kind") == "footnote":
                continue
            if para.get("kind") in ("heading", "subheading"):
                continue
            clean = re.sub(r"\*", "", para.get("text", "")).strip()
            if len(clean) > 80:
                break
            if len(clean) < 2:
                continue
            para["kind"] = "heading"

    for p in pages:
        for para in p.get("paragraphs", []):
            if para.get("kind") != "paragraph":
                continue
            text = para["text"].strip()
            clean = re.sub(r"\*", "", text)
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

    # Load authoritative TOC early so we can use it for heading promotion
    toc_file = Path(__file__).parent / "toc" / f"{work_id}.json"
    if toc_file.exists():
        raw_toc = json.loads(toc_file.read_text(encoding="utf-8"))
    else:
        raw_toc = []

    promote_headings(pages, raw_toc)

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

    # Snap TOC page numbers to the nearest existing page_book value,
    # since the PDF extraction has gaps in page numbering.
    existing_pages = sorted(set(
        p["page_book"] for p in web_pages
        if p.get("page_book") is not None and p["page_kind"] == "body"
    ))

    # Build index of actual heading positions for TOC snapping
    heading_positions = {}
    for p in web_pages:
        pb = p.get("page_book")
        if pb is None or p["page_kind"] != "body":
            continue
        for u in p["units"]:
            if u["type"] == "heading":
                norm_h = _norm(u["text"])
                heading_positions[norm_h] = pb

    toc = []
    vorlesung_re = re.compile(
        r"^(.+?Vorlesung)\.\s+.+", re.DOTALL
    )
    for entry in raw_toc:
        title = entry["title"]
        # Truncate Vorlesung entries to just "N-te Vorlesung"
        vm = vorlesung_re.match(title)
        if vm:
            title = vm.group(1)
        # Try to find actual heading position in text
        norm_title = _norm(title)
        actual_page = heading_positions.get(norm_title)
        if actual_page is not None:
            toc.append({"title": title, "page": actual_page})
        else:
            target = entry.get("page")
            if target is not None and existing_pages:
                best = min(existing_pages, key=lambda p: (abs(p - target), p < target))
                toc.append({"title": title, "page": best})
            else:
                toc.append({"title": title, "page": entry.get("page")})

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
        "text": re.sub(r"\*", "", text),
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
