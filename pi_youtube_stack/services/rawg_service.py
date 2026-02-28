# -*- coding: utf-8 -*-
"""
RAWG.io Game Database Service
================================
Fetches game data from the RAWG.io API (free tier — 20K requests/month).
Provides methods for:
  - Fetching monthly game releases
  - Searching for specific games
  - Getting detailed game information
  - Storing fetched data in the local PostgreSQL database

API Docs: https://rawg.io/apidocs
"""

import json
import logging
from datetime import date, datetime
from typing import Optional

import requests

from config.settings import settings
from database.connection import execute_query
from database.models import Game, ArabicSupport

logger = logging.getLogger(__name__)


class RAWGService:
    """
    RAWG.io API client for fetching game data.

    Usage:
        service = RAWGService()
        games = service.get_monthly_releases(2026, 2)
        game = service.get_game_details("elden-ring")
    """

    TIMEOUT = 30  # seconds

    def __init__(self):
        """Initialize with RAWG API configuration."""
        cfg = settings.rawg
        self.api_key = cfg.api_key
        self.base_url = cfg.base_url.rstrip("/")
        self.page_size = cfg.page_size
        logger.info("RAWGService initialized (base_url=%s)", self.base_url)

    def _request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """
        Make an authenticated GET request to the RAWG API.

        Args:
            endpoint: API endpoint (e.g., "/games").
            params: Additional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            RuntimeError: On HTTP errors.
        """
        url = f"{self.base_url}{endpoint}"
        request_params = {"key": self.api_key}
        if params:
            request_params.update(params)

        try:
            response = requests.get(url, params=request_params, timeout=self.TIMEOUT)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as exc:
            logger.error("RAWG API HTTP error: %s — %s", exc, response.text[:300])
            raise RuntimeError(f"RAWG API error: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            logger.error("RAWG API request failed: %s", exc)
            raise RuntimeError(f"RAWG API connection error: {exc}") from exc

    # ------------------------------------------------------------------
    # Game discovery methods
    # ------------------------------------------------------------------

    def get_monthly_releases(
        self,
        year: int,
        month: int,
        page: int = 1,
        ordering: str = "-rating",
    ) -> list[dict]:
        """
        Get games released in a specific month.

        Args:
            year: Release year (e.g., 2026).
            month: Release month (1-12).
            page: Pagination page number.
            ordering: Sort order (-rating, -released, -metacritic, etc.).

        Returns:
            List of game dicts from RAWG.
        """
        # Build date range for the month
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        params = {
            "dates": f"{start_date},{end_date}",
            "ordering": ordering,
            "page_size": self.page_size,
            "page": page,
        }

        data = self._request("/games", params)
        games = data.get("results", [])
        total = data.get("count", 0)

        logger.info(
            "Fetched %d/%d games for %d-%02d (page %d)",
            len(games),
            total,
            year,
            month,
            page,
        )
        return games

    def get_upcoming_games(
        self,
        page: int = 1,
        ordering: str = "-added",
    ) -> list[dict]:
        """
        Get upcoming game releases (future release dates).

        Args:
            page: Pagination page.
            ordering: Sort order.

        Returns:
            List of upcoming game dicts.
        """
        today = date.today().isoformat()
        future = f"{date.today().year + 1}-12-31"

        params = {
            "dates": f"{today},{future}",
            "ordering": ordering,
            "page_size": self.page_size,
            "page": page,
        }

        data = self._request("/games", params)
        return data.get("results", [])

    def search_games(
        self,
        query: str,
        page: int = 1,
    ) -> list[dict]:
        """
        Search for games by name.

        Args:
            query: Search query string.
            page: Pagination page.

        Returns:
            List of matching game dicts.
        """
        params = {
            "search": query,
            "page_size": self.page_size,
            "page": page,
        }

        data = self._request("/games", params)
        return data.get("results", [])

    def get_game_details(self, slug_or_id: str | int) -> dict:
        """
        Get detailed information about a specific game.

        Args:
            slug_or_id: Game slug (e.g., "elden-ring") or RAWG game ID.

        Returns:
            Detailed game data dict.
        """
        return self._request(f"/games/{slug_or_id}")

    def get_game_screenshots(self, slug_or_id: str | int) -> list[dict]:
        """Get screenshots for a game."""
        data = self._request(f"/games/{slug_or_id}/screenshots")
        return data.get("results", [])

    # ------------------------------------------------------------------
    # Data transformation & storage
    # ------------------------------------------------------------------

    def rawg_to_game_model(self, rawg_data: dict) -> Game:
        """
        Transform raw RAWG API data into our Game model.

        Args:
            rawg_data: Raw game dict from RAWG API.

        Returns:
            A Game model instance.
        """
        # Extract platform names
        platforms = []
        if rawg_data.get("platforms"):
            platforms = [
                p["platform"]["name"]
                for p in rawg_data["platforms"]
                if p.get("platform", {}).get("name")
            ]

        # Extract genre names
        genres = []
        if rawg_data.get("genres"):
            genres = [g["name"] for g in rawg_data["genres"]]

        # Extract developer names
        developers = []
        if rawg_data.get("developers"):
            developers = [d["name"] for d in rawg_data["developers"]]

        # Extract publisher names
        publishers = []
        if rawg_data.get("publishers"):
            publishers = [p["name"] for p in rawg_data["publishers"]]

        # Parse release date
        release_date = None
        if rawg_data.get("released"):
            try:
                release_date = datetime.strptime(
                    rawg_data["released"], "%Y-%m-%d"
                ).date()
            except ValueError:
                pass

        return Game(
            rawg_id=rawg_data.get("id"),
            title=rawg_data.get("name", "Unknown"),
            slug=rawg_data.get("slug"),
            description=rawg_data.get("description_raw", ""),
            release_date=release_date,
            platforms=platforms,
            genres=genres,
            developers=developers,
            publishers=publishers,
            metacritic=rawg_data.get("metacritic"),
            rating=rawg_data.get("rating"),
            background_image=rawg_data.get("background_image"),
            arabic_support=ArabicSupport(),  # Will be enriched separately
        )

    def store_game(self, game: Game) -> str:
        """
        Store or update a game in the local PostgreSQL database.
        Uses UPSERT (ON CONFLICT) based on rawg_id.

        Args:
            game: Game model instance to store.

        Returns:
            UUID of the stored/updated game record.
        """
        query = """
            INSERT INTO games (
                rawg_id, title, title_ar, slug, description,
                release_date, platforms, genres, developers, publishers,
                price, gamepass, arabic_support, metacritic, rating,
                background_image
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s
            )
            ON CONFLICT (rawg_id) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                release_date = EXCLUDED.release_date,
                platforms = EXCLUDED.platforms,
                genres = EXCLUDED.genres,
                developers = EXCLUDED.developers,
                publishers = EXCLUDED.publishers,
                metacritic = EXCLUDED.metacritic,
                rating = EXCLUDED.rating,
                background_image = EXCLUDED.background_image,
                updated_at = NOW()
            RETURNING id
        """

        params = (
            game.rawg_id,
            game.title,
            game.title_ar,
            game.slug,
            game.description,
            game.release_date,
            json.dumps(game.platforms),
            json.dumps(game.genres),
            json.dumps(game.developers),
            json.dumps(game.publishers),
            game.price,
            game.gamepass,
            json.dumps(game.arabic_support.model_dump()),
            game.metacritic,
            game.rating,
            game.background_image,
        )

        result = execute_query(query, params)
        game_id = result[0]["id"] if result else None
        logger.info(
            "Stored game: %s (id=%s, rawg_id=%s)", game.title, game_id, game.rawg_id
        )
        return str(game_id)

    def fetch_and_store_monthly(
        self,
        year: int,
        month: int,
        max_pages: int = 3,
    ) -> list[Game]:
        """
        Fetch all games for a month from RAWG and store in the database.

        Args:
            year: Target year.
            month: Target month.
            max_pages: Maximum API pages to fetch.

        Returns:
            List of stored Game models.
        """
        all_games = []

        for page in range(1, max_pages + 1):
            raw_games = self.get_monthly_releases(year, month, page=page)

            if not raw_games:
                break

            for raw in raw_games:
                try:
                    # Get detailed info for each game
                    details = self.get_game_details(raw["id"])
                    game = self.rawg_to_game_model(details)
                    self.store_game(game)
                    all_games.append(game)
                except Exception as exc:
                    logger.warning(
                        "Failed to process game '%s': %s",
                        raw.get("name", "?"),
                        exc,
                    )

        logger.info(
            "Fetched and stored %d games for %d-%02d",
            len(all_games),
            year,
            month,
        )
        return all_games

    def get_stored_games_for_month(
        self,
        year: int,
        month: int,
    ) -> list[dict]:
        """
        Retrieve games for a specific month from the local database.

        Args:
            year: Target year.
            month: Target month.

        Returns:
            List of game records as dicts.
        """
        query = """
            SELECT * FROM games
            WHERE EXTRACT(YEAR FROM release_date) = %s
              AND EXTRACT(MONTH FROM release_date) = %s
            ORDER BY release_date ASC, rating DESC NULLS LAST
        """
        return execute_query(query, (year, month)) or []
