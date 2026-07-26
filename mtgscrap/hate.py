"""
    mtgscrap.hate
    ~~~~~~~~~~~~~
    Shared helpers for hate-card analysis: loading the user's hate-card list
    (with categories) and rendering the plain-text report consumed by the PDF
    generator.

"""
from __future__ import annotations

from pathlib import Path


def load_hate_cards(hate_file: Path) -> dict[str, str]:
    """Load hate cards from a hate-cards file, tracking their category.

    The file groups cards under ``# category`` comment headers (e.g.
    ``# graveyard``). Each card line below a header is tagged with that
    category. Returns a mapping of ``card_name.lower() -> category``.

    Membership tests (``name in load_hate_cards(...)``) still work because the
    mapping's keys are the lowercased card names.
    """
    hate_cards: dict[str, str] = {}
    category = "misc"

    with open(hate_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                # Comment line doubles as a category header.
                category = line.lstrip("#").strip().lower() or "misc"
                continue
            hate_cards[line.lower()] = category

    return hate_cards


def generate_report(hate_cards_data: dict, source: str, format_name: str = "Legacy") -> str:
    """Render a formatted plain-text hate-cards report.

    Args:
        hate_cards_data: ``{archetype: {"maindeck": [...], "sideboard": [...]}}``
            where each card is ``{card_name, avg_count, percentage}``.
        source: human-readable source label shown in the header.
        format_name: MTG format name used in the title (e.g. "Modern").
    """
    lines = ["=" * 80, f"{format_name.upper()} HATE CARDS ANALYSIS",
             f"Source: {source}", "=" * 80, ""]

    for archetype, data in hate_cards_data.items():
        if not data["maindeck"] and not data["sideboard"]:
            continue

        lines.append(f"\n{archetype.upper()}")
        lines.append("-" * 80)

        for section, label in (("maindeck", "MAINDECK"), ("sideboard", "SIDEBOARD")):
            if not data[section]:
                continue
            lines.append(f"\n  {label}:")
            for card in sorted(data[section], key=lambda c: c["percentage"], reverse=True):
                lines.append(
                    f"    • {card['card_name']:40s} "
                    f"avg: {card['avg_count']:>4.1f}x  |  {card['percentage']:>3d}% of decks"
                )

        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)
