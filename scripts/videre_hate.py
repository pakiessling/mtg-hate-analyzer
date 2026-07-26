#!/usr/bin/env python3
"""
Fetch archetype card-adoption data from the Videre API and report which hate
cards (from _input/hatecards.txt) show up per archetype.

This is the API-backed replacement for the scrape_legacy.py + analyze_hate_cards.py
pipeline. It writes two artifacts to _output/reports/:
  - hate_cards_report_<ts>.txt   human-readable text report (PDF-parseable)
  - hate_cards_<ts>.json         structured data consumed by generate_pdf_report.py
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the mtgscrap package importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).parent.parent))

from mtgscrap.hate import load_hate_cards, generate_report  # noqa: E402
from mtgscrap.deck.videre import fetch_archetypes, VidereAPIError  # noqa: E402

OUTPUT_DIR = Path(__file__).parent.parent / "_output"
REPORTS_DIR = OUTPUT_DIR / "reports"
INPUT_DIR = Path(__file__).parent.parent / "_input"


def filter_hate_cards(archetypes: list[dict], hate_cards: dict[str, str],
                      min_pct: int = 0) -> list[dict]:
    """Reduce each archetype's boards to only the hate cards it plays.

    Returns a list of per-archetype dicts preserving API order (by play rate),
    each card annotated with its category. Cards adopted by fewer than
    ``min_pct`` percent of the archetype's decks are dropped as noise.
    Archetypes with no hate cards left in either board are dropped.
    """
    result = []
    # API uses "mainboard"; the report/PDF code uses "maindeck".
    board_map = {"maindeck": "mainboard", "sideboard": "sideboard"}
    for arch in archetypes:
        entry = {"name": arch["archetype"], "count": arch["count"],
                 "maindeck": [], "sideboard": []}
        for out_board, api_board in board_map.items():
            for card in arch[api_board]:
                category = hate_cards.get(card["card_name"].lower())
                if category is None:
                    continue
                if card["percentage"] < min_pct:
                    continue
                entry[out_board].append({
                    "name": card["card_name"],
                    "avg": card["avg_count"],
                    "pct": card["percentage"],
                    "category": category,
                })
        if entry["maindeck"] or entry["sideboard"]:
            result.append(entry)
    return result


def to_report_data(filtered: list[dict]) -> dict:
    """Convert the filtered list into the {archetype: {maindeck, sideboard}}
    structure that analyze_hate_cards.generate_report expects."""
    data = {}
    for entry in filtered:
        data[entry["name"]] = {
            "maindeck": [
                {"card_name": c["name"], "avg_count": c["avg"], "percentage": c["pct"]}
                for c in entry["maindeck"]
            ],
            "sideboard": [
                {"card_name": c["name"], "avg_count": c["avg"], "percentage": c["pct"]}
                for c in entry["sideboard"]
            ],
        }
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report hate cards per archetype using the Videre API")
    parser.add_argument("--format", dest="fmt", default="modern",
                        help="MTG format (default: modern)")
    parser.add_argument("--min-date", default=None,
                        help="Inclusive start date YYYY-MM-DD (default: API's recent window)")
    parser.add_argument("--max-date", default=None,
                        help="Inclusive end date YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max archetype rows to fetch (default: 100)")
    parser.add_argument("--min-decks", type=int, default=5,
                        help="Drop archetypes with fewer than this many decks (default: 5)")
    parser.add_argument("--min-pct", type=int, default=20,
                        help="Hide hate cards run in fewer than this %% of the "
                             "archetype's decks (default: 20)")
    parser.add_argument("--hate-file", default=str(INPUT_DIR / "hatecards.txt"),
                        help="Path to the hate-cards file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    hate_cards = load_hate_cards(Path(args.hate_file))
    logger.info("Loaded %d hate cards from %s", len(hate_cards), args.hate_file)

    try:
        result = fetch_archetypes(
            args.fmt, min_date=args.min_date, max_date=args.max_date,
            limit=args.limit, min_decks=args.min_decks,
        )
    except VidereAPIError as e:
        logger.error("Failed to fetch data: %s", e)
        raise SystemExit(1)

    archetypes = result["archetypes"]
    window = result["window"]  # resolved by the API: {min_date, max_date, days}

    filtered = filter_hate_cards(archetypes, hate_cards, min_pct=args.min_pct)
    if not filtered:
        logger.warning("No hate cards found in any archetype for the selected window.")

    format_name = args.fmt.capitalize()
    window_str = f"{window['min_date']} -> {window['max_date']}"
    source = f"Videre API /archetypes/{args.fmt}"

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # Text report (backward compatible, human-readable).
    report_source = f"{source}  |  window: {window_str} (last {window['days']} days)"
    report = generate_report(to_report_data(filtered), report_source, format_name=format_name)
    txt_path = REPORTS_DIR / f"hate_cards_report_{timestamp}.txt"
    txt_path.write_text(report, encoding="utf-8")
    logger.info("Text report saved to: %s", txt_path)

    # Structured JSON (drives the redesigned PDF).
    json_payload = {
        "format": format_name,
        "source": source,
        "window": window,
        "min_pct": args.min_pct,
        "generated": now.isoformat(timespec="seconds"),
        "archetypes": filtered,
    }
    json_path = REPORTS_DIR / f"hate_cards_{timestamp}.json"
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")
    logger.info("JSON report saved to: %s", json_path)

    print(report)


if __name__ == "__main__":
    main()
