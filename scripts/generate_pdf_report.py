#!/usr/bin/env python3
"""
Generate a printer-friendly single-page A4 PDF of hate cards per archetype.

Preferred input is the structured JSON written by videre_hate.py
(_output/reports/hate_cards_<ts>.json), which carries per-card category tags,
per-archetype deck counts, and the format/date window. If no JSON is present,
it falls back to parsing the legacy text report so the old Legacy pipeline keeps
working.

Font sizes are auto-scaled to maximize readability while fitting one A4 page.
"""
import json
import logging
import re
from pathlib import Path

# weasyprint is imported lazily inside the render helpers: it needs native
# GTK/Pango libraries (present in CI/Linux) that may be absent on a dev box,
# and the HTML-generation code should remain usable without them.

OUTPUT_DIR = Path(__file__).parent.parent / "_output"
REPORTS_DIR = OUTPUT_DIR / "reports"
PAPER_DIR = OUTPUT_DIR / "paper"

# Number of hate cards shown per board per archetype (highest adoption first).
MAX_CARDS_PER_BOARD = 4

# Print-friendly muted color palette, assigned to whatever categories the data
# actually contains (so user-defined categories always get a color). Each entry
# is (background, left-accent).
PALETTE = [
    ("#d9e6f5", "#3f6fb0"),  # blue
    ("#dfebd6", "#6a9a4e"),  # green
    ("#f3dede", "#c25b5b"),  # red
    ("#f6e2cf", "#cc8a3a"),  # orange
    ("#ede3f6", "#8e6fbf"),  # purple
    ("#f7dfec", "#c25b96"),  # pink
    ("#dcecf5", "#4a90c2"),  # cyan
    ("#f6ecd2", "#c9a13b"),  # gold
    ("#d6efe9", "#3fa08a"),  # teal
    ("#e9e9e9", "#999999"),  # gray
]


def _cat_class(category: str) -> str:
    """CSS-safe class fragment for a category name."""
    return "cat-" + re.sub(r"[^a-z0-9]+", "-", (category or "misc").lower()).strip("-")


def collect_categories(archetypes: list) -> list[str]:
    """Ordered list of unique categories present in the data (by first appearance)."""
    seen = []
    for arch in archetypes:
        for board in ("maindeck", "sideboard"):
            for card in arch.get(board, []):
                cat = card.get("category", "misc")
                if cat not in seen:
                    seen.append(cat)
    return seen


def category_colors(archetypes: list) -> dict[str, tuple[str, str]]:
    """Map each present category to a palette color (cycled if there are many)."""
    cats = collect_categories(archetypes)
    return {cat: PALETTE[i % len(PALETTE)] for i, cat in enumerate(cats)}


# --------------------------------------------------------------------------- #
# Input loading                                                               #
# --------------------------------------------------------------------------- #

def get_latest_json() -> Path | None:
    """Return the newest structured JSON report, or None if there isn't one."""
    files = sorted(REPORTS_DIR.glob("hate_cards_*.json"))
    return files[-1] if files else None


def get_latest_report() -> Path:
    """Return the newest legacy text report (fallback input)."""
    report_files = sorted(REPORTS_DIR.glob("hate_cards_report_*.txt"))
    if not report_files:
        raise FileNotFoundError("No report files found in _output/reports/")
    return report_files[-1]


def extract_timestamp(path: Path) -> str:
    """Extract the YYYYMMDD_HHMMSS timestamp from a report filename."""
    match = re.search(r"(\d{8}_\d{6})", path.name)
    return match.group(1) if match else ""


def load_from_json(json_path: Path) -> dict:
    """Load the structured report into the internal render model."""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    window = payload.get("window") or {}

    # Analyzed event window, e.g. "2026-06-25 → 2026-07-26 (last 31 days)".
    if window.get("min_date") and window.get("max_date"):
        window_str = f"{window['min_date']} → {window['max_date']}"
        if window.get("days") is not None:
            window_str += f" (last {window['days']} days)"
    else:
        window_str = "recent event window"

    # Generation timestamp -> readable "2026-07-26 16:30 UTC".
    generated = payload.get("generated", "")
    gen_str = generated.replace("T", " ")[:16] + " UTC" if generated else ""

    min_pct = payload.get("min_pct")
    parts = [payload.get("source", ""), f"window: {window_str}"]
    if min_pct:
        parts.append(f"≥{min_pct}% adoption")
    if gen_str:
        parts.append(f"generated {gen_str}")
    subtitle = "  ·  ".join(p for p in parts if p)

    return {
        "title": f"{payload.get('format', 'MTG')} Hate Cards Analysis",
        "subtitle": subtitle,
        "archetypes": payload.get("archetypes", []),
    }


def parse_report(report_path: Path) -> dict:
    """Fallback: parse the legacy text report into the internal render model."""
    archetypes = []
    archetype_dict = None
    current_section = None
    skip_next_line = False
    title = "Hate Cards Analysis"

    with open(report_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()

            if line.startswith("=") or not line.strip():
                skip_next_line = False
                continue
            if "HATE CARDS ANALYSIS" in line:
                title = line.strip().title()
                continue
            if line.startswith("Source:"):
                continue
            if line.strip() and all(c == "-" for c in line.strip()):
                skip_next_line = True
                continue

            if not skip_next_line and line.isupper() and not line.startswith(" "):
                archetype_dict = {"name": line.strip(), "count": None,
                                  "maindeck": [], "sideboard": []}
                archetypes.append(archetype_dict)
                current_section = None
                continue
            skip_next_line = False

            if "MAINDECK:" in line:
                current_section = "maindeck"
                continue
            if "SIDEBOARD:" in line:
                current_section = "sideboard"
                continue

            if archetype_dict and current_section and "•" in line:
                match = re.search(r"•\s+(.+?)\s{2,}avg:\s+([\d.]+)x\s+\|\s+(\d+)%", line)
                if match:
                    archetype_dict[current_section].append({
                        "name": match.group(1).strip(),
                        "avg": float(match.group(2)),
                        "pct": int(match.group(3)),
                        "category": "misc",
                    })

    return {"title": title, "subtitle": f"Source: {report_path.name}",
            "archetypes": archetypes}


# --------------------------------------------------------------------------- #
# Rendering                                                                   #
# --------------------------------------------------------------------------- #

def _cards_html(cards: list) -> str:
    """Render a board's hate cards as category-colored chips."""
    if not cards:
        return '<span class="empty">—</span>'
    cards = sorted(cards, key=lambda c: c.get("pct", 0), reverse=True)[:MAX_CARDS_PER_BOARD]
    chips = []
    for card in cards:
        cls = _cat_class(card.get("category", "misc"))
        name = card["name"]
        name_html = f"<b>{name}</b>" if card.get("pct", 0) >= 50 else name
        chips.append(
            f'<span class="chip {cls}">{name_html}'
            f'<span class="pct">{card.get("pct", 0)}%</span>'
            f'<span class="avg">{card.get("avg", 0):.1f}</span></span>'
        )
    return "".join(chips)


def _legend_html(archetypes: list) -> str:
    """Legend of only the categories actually present in the data."""
    items = "".join(
        f'<span class="chip {_cat_class(c)} legend-chip">{c}</span>'
        for c in collect_categories(archetypes)
    )
    return f'<div class="legend">{items}</div>'


def _css(font_sizes: dict, colors: dict[str, tuple[str, str]]) -> str:
    cat_rules = []
    for cat, (bg, border) in colors.items():
        cls = _cat_class(cat)
        cat_rules.append(f".{cls} {{ background: {bg}; border-left: 2.5pt solid {border}; }}")
    cat_css = "\n        ".join(cat_rules)
    return f"""
        @page {{ size: A4; margin: 8mm; }}
        html, body {{ margin: 0; padding: 0; width: 100%; }}
        body {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: {font_sizes['body']}pt;
            color: #1a1a1a;
        }}
        .header {{ margin-bottom: 5pt; }}
        h1 {{ font-size: 15pt; margin: 0; font-weight: bold; letter-spacing: 0.3pt; }}
        .subtitle {{ font-size: {font_sizes['date']}pt; color: #666; margin: 1pt 0 4pt 0; }}
        .legend {{ margin-bottom: 4pt; }}
        .legend-chip {{ text-transform: capitalize; font-size: {font_sizes['date']}pt; }}
        table {{ width: 100%; border-collapse: collapse; }}
        thead th {{
            background: #2b2b2b; color: #fff; font-size: {font_sizes['thead']}pt;
            text-align: left; padding: 2.5pt 4pt; font-weight: bold;
        }}
        td {{ padding: 2.5pt 4pt; vertical-align: top; border-bottom: 0.5pt solid #d8d8d8; }}
        tbody tr:nth-child(even) {{ background: #f4f4f4; }}
        .arch-col {{ width: 19%; }}
        .arch-name {{ font-weight: bold; font-size: {font_sizes['body']}pt; }}
        .arch-count {{
            display: inline-block; margin-top: 1pt; color: #555;
            font-size: {font_sizes['date']}pt;
        }}
        .board-col {{ width: 40.5%; }}
        .chip {{
            display: inline-block; border-radius: 2pt; padding: 0.5pt 3pt;
            margin: 0.6pt 1.2pt 0.6pt 0; font-size: {font_sizes['cards']}pt;
            line-height: 1.35; white-space: nowrap;
        }}
        .chip .pct {{ font-weight: bold; margin-left: 3pt; }}
        .chip .avg {{ color: #555; margin-left: 3pt; font-size: {font_sizes['cards'] - 0.5}pt; }}
        .chip .avg::before {{ content: "×"; }}
        .empty {{ color: #bbb; }}
        {cat_css}
    """


def generate_html(model: dict, font_sizes: dict | None = None) -> str:
    """Build the single-page A4 HTML from the render model."""
    if font_sizes is None:
        font_sizes = {"body": 7.5, "thead": 7.0, "cards": 6.5, "date": 6.5}

    archetypes = model["archetypes"]
    colors = category_colors(archetypes)
    rows = []
    for arch in archetypes:
        count = arch.get("count")
        count_html = f'<div class="arch-count">{count} decks</div>' if count else ""
        rows.append(
            f'<tr>'
            f'<td class="arch-col"><div class="arch-name">{arch["name"]}</div>{count_html}</td>'
            f'<td class="board-col">{_cards_html(arch.get("maindeck", []))}</td>'
            f'<td class="board-col">{_cards_html(arch.get("sideboard", []))}</td>'
            f'</tr>'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{model['title']}</title>
<style>{_css(font_sizes, colors)}</style>
</head>
<body>
    <div class="header">
        <h1>{model['title']}</h1>
        <div class="subtitle">{model['subtitle']}  ·  {len(archetypes)} archetypes</div>
        {_legend_html(archetypes)}
    </div>
    <table>
        <thead>
            <tr><th>Archetype</th><th>Maindeck hate</th><th>Sideboard hate</th></tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
</body>
</html>"""


def _web_css(colors: dict[str, tuple[str, str]]) -> str:
    """Responsive web stylesheet (screen-oriented, not print)."""
    cat_rules = "\n".join(
        f".{_cat_class(cat)} {{ background: {bg}; border-left: 3px solid {border}; }}"
        for cat, (bg, border) in colors.items()
    )
    return f"""
        :root {{ color-scheme: light dark; }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
            margin: 0; color: #1a1a1a; background: #fafafa; line-height: 1.4;
        }}
        .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }}
        header {{ border-bottom: 2px solid #2b2b2b; padding-bottom: 12px; margin-bottom: 16px; }}
        .titlebar {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px; justify-content: space-between; }}
        h1 {{ font-size: 1.6rem; margin: 0; }}
        .subtitle {{ color: #555; font-size: 0.85rem; margin: 6px 0 10px; }}
        .btn {{
            display: inline-block; background: #2b2b2b; color: #fff; text-decoration: none;
            padding: 7px 14px; border-radius: 6px; font-size: 0.85rem; font-weight: 600;
            white-space: nowrap;
        }}
        .btn.secondary {{ background: #e6e6e6; color: #333; margin-left: 6px; }}
        .btn.disabled {{ background: #ccc; color: #777; pointer-events: none; }}
        .legend {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }}
        table {{ width: 100%; border-collapse: collapse; background: #fff; }}
        thead th {{
            position: sticky; top: 0; background: #2b2b2b; color: #fff; text-align: left;
            padding: 8px 10px; font-size: 0.8rem;
        }}
        td {{ padding: 8px 10px; vertical-align: top; border-bottom: 1px solid #eee; }}
        tbody tr:nth-child(even) {{ background: #f6f6f6; }}
        .arch-col {{ width: 20%; min-width: 130px; }}
        .arch-name {{ font-weight: 700; }}
        .arch-count {{ color: #777; font-size: 0.75rem; margin-top: 2px; }}
        .board-col {{ width: 40%; }}
        .chip {{
            display: inline-block; border-radius: 4px; padding: 2px 7px; margin: 2px 3px 2px 0;
            font-size: 0.8rem; white-space: nowrap;
        }}
        .chip .pct {{ font-weight: 700; margin-left: 5px; }}
        .chip .avg {{ color: #555; margin-left: 5px; font-size: 0.72rem; }}
        .chip .avg::before {{ content: "×"; }}
        .legend-chip {{ text-transform: capitalize; font-size: 0.75rem; }}
        .empty {{ color: #bbb; }}
        @media (max-width: 640px) {{
            table, thead, tbody, th, td, tr {{ display: block; }}
            thead {{ display: none; }}
            tr {{ border-bottom: 2px solid #ddd; padding: 6px 0; }}
            .board-col::before {{ content: attr(data-label); font-weight: 700; color: #888; font-size: 0.7rem; display: block; }}
        }}
        {cat_rules}
    """


def generate_web_html(model: dict, pdf_href: str | None = None,
                      json_href: str | None = None) -> str:
    """Build a responsive, screen-oriented web page from the render model.

    Reuses the same category coloring and chip rendering as the PDF, but with
    fluid CSS instead of the fixed A4 print layout. `pdf_href`/`json_href`, when
    given, add download buttons.
    """
    archetypes = model["archetypes"]
    colors = category_colors(archetypes)

    rows = []
    for arch in archetypes:
        count = arch.get("count")
        count_html = f'<div class="arch-count">{count} decks</div>' if count else ""
        rows.append(
            f'<tr>'
            f'<td class="arch-col"><div class="arch-name">{arch["name"]}</div>{count_html}</td>'
            f'<td class="board-col" data-label="Maindeck">{_cards_html(arch.get("maindeck", []))}</td>'
            f'<td class="board-col" data-label="Sideboard">{_cards_html(arch.get("sideboard", []))}</td>'
            f'</tr>'
        )

    if pdf_href:
        pdf_btn = f'<a class="btn" href="{pdf_href}" download>Download PDF</a>'
    else:
        pdf_btn = '<span class="btn disabled">PDF unavailable</span>'
    json_btn = f'<a class="btn secondary" href="{json_href}" download>JSON</a>' if json_href else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{model['title']}</title>
<style>{_web_css(colors)}</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="titlebar">
        <h1>{model['title']}</h1>
        <div>{pdf_btn}{json_btn}</div>
      </div>
      <div class="subtitle">{model['subtitle']}  ·  {len(archetypes)} archetypes</div>
      {_legend_html(archetypes)}
    </header>
    <table>
      <thead>
        <tr><th>Archetype</th><th>Maindeck hate</th><th>Sideboard hate</th></tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>
</body>
</html>"""


def get_page_count(html_content: str) -> int:
    """Render without saving and count pages; conservative on failure."""
    from weasyprint import HTML
    try:
        return len(HTML(string=html_content).render().pages)
    except Exception:
        return 999


def find_optimal_font_sizes(model: dict, logger) -> dict:
    """Increase font sizes until the layout would spill onto a second page."""
    base_sizes = {"body": 7.5, "thead": 7.0, "cards": 6.5, "date": 6.5}
    current_scale = 1.0
    increment = 0.02
    last_working = base_sizes.copy()

    logger.info("Optimizing font sizes for single-page fit...")
    for _ in range(50):
        sizes = {k: round(v * current_scale, 2) for k, v in base_sizes.items()}
        pages = get_page_count(generate_html(model, sizes))
        if pages == 1:
            logger.info("  scale %.2fx (%.1fpt body): 1 page", current_scale, sizes["body"])
            last_working = sizes.copy()
            current_scale += increment
        else:
            logger.info("  scale %.2fx (%.1fpt body): %d pages - stopping",
                        current_scale, sizes["body"], pages)
            break

    logger.info("Optimal body font: %.1fpt", last_working["body"])
    return last_working


def main():
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    json_path = get_latest_json()
    if json_path:
        logger.info("Reading JSON report: %s", json_path.name)
        model = load_from_json(json_path)
        source_path = json_path
    else:
        report_path = get_latest_report()
        logger.info("No JSON found; parsing text report: %s", report_path.name)
        model = parse_report(report_path)
        source_path = report_path

    if not model["archetypes"]:
        logger.warning("No archetype data found in report")
        return

    logger.info("Found %d archetypes", len(model["archetypes"]))

    optimal_sizes = find_optimal_font_sizes(model, logger)
    html_content = generate_html(model, optimal_sizes)

    timestamp = extract_timestamp(source_path)
    pdf_path = PAPER_DIR / (f"hate_cards_{timestamp}.pdf" if timestamp else "hate_cards.pdf")

    from weasyprint import HTML
    HTML(string=html_content).write_pdf(str(pdf_path))
    logger.info("PDF saved to: %s", pdf_path)


if __name__ == "__main__":
    main()
