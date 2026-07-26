#!/usr/bin/env python3
"""
Build a static GitHub Pages site from the latest hate-cards report.

Writes `_output/site/`:
  - index.html   responsive web version of the latest report
  - report.pdf   copy of the latest generated PDF (if one exists)
  - report.json  copy of the latest structured report

The folder is deployed to GitHub Pages by the videre-report workflow.
"""
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_pdf_report import (  # noqa: E402
    get_latest_json, load_from_json, generate_web_html,
)

OUTPUT_DIR = Path(__file__).parent.parent / "_output"
PAPER_DIR = OUTPUT_DIR / "paper"
REPORTS_DIR = OUTPUT_DIR / "reports"
SITE_DIR = OUTPUT_DIR / "site"


def latest(glob: str, directory: Path) -> Path | None:
    files = sorted(directory.glob(glob))
    return files[-1] if files else None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    json_path = get_latest_json()
    if not json_path:
        logger.error("No JSON report found in %s. Run videre_hate.py first.", REPORTS_DIR)
        raise SystemExit(1)

    model = load_from_json(json_path)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    # Copy the raw JSON for a data-download link.
    shutil.copyfile(json_path, SITE_DIR / "report.json")

    # Copy the latest PDF if one was rendered (may be absent without GTK libs).
    pdf_path = latest("hate_cards_*.pdf", PAPER_DIR)
    pdf_href = None
    if pdf_path:
        shutil.copyfile(pdf_path, SITE_DIR / "report.pdf")
        pdf_href = "report.pdf"
        logger.info("Included PDF: %s", pdf_path.name)
    else:
        logger.warning("No PDF found in %s; page will show 'PDF unavailable'.", PAPER_DIR)

    html = generate_web_html(model, pdf_href=pdf_href, json_href="report.json")
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    logger.info("Site written to: %s (%d archetypes)", SITE_DIR / "index.html",
                len(model["archetypes"]))


if __name__ == "__main__":
    main()
