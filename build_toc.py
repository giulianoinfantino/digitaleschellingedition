#!/usr/bin/env python3
"""
Assemble the authoritative TOC for each volume from the hand-verified
structured sources in toc_src/<volume_id>.json (produced by careful OCR of
the printed Inhalt/Uebersicht pages).

Emits toc/<volume_id>.json — a flat, ordered list consumed by build_site.py.
Each emitted entry is backward-compatible ({title, page}) and additionally
carries {level, kind, label} so the reader can render a hierarchical TOC.

Volumes without a toc_src file (e.g. Abteilung II, sw-intro) are left
untouched: their existing toc/<volume_id>.json is not modified.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent
TOC_SRC = ROOT / "toc_src"
TOC_OUT = ROOT / "toc"


def compose_title(entry: dict) -> str:
    """Build the display title from the structural label and the topic."""
    label = (entry.get("label") or "").strip()
    title = (entry.get("title") or "").strip()
    if label and title:
        return f"{label}. {title}"
    return label or title


def build_volume(src_file: Path) -> list[dict]:
    data = json.loads(src_file.read_text(encoding="utf-8"))
    out = []
    for e in data.get("entries", []):
        title = compose_title(e)
        if not title:
            continue
        out.append({
            "title": title,
            "page": e.get("page"),
            "level": e.get("level", 0),
            "kind": e.get("kind", "section"),
            "label": (e.get("label") or "").strip(),
        })
    return out


def main():
    TOC_OUT.mkdir(exist_ok=True)
    src_files = sorted(TOC_SRC.glob("sw-*.json"))
    if not src_files:
        print("No toc_src files found.")
        return

    total = 0
    for src in src_files:
        vol_id = src.stem
        entries = build_volume(src)
        out_file = TOC_OUT / f"{vol_id}.json"
        out_file.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total += len(entries)
        works = sum(1 for e in entries if e["kind"] == "work")
        print(f"{vol_id}: {len(entries)} entries ({works} works)")

    print(f"\nTotal: {total} TOC entries across {len(src_files)} volumes "
          f"(volumes without toc_src left untouched).")


if __name__ == "__main__":
    main()
