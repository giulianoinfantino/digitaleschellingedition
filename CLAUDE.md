# Claude Code — Projektregeln

## Arbeitsweise

- Handeln statt fragen: Wenn mehrere Optionen zur Auswahl stehen, wähle die sinnvollste und führe sie aus, ohne vorher nachzufragen.
- Bestätigungen überspringen: Keine Rückfragen wie „Soll ich fortfahren?", „Bist du einverstanden?" oder „Möchtest du, dass ich…?". Einfach tun.
- Bei ambiguous Aufgaben die naheliegendste Interpretation wählen und direkt umsetzen.
- Kurze Antworten bevorzugen — kein Nacherzählen von bereits Gezeigtem.

## Projekt

Digitale Hegel-Edition auf Basis der Gesammelte Werke (Felix Meiner Verlag).
Primärtext (Hegel) ist gemeinfrei. Der historisch-kritische Apparat der GW-Herausgeber ist urheberrechtlich geschützt — Fußnoten daher nie extrahieren.

## OCR der GW-Seiten — Claude macht es direkt

Der pdfplumber-basierte `extractor_pdf_v24.py` produziert verstümmelten Text (Wortreihenfolgen kaputt, Wasserzeichen ins Korpus, „SfAnmerinnertwordendaß"). Die OCR der GW-Seiten mache ICH direkt im Chat aus den vorgerenderten PNGs — KEIN API-Skript, KEIN externer Dienst, KEIN Patch des alten Extractors.

**Quelle**: `GW/GW NN pic/GW NN Wissenschaft der Logik (...)_Page_NNN.png` (300 dpi, alle drei Bände vollständig vorhanden: GW 11 = 460 S., GW 12 = 366 S., GW 21 = 458 S.).

**Ziel**: pro Seite ein JSON nach `ocr/<work_id>/page_<NNNN>.json` (`work_id` ∈ `{gw-11, gw-12, gw-21}`).

### Was extrahiert wird

- **Haupttext** Hegels in Originalrechtschreibung — *Seyn*, *Verhältniß*, *daß*, *Begriff*, *Nothwendigkeit*, *Substantialitäts-Verhältniß*, *Subject*. KEINE Modernisierung.
- **Sperrsatz** (gesperrte Lettern als typografische Hervorhebung) → Markdown-Kursiv: `*Der Begriff*`. Versalsatz wie `ERSTES KAPITEL` bleibt ALL-CAPS, ohne Sterne.
- Worttrennungen am Zeilenende auflösen (`Voll-` + `endung` → `Vollendung`); innerhalb eines Absatzes durchgängiger Fließtext.

### Was NICHT extrahiert wird

- **Apparat / Fußnoten** der GW-Herausgeber (urheberrechtlich) — kleinerer Schriftgrad, durch waagerechten Strich vom Haupttext getrennt. Nur `has_footnote_apparatus: true` setzen.
- **Marginal-Zeilennummern** am Außenrand (5, 10, 15, 20, 25, …).
- **Bibliotheks-Wasserzeichen** (rotierter Text wie „Universitäts- und Landesbibliothek Bonn …" am linken Rand).
- **Kolumnentitel** (z.B. „LOGIK · LEHRE VOM BEGRIFF") → separat in `running_header`.
- **GW-Seitenkorrespondenzen am Fuß** (z.B. „9 376) 0: 225") — sind Editions-Apparat.

### Schema pro Seite

```json
{
  "page_pdf": <int>,
  "page_book": <int|null>,
  "page_kind": "body|toc|frontmatter|title_page|section_break|blank|index|appendix|imprint|unknown",
  "running_header": <string|null>,
  "paragraphs": [
    {"kind": "heading|subheading|paragraph|epigraph|list_item",
     "text": "...",
     "level": <int|null>}
  ],
  "toc_entries": [{"title": "...", "page": <int|null>}],
  "has_footnote_apparatus": <bool>,
  "notes": <string|null>
}
```

### Vorgehen

1. PNG via `Read` laden.
2. Inhalte gemäß Regeln oben in das Schema übersetzen, dabei alle Marginalien/Wasserzeichen ignorieren.
3. JSON nach `ocr/<work_id>/page_<NNNN>.json` schreiben.
4. Bei Auffälligkeiten (verschmierte Stellen, Mehrdeutigkeiten) `notes` füllen, statt zu raten.

`gw_vision.py` ist nur eine Referenz für das Prompt-Schema; der API-basierte Workflow ist nicht der gewählte Weg.
