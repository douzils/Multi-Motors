"""DuckDuckGo search-based motor discovery."""

import logging
import re
from typing import Optional

from duckduckgo_search import DDGS

from ..config import MOTOR_BRANDS, SEARCH_QUERIES, STATOR_SIZES, MAX_RESULTS_PER_SEARCH
from ..models import MotorSpec
from .base import BaseScraper

logger = logging.getLogger(__name__)

# URL patterns that are likely motor product pages
MOTOR_URL_PATTERNS = [
    r"motor",
    r"brushless",
    r"\d{4}",  # Stator size in URL
    r"\d+kv",
]

# URLs to skip
SKIP_PATTERNS = [
    r"youtube\.com",
    r"facebook\.com",
    r"instagram\.com",
    r"twitter\.com",
    r"reddit\.com/r/",
    r"amazon\.",
    r"ebay\.",
    r"wikipedia\.org",
    r"\.pdf$",
]


class SearchEngineScraper(BaseScraper):
    """Uses DuckDuckGo to discover brushless motor product pages."""

    source_name = "search"

    def __init__(self):
        super().__init__()
        self._searched_urls: set[str] = set()

    def _is_motor_url(self, url: str, title: str = "", snippet: str = "") -> bool:
        """Check if a URL is likely a motor product page."""
        combined = f"{url} {title} {snippet}".lower()

        # Skip unwanted sites
        for pattern in SKIP_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return False

        # Check for motor-related content
        motor_keywords = [
            "brushless", "motor", "kv", "stator",
            "fpv", "drone", "racing", "quad",
        ]
        return any(kw in combined for kw in motor_keywords)

    def search_brand(self, brand: str, max_results: int = 10) -> list[dict]:
        """Search for motors from a specific brand."""
        results = []
        queries = [
            f"{brand} brushless motor fpv specifications",
            f"{brand} motor drone KV weight stator",
        ]

        for query in queries:
            try:
                with DDGS() as ddgs:
                    search_results = list(ddgs.text(
                        query,
                        max_results=max_results,
                    ))
                    for r in search_results:
                        url = r.get("href", "")
                        if url and url not in self._searched_urls:
                            if self._is_motor_url(url, r.get("title", ""), r.get("body", "")):
                                results.append({
                                    "url": url,
                                    "title": r.get("title", ""),
                                    "snippet": r.get("body", ""),
                                    "brand": brand,
                                })
                                self._searched_urls.add(url)
            except Exception as e:
                logger.warning("Search failed for query '%s': %s", query, e)
                self._delay()

            self._delay()

        logger.info("Found %d potential motor pages for brand '%s'", len(results), brand)
        return results

    def search_stator_size(self, stator: str, max_results: int = 10) -> list[dict]:
        """Search for motors by stator size."""
        results = []
        query = f"brushless motor {stator} fpv drone specifications KV"

        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(
                    query,
                    max_results=max_results,
                ))
                for r in search_results:
                    url = r.get("href", "")
                    if url and url not in self._searched_urls:
                        if self._is_motor_url(url, r.get("title", ""), r.get("body", "")):
                            results.append({
                                "url": url,
                                "title": r.get("title", ""),
                                "snippet": r.get("body", ""),
                                "brand": "",
                            })
                            self._searched_urls.add(url)
        except Exception as e:
            logger.warning("Search failed for stator '%s': %s", stator, e)

        self._delay()
        return results

    def search_new_motors(self, max_results: int = 15) -> list[dict]:
        """Search for newly released brushless motors."""
        results = []
        queries = [
            "new brushless motor fpv 2024 2025 specifications",
            "latest fpv racing motor release brushless",
            "new drone motor brushless KV specs",
            "best fpv motor 2025 brushless stator",
        ]

        for query in queries:
            try:
                with DDGS() as ddgs:
                    search_results = list(ddgs.text(
                        query,
                        max_results=max_results,
                    ))
                    for r in search_results:
                        url = r.get("href", "")
                        if url and url not in self._searched_urls:
                            if self._is_motor_url(url, r.get("title", ""), r.get("body", "")):
                                results.append({
                                    "url": url,
                                    "title": r.get("title", ""),
                                    "snippet": r.get("body", ""),
                                    "brand": "",
                                })
                                self._searched_urls.add(url)
            except Exception as e:
                logger.warning("Search failed for query '%s': %s", query, e)

            self._delay()

        logger.info("Found %d potential new motor pages", len(results))
        return results

    def discover_motors(
        self,
        brands: Optional[list[str]] = None,
        stator_sizes: Optional[list[str]] = None,
        include_new: bool = True,
    ) -> list[dict]:
        """Run a full discovery cycle across brands, sizes, and new releases."""
        all_results = []

        if brands is None:
            brands = MOTOR_BRANDS

        if stator_sizes is None:
            stator_sizes = STATOR_SIZES

        # Search by brand
        for brand in brands:
            results = self.search_brand(brand)
            all_results.extend(results)
            logger.info("Brand '%s': found %d URLs", brand, len(results))

        # Search by stator size
        for stator in stator_sizes:
            results = self.search_stator_size(stator)
            all_results.extend(results)

        # Search for new releases
        if include_new:
            results = self.search_new_motors()
            all_results.extend(results)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique_results.append(r)

        logger.info(
            "Discovery complete: %d unique URLs found from %d total",
            len(unique_results),
            len(all_results),
        )
        return unique_results

    def scrape(self) -> list[MotorSpec]:
        """Run full discovery and scrape cycle."""
        discovered = self.discover_motors()
        all_motors = []

        for result in discovered:
            try:
                motors = self.scrape_product_page(
                    url=result["url"],
                    brand=result.get("brand", ""),
                )
                all_motors.extend(motors)
            except Exception as e:
                logger.warning(
                    "Failed to scrape %s: %s", result["url"], e
                )

        logger.info("Total motors scraped: %d", len(all_motors))
        return all_motors
