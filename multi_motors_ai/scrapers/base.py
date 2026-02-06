"""Base scraper with common functionality."""

import logging
import random
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from ..config import USER_AGENT, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX
from ..models import MotorSpec

logger = logging.getLogger(__name__)


class BaseScraper:
    """Base class for motor scrapers."""

    source_name: str = "base"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        })

    def _delay(self):
        """Random delay between requests to be respectful."""
        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        time.sleep(delay)

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """Make a GET request with error handling and delay."""
        self._delay()
        try:
            response = self.session.get(url, timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.warning("[%s] Request failed for %s: %s", self.source_name, url, e)
            return None

    def _soup(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a URL and return a BeautifulSoup object."""
        response = self._get(url)
        if response is None:
            return None
        return BeautifulSoup(response.text, "lxml")

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Extract visible text from a page."""
        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    def _extract_specs_table(self, soup: BeautifulSoup) -> dict:
        """Try to extract specification tables from the page."""
        specs = {}

        # Look for common spec table patterns
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if key and value:
                        specs[key] = value

        # Look for definition lists
        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                key = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                if key and value:
                    specs[key] = value

        # Look for spec-like divs (key: value patterns)
        for div in soup.find_all(["div", "li", "span"], class_=lambda c: c and any(
            kw in (c if isinstance(c, str) else " ".join(c)).lower()
            for kw in ["spec", "feature", "detail", "attribute", "param"]
        )):
            text = div.get_text(strip=True)
            if ":" in text:
                parts = text.split(":", 1)
                specs[parts[0].strip()] = parts[1].strip()

        return specs

    def _extract_images(self, soup: BeautifulSoup) -> list[str]:
        """Extract product image URLs from the page."""
        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            alt = (img.get("alt") or "").lower()
            if src and any(kw in alt for kw in ["motor", "brushless", "product"]):
                images.append(src)
            elif src and not any(kw in src.lower() for kw in [
                "logo", "icon", "banner", "avatar", "payment", "flag"
            ]):
                images.append(src)
        return images[:5]  # Limit to first 5

    def scrape(self) -> list[MotorSpec]:
        """Main scrape method - override in subclasses."""
        raise NotImplementedError

    def scrape_product_page(self, url: str, brand: str = "") -> list[MotorSpec]:
        """Scrape a single product page for motor specs."""
        from ..parser import parse_product_listing

        soup = self._soup(url)
        if soup is None:
            return []

        # Extract title
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Extract description / body text
        description = self._extract_text(soup)

        # Extract specs table
        specs_table = self._extract_specs_table(soup)

        # Extract images
        images = self._extract_images(soup)
        image_url = images[0] if images else ""

        motors = parse_product_listing(
            title=title,
            description=description,
            brand=brand,
            url=url,
            image_url=image_url,
            specs_table=specs_table,
        )

        logger.info(
            "[%s] Found %d motor(s) on %s",
            self.source_name,
            len(motors),
            url,
        )
        return motors
