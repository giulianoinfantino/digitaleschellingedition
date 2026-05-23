#!/usr/bin/env python3
"""
Fix garbled Greek text in OCR JSON files.

The Total Verlag 1997 PDF stores Greek using ISO 8859-7 code points
but pymupdf reads them as Latin-1. This script detects runs of 3+
consecutive high-byte chars (0xC0–0xFF) and re-decodes them as
ISO 8859-7 → proper Unicode Greek.
"""

import json
import re
from pathlib import Path

OCR_ROOT = Path(__file__).parent / "ocr"

GREEK_RUN = re.compile(r'[\xc0-\xff]{3,}')


def fix_greek_in_text(text: str) -> str:
    def replace_match(m):
        garbled = m.group(0)
        try:
            raw = garbled.encode('latin-1')
            return raw.decode('iso-8859-7')
        except (UnicodeDecodeError, UnicodeEncodeError):
            return garbled
    return GREEK_RUN.sub(replace_match, text)


def fix_volume(vol_dir: Path) -> tuple[int, int]:
    pages_fixed = 0
    sequences_fixed = 0

    for f in sorted(vol_dir.glob("page_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        changed = False

        for p in data.get("paragraphs", []):
            old = p.get("text", "")
            new = fix_greek_in_text(old)
            if new != old:
                p["text"] = new
                sequences_fixed += len(GREEK_RUN.findall(old))
                changed = True

        if data.get("running_header"):
            old_rh = data["running_header"]
            new_rh = fix_greek_in_text(old_rh)
            if new_rh != old_rh:
                data["running_header"] = new_rh
                changed = True

        if changed:
            pages_fixed += 1
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return pages_fixed, sequences_fixed


def main():
    total_pages = 0
    total_seqs = 0

    volumes = sorted(OCR_ROOT.iterdir())
    for vol_dir in volumes:
        if not vol_dir.is_dir() or not vol_dir.name.startswith("sw-"):
            continue
        pages, seqs = fix_volume(vol_dir)
        if pages:
            print(f"  {vol_dir.name}: {pages} pages, {seqs} sequences fixed")
        total_pages += pages
        total_seqs += seqs

    print(f"\nFixed {total_seqs} Greek sequences across {total_pages} pages.")


if __name__ == "__main__":
    main()
