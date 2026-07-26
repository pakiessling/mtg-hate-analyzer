"""
    mtgscrap.deck.videre
    ~~~~~~~~~~~~~~~~~~~~~
    Client for the public Videre API (https://api.videreproject.com).

    The `/archetypes/:format` endpoint returns per-archetype card-adoption
    statistics (mainboard + sideboard) over a recent MTGO event window. This is
    the API-backed replacement for scraping MTGGoldfish HTML: it gives us, for
    each archetype, which cards are played and how often, which is exactly what
    the hate-card analysis needs.

"""
from __future__ import annotations

import logging
from datetime import date

import requests

_log = logging.getLogger(__name__)

API_BASE = "https://api.videreproject.com"
DEFAULT_TIMEOUT = 20  # seconds; the Worker itself times out at 15s


class VidereAPIError(RuntimeError):
    """Raised when the Videre API returns an error or unexpected response."""


def _parse_percentage(value) -> int:
    """Parse the API's percentage field (e.g. "62.00%") into an int percent."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(round(value))
    return int(round(float(str(value).strip().rstrip("%"))))


def _resolve_window(parameters: dict) -> dict:
    """Extract the actual analyzed date window from the API's echoed parameters.

    The API echoes the resolved `min_date`/`max_date` (as ISO datetimes) even
    when the caller supplies none — that is how we know the default lookback
    (~last 31 days). Returns date-only strings plus the span in days.
    """
    def _date_only(value):
        if not value:
            return None
        return str(value)[:10]  # "2026-06-25T14:09:26.000Z" -> "2026-06-25"

    min_date = _date_only(parameters.get("min_date"))
    max_date = _date_only(parameters.get("max_date"))
    days = None
    if min_date and max_date:
        try:
            days = (date.fromisoformat(max_date) - date.fromisoformat(min_date)).days
        except ValueError:
            days = None
    return {"min_date": min_date, "max_date": max_date, "days": days}


def _normalize_cards(cards: list) -> list[dict]:
    """Normalize API card-stat entries to the shape the report code expects.

    API entry: {card, count, percentage: "62.00%", total, average}
    Normalized: {card_name, avg_count, percentage(int), count}
    """
    normalized = []
    for card in cards:
        normalized.append({
            "card_name": card["card"],
            "avg_count": round(float(card.get("average") or 0), 1),
            "percentage": _parse_percentage(card.get("percentage")),
            "count": int(card.get("count") or 0),
        })
    return normalized


def fetch_archetypes(
        fmt: str,
        min_date: str | None = None,
        max_date: str | None = None,
        limit: int = 100,
        min_decks: int = 1,
) -> list[dict]:
    """Fetch archetype card-adoption rows from the Videre API.

    Args:
        fmt: MTGO format (e.g. "modern", "legacy", "pioneer", "vintage").
        min_date: optional inclusive start date "YYYY-MM-DD". If omitted (with
            max_date), the API uses its default recent window (~last 31 days).
        max_date: optional inclusive end date "YYYY-MM-DD".
        limit: maximum number of archetype rows to request (API max 500).
        min_decks: drop archetypes with fewer than this many matching decklists.

    Returns:
        A dict ``{"archetypes": [...], "window": {...}}`` where each archetype
        is shaped as::

            {
                "id": int,
                "archetype": str,
                "count": int,          # matching decklists
                "mainboard": [ {card_name, avg_count, percentage, count}, ... ],
                "sideboard": [ {card_name, avg_count, percentage, count}, ... ],
            }

        and ``window`` is ``{"min_date", "max_date", "days"}`` describing the
        actual analyzed event window (date-only strings; ``days`` is the span).

    Raises:
        VidereAPIError: on network failure, non-200 status, or empty data.
    """
    url = f"{API_BASE}/archetypes/{fmt.lower()}"
    params: dict[str, object] = {"limit": limit}
    if min_date:
        params["min_date"] = min_date
    if max_date:
        params["max_date"] = max_date

    _log.info("Fetching %s?%s", url, "&".join(f"{k}={v}" for k, v in params.items()))

    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as e:
        raise VidereAPIError(f"Request to Videre API failed: {e}") from e

    if resp.status_code != 200:
        raise VidereAPIError(
            f"Videre API returned {resp.status_code} for {resp.url}: {resp.text[:300]}"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise VidereAPIError(f"Videre API returned invalid JSON: {e}") from e

    rows = payload.get("data")
    if not rows:
        raise VidereAPIError(
            f"Videre API returned no archetypes for format '{fmt}'. "
            f"Response meta: {payload.get('meta')}"
        )

    archetypes = []
    for row in rows:
        count = int(row.get("count") or 0)
        if count < min_decks:
            continue
        archetypes.append({
            "id": row.get("id"),
            "archetype": row.get("archetype", ""),
            "count": count,
            "mainboard": _normalize_cards(row.get("mainboard", [])),
            "sideboard": _normalize_cards(row.get("sideboard", [])),
        })

    window = _resolve_window(payload.get("parameters") or {})

    _log.info(
        "Fetched %d archetypes (%d after min_decks>=%d filter); window %s -> %s (%s days)",
        len(rows), len(archetypes), min_decks,
        window["min_date"], window["max_date"], window["days"],
    )
    return {"archetypes": archetypes, "window": window}
