"""mtgscrap.deck - Videre API client for archetype card-adoption data."""
from mtgscrap.deck.videre import fetch_archetypes, VidereAPIError

__all__ = ["fetch_archetypes", "VidereAPIError"]
