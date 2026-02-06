"""Direct scraping of FPV shop websites for motor listings."""

import logging
import re
from urllib.parse import urljoin, quote_plus
from typing import Optional

from bs4 import BeautifulSoup

from ..config import SCRAPE_SOURCES
from ..models import MotorSpec
from ..parser import parse_product_listing
from .base import BaseScraper

logger = logging.getLogger(__name__)


class ShopScraper(BaseScraper):
    """Scrapes FPV shop websites for brushless motor product listings."""

    source_name = "shop"

    def _extract_product_links(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[dict]:
        """Extract product links from a search results / category page."""
        products = []
        seen_urls = set()

        # Common product listing patterns
        selectors = [
            "a.product-item-link",
            "a.product-title",
            ".product-card a",
            ".product-item a",
            ".grid-product__link",
            ".product-link",
            "h2 a",
            "h3 a",
            ".product-name a",
            ".product a[href]",
        ]

        for selector in selectors:
            for link in soup.select(selector):
                href = link.get("href", "")
                if not href:
                    continue

                url = urljoin(base_url, href)
                title = link.get_text(strip=True)

                # Filter: must look like a motor product
                combined = f"{url} {title}".lower()
                if not any(kw in combined for kw in [
                    "motor", "brushless", "kv",
                ]):
                    continue

                if url not in seen_urls:
                    seen_urls.add(url)

                    # Try to find an image nearby
                    img = link.find("img")
                    image_url = ""
                    if img:
                        image_url = img.get("src") or img.get("data-src") or ""
                        if image_url:
                            image_url = urljoin(base_url, image_url)

                    products.append({
                        "url": url,
                        "title": title,
                        "image_url": image_url,
                    })

        # Also look for links with motor-related hrefs
        for a in soup.find_all("a", href=True):
            href = a["href"]
            url = urljoin(base_url, href)

            if url in seen_urls:
                continue

            url_lower = url.lower()
            if any(kw in url_lower for kw in [
                "brushless-motor", "motor-brushless", "/motors/",
                "/motor-", "-motor-",
            ]):
                title = a.get_text(strip=True)
                if len(title) > 5:
                    seen_urls.add(url)
                    products.append({
                        "url": url,
                        "title": title,
                        "image_url": "",
                    })

        return products

    def scrape_shop(
        self, shop_key: str, search_query: str = "brushless motor"
    ) -> list[MotorSpec]:
        """Scrape a single shop for motor listings."""
        if shop_key not in SCRAPE_SOURCES:
            logger.warning("Unknown shop: %s", shop_key)
            return []

        shop = SCRAPE_SOURCES[shop_key]
        search_url = shop["search_url"].format(query=quote_plus(search_query))
        base_url = shop["base_url"]

        logger.info("[%s] Searching: %s", shop_key, search_url)

        soup = self._soup(search_url)
        if soup is None:
            return []

        products = self._extract_product_links(soup, base_url)
        logger.info("[%s] Found %d product links", shop_key, len(products))

        all_motors = []
        for product in products:
            try:
                motors = self.scrape_product_page(
                    url=product["url"],
                    brand="",  # Will be detected from page
                )
                all_motors.extend(motors)
            except Exception as e:
                logger.warning(
                    "[%s] Failed to scrape product %s: %s",
                    shop_key,
                    product["url"],
                    e,
                )

        return all_motors

    def scrape_all_shops(self) -> list[MotorSpec]:
        """Scrape all configured shops."""
        all_motors = []
        search_terms = [
            "brushless motor",
            "fpv motor",
            "racing drone motor",
        ]

        for shop_key in SCRAPE_SOURCES:
            for term in search_terms:
                try:
                    motors = self.scrape_shop(shop_key, term)
                    all_motors.extend(motors)
                    logger.info(
                        "[%s] Scraped %d motors for '%s'",
                        shop_key,
                        len(motors),
                        term,
                    )
                except Exception as e:
                    logger.error("[%s] Shop scrape failed: %s", shop_key, e)

        return all_motors

    def scrape(self) -> list[MotorSpec]:
        """Run full shop scraping cycle."""
        return self.scrape_all_shops()


class ManufacturerScraper(BaseScraper):
    """Scrapes manufacturer websites directly for motor specifications."""

    source_name = "manufacturer"

    # Known manufacturer product pages
    MANUFACTURER_URLS = {
        "T-Motor": [
            "https://www.tmotor.com/category/Multirotor-Motor.html",
        ],
        "BetaFPV": [
            "https://betafpv.com/collections/brushless-motors",
        ],
        "Emax": [
            "https://emax-usa.com/collections/motors",
        ],
        "iFlight": [
            "https://www.iflight-rc.com/index.php?route=product/category&path=25_56",
        ],
        "GepRC": [
            "https://geprc.com/category/motors/",
        ],
        "Flywoo": [
            "https://flywoo.net/collections/motors",
        ],
        "BrotherHobby": [
            "https://www.brotherhobbystore.com/motor-c0001",
        ],
    }

    def scrape_manufacturer(self, brand: str) -> list[MotorSpec]:
        """Scrape a manufacturer's motor listing page."""
        urls = self.MANUFACTURER_URLS.get(brand, [])
        if not urls:
            return []

        all_motors = []
        for listing_url in urls:
            logger.info("[%s] Scraping manufacturer page: %s", brand, listing_url)

            soup = self._soup(listing_url)
            if soup is None:
                continue

            # Extract product links
            products = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                url = urljoin(listing_url, href)
                title = a.get_text(strip=True)
                combined = f"{url} {title}".lower()

                if any(kw in combined for kw in ["motor", "brushless"]):
                    if len(title) > 3:
                        products.append({
                            "url": url,
                            "title": title,
                            "brand": brand,
                        })

            # Deduplicate
            seen = set()
            unique_products = []
            for p in products:
                if p["url"] not in seen:
                    seen.add(p["url"])
                    unique_products.append(p)

            logger.info(
                "[%s] Found %d product links on manufacturer page",
                brand,
                len(unique_products),
            )

            for product in unique_products[:20]:  # Limit per manufacturer
                try:
                    motors = self.scrape_product_page(
                        url=product["url"],
                        brand=brand,
                    )
                    all_motors.extend(motors)
                except Exception as e:
                    logger.warning(
                        "[%s] Failed to scrape %s: %s",
                        brand,
                        product["url"],
                        e,
                    )

        return all_motors

    def scrape(self) -> list[MotorSpec]:
        """Scrape all known manufacturers."""
        all_motors = []
        for brand in self.MANUFACTURER_URLS:
            try:
                motors = self.scrape_manufacturer(brand)
                all_motors.extend(motors)
            except Exception as e:
                logger.error(
                    "Failed to scrape manufacturer %s: %s", brand, e
                )

        return all_motors
